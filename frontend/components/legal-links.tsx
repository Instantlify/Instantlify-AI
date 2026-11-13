import Link from "next/link";
import { LEGAL } from "@/lib/legal";

export function LegalLinks() {
  return (
    <footer
      className="stack"
      style={{ borderTop: "1px solid var(--border)", paddingTop: 20 }}
    >
      <nav
        aria-label="Legal and contact links"
        className="row"
        style={{ flexWrap: "wrap", gap: 16 }}
      >
        <Link href="/">Instantlify home</Link>
        <Link href="/privacy/">Privacy policy</Link>
        <Link href="/terms/">Terms and conditions</Link>
        <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a>
        <a href={`tel:${LEGAL.supportPhoneHref}`}>{LEGAL.supportPhone}</a>
      </nav>
      <small>Instantlify is a product of {LEGAL.company}.</small>
    </footer>
  );
}
