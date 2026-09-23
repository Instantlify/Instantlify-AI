import Link from "next/link";

function policyUrl(value: string | undefined) {
  if (!value) return null;
  try {
    return new URL(value).protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

export function PublicHelpLinks() {
  const privacy = policyUrl(process.env.NEMIO_PRIVACY_URL);
  const terms = policyUrl(process.env.NEMIO_TERMS_URL);
  return (
    <>
      <Link href="/help">Help</Link>
      {privacy && <a href={privacy}>Privacy</a>}
      {terms && <a href={terms}>Terms</a>}
    </>
  );
}
