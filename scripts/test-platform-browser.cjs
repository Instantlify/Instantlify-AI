/* Local-only browser acceptance. Creates then revokes a disposable platform account.
 * Credentials stay in process memory and are never printed or written to disk.
 */
const { chromium } = require('../frontend/node_modules/@playwright/test');
const { spawnSync } = require('node:child_process');
const { randomBytes, createHmac } = require('node:crypto');
const { mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..');
const account = { username: `ops-browser-${Date.now()}`, password: randomBytes(32).toString('base64url') };
let stage = 'fixture';
function shell(source, payload = account) {
  const result = spawnSync('docker', ['compose', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', source], {
    cwd: root, input: JSON.stringify(payload), encoding: 'utf8', timeout: 30000,
  });
  if (result.status !== 0) throw new Error('Console browser fixture command failed.');
  return result.stdout.trim().split('\n').at(-1);
}
function totp(secret) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const letter of secret.replace(/=/g, '')) bits += alphabet.indexOf(letter).toString(2).padStart(5, '0');
  const bytes = []; for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = createHmac('sha1', Buffer.from(bytes)).update(counter).digest();
  return ((digest.readUInt32BE(digest[19] & 15) & 0x7fffffff) % 1000000).toString().padStart(6, '0');
}
(async () => {
  let browser;
  let created = false;
  try {
    const workspace = shell(`import json,sys
from apps.tenants.models import User,Workspace
from apps.platform_ops.models import PlatformRole
from apps.platform_ops.security import record
p=json.load(sys.stdin)
u=User.objects.create_user(username=p['username'],email=p['username']+'@example.invalid',password=p['password'],is_staff=True)
PlatformRole.objects.create(user=u,role='owner')
w=Workspace.objects.create(name=p['username'])
record('browser-test','staff.test_provisioned',target=str(u.pk))
print(w.pk)`);
    created = true;
    stage = 'browser launch';
    browser = await chromium.launch({ headless: true, args: ['--host-resolver-rules=MAP ops.localhost 127.0.0.1'] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('response', response => { if (response.url().endsWith('/ops/login/') && response.request().method() === 'POST') console.log('Login POST HTTP status:', response.status()); });
    stage = 'login';
    const initial = await page.goto('http://ops.localhost:8000/ops/login/');
    console.log('Console login HTTP status:', initial.status());
    stage = 'password entry';
    await page.getByLabel('Username', { exact: true }).fill(account.username);
    await page.getByLabel('Password', { exact: true }).fill(account.password);
    await page.getByRole('button', { name: 'Continue to two-factor verification' }).click();
    stage = 'password verification redirect';
    console.log('Login result path:', new URL(page.url()).pathname, 'heading:', (await page.locator('h1').allTextContents()).join(' ').slice(0, 100));
    const notice = await page.getByRole('alert').allTextContents();
    if (notice.length) console.log('Login notice:', notice.join(' ').slice(0, 200));
    await page.waitForURL('**/ops/mfa/');
    stage = 'MFA';
    const secret = (await page.locator('code').innerText()).trim();
    await page.getByLabel('Authenticator code').fill(totp(secret));
    await page.getByRole('button', { name: 'Verify', exact: true }).click();
    await page.waitForURL('**/ops/');
    stage = 'dashboard';
    await page.getByRole('heading', { name: 'Platform overview', exact: true }).waitFor();
    const controls = page.locator('form[action="/ops/control/"]');
    stage = 'tenant control';
    await controls.getByLabel('Workspace UUID', { exact: false }).fill(workspace);
    await controls.getByLabel('Control', { exact: true }).fill('ai');
    await controls.getByLabel('Reason', { exact: true }).fill('Browser acceptance test');
    await controls.getByRole('button', { name: 'Apply control' }).click();
    await page.getByText('Browser acceptance test', { exact: false }).first().waitFor();
    await page.getByLabel('Search by name').fill(account.username);
    stage = 'support';
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    const support = page.locator('form[action="/ops/support/"]');
    await support.getByLabel('Support reason').fill('Browser support acceptance');
    await support.getByRole('button', { name: 'View for 10 minutes' }).click();
    await page.locator('.banner').waitFor();
    await page.getByRole('button', { name: 'End support session' }).click();
    await page.waitForURL('**/ops/');
    mkdirSync(resolve(root, 'frontend/test-results'), { recursive: true });
    stage = 'screenshots and responsiveness';
    await page.screenshot({ path: resolve(root, 'frontend/test-results/platform-console-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: resolve(root, 'frontend/test-results/platform-console-mobile.png'), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    if (overflow) throw new Error('Console has page-level horizontal overflow on mobile.');
    const publicResponse = await page.request.get('http://localhost:8000/ops/');
    stage = 'host isolation and logout';
    if (publicResponse.status() !== 404) throw new Error('Console is exposed on the customer host.');
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await page.waitForURL('**/ops/login/');
    console.log('PASS: login, MFA enrollment, dashboard, tenant control, support start/end, host isolation, logout, desktop and mobile.');
  } finally {
    if (browser) await browser.close();
    if (created) shell(`import json,sys
from apps.tenants.models import User,Workspace
from apps.platform_ops.models import PlatformRole,Control
from apps.platform_ops.security import record
p=json.load(sys.stdin)
u=User.objects.get(username=p['username'])
PlatformRole.objects.filter(user=u).update(active=False)
u.is_active=False;u.set_unusable_password();u.save()
for w in Workspace.objects.filter(name=p['username']):
 Control.objects.filter(scope=str(w.pk)).delete()
 w.delete()
record('browser-test','staff.test_revoked',target=str(u.pk))`);
  }
})().catch((error) => { console.error(`Platform browser acceptance failed at ${stage} (${error.name}); disposable access was revoked.`); process.exitCode = 1; });
