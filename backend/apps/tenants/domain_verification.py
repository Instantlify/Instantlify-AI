import logging
import secrets
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.utils import timezone

from .models import WorkspaceBranding
from .services import audit

log = logging.getLogger(__name__)

PLATFORM_CNAME_TARGETS = {
    "domains.nemio.ai",
    "app.nemio.ai",
    getattr(settings, "APP_DOMAIN", "app.nemio.ai").lower(),
}


def generate_verification_token() -> str:
    """Returns a cryptographically secure hex challenge token for DNS TXT verification."""
    return secrets.token_hex(24)


def query_dns_records(domain: str, record_type: str = "TXT", timeout: float = 4.0) -> list[str]:
    """Query DNS records via Cloudflare DoH (DNS-over-HTTPS).
    Returns list of record string values, or empty list on network/lookup failure.
    """
    url = f"https://cloudflare-dns.com/dns-query?{urlencode({'name': domain, 'type': record_type})}"
    headers = {"Accept": "application/dns-json"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                answers = data.get("Answer", [])
                results = []
                for ans in answers:
                    val = str(ans.get("data", "")).strip(' "')
                    if val:
                        results.append(val)
                return results
    except Exception as exc:
        log.warning("DNS lookup failed for %s (%s): %s", domain, record_type, exc)
    return []


def verify_custom_domain(
    branding: WorkspaceBranding,
    *,
    user=None,
    resolver=None,
) -> tuple[bool, str]:
    """Verifies custom domain ownership for a WorkspaceBranding row.

    Verification succeeds if either:
    1. A TXT record at `_nemio-challenge.<custom_domain>` contains `nemio-verify=<token>` or `<token>`.
    2. A CNAME record at `<custom_domain>` resolves to one of the platform targets (`domains.nemio.ai`, etc.).

    Args:
        branding: The WorkspaceBranding instance to verify.
        user: Optional acting User for the audit log.
        resolver: Optional callable `resolver(name: str, rtype: str) -> list[str]` for testing.

    Returns:
        tuple[bool, str]: (is_verified, message)
    """
    domain = (branding.custom_domain or "").strip().lower()
    if not domain:
        return False, "No custom domain configured."

    token = branding.verification_token
    if not token:
        token = generate_verification_token()
        branding.verification_token = token
        branding.save(update_fields=["verification_token"])

    dns_query = resolver or query_dns_records

    # 1. Check TXT record at _nemio-challenge.<domain>
    challenge_host = f"_nemio-challenge.{domain}"
    txt_records = dns_query(challenge_host, "TXT")
    expected_full = f"nemio-verify={token}"
    txt_verified = any(
        record == expected_full or record == token or expected_full in record
        for record in txt_records
    )

    # 2. Check CNAME record at <domain>
    cname_records = [rec.rstrip(".").lower() for rec in dns_query(domain, "CNAME")]
    cname_verified = any(rec in PLATFORM_CNAME_TARGETS for rec in cname_records)

    if txt_verified or cname_verified:
        branding.custom_domain_status = WorkspaceBranding.DomainStatus.ACTIVE
        branding.verified_at = timezone.now()
        branding.tls_status = WorkspaceBranding.TLSStatus.ACTIVE
        branding.save(update_fields=["custom_domain_status", "verified_at", "tls_status"])

        audit(
            branding.workspace,
            user,
            "branding.domain_verified",
            str(branding.id),
            metadata={
                "domain": domain,
                "method": "txt" if txt_verified else "cname",
            },
        )
        return True, "Domain ownership verified successfully."

    branding.custom_domain_status = WorkspaceBranding.DomainStatus.FAILED
    branding.tls_status = WorkspaceBranding.TLSStatus.ERROR
    branding.save(update_fields=["custom_domain_status", "tls_status"])

    audit(
        branding.workspace,
        user,
        "branding.domain_verification_failed",
        str(branding.id),
        metadata={"domain": domain},
    )
    return False, (
        f"Verification failed. Set a TXT record at '{challenge_host}' with value "
        f"'{expected_full}' or a CNAME pointing to 'domains.nemio.ai'."
    )
