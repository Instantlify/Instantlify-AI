import { execFileSync } from "node:child_process";
import path from "node:path";

/**
 * Each run signs up a fresh `e2e-<timestamp>@example.com` account. Remove them so the
 * local platform console does not fill with "E2E Studio" workspaces that look like
 * customers. Only against the local Compose stack; set E2E_KEEP_DATA=1 to inspect
 * what a run left behind.
 */
export default function globalTeardown() {
  if (process.env.E2E_KEEP_DATA === "1" || process.env.E2E_BASE_URL) return;
  try {
    const output = execFileSync(
      "docker",
      [
        "compose",
        "exec",
        "-T",
        "backend",
        "python",
        "manage.py",
        "purge_e2e_accounts",
      ],
      { cwd: path.resolve(__dirname, "..", ".."), encoding: "utf8" },
    );
    console.log(`e2e cleanup: ${output.trim().replace(/\s+/g, " ")}`);
  } catch (error) {
    // Cleanup is a convenience; a failure here must not fail the suite.
    console.warn(
      `e2e cleanup skipped: ${(error as Error).message.split("\n")[0]}`,
    );
  }
}
