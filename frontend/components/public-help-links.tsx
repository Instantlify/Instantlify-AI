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
  const privacy = policyUrl(process.env.INSTANTLIFY_PRIVACY_URL);
  const terms = policyUrl(process.env.INSTANTLIFY_TERMS_URL);
  return (
    <>
      <Link href="/help">Help</Link>
      {privacy ? (
        <a href={privacy}>Privacy</a>
      ) : (
        <Link href="/privacy/">Privacy</Link>
      )}
      {terms ? <a href={terms}>Terms</a> : <Link href="/terms/">Terms</Link>}
    </>
  );
}
