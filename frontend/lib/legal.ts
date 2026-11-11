/**
 * Company details used by the privacy policy and terms of service.
 * Fill these in before launch; everything else in the documents is derived from what
 * Instantlify actually does. Have a lawyer review both documents for your jurisdiction.
 */
export const LEGAL = {
  /** Legal name of the company that operates Instantlify. */
  company: "Instantlify",
  /** Registered business address. */
  address: "[Registered business address]",
  /** Contact for privacy requests and data protection questions. */
  privacyEmail:
    process.env.INSTANTLIFY_PRIVACY_EMAIL || "support@instantlify.com",
  /** General support contact. */
  supportEmail:
    process.env.INSTANTLIFY_SUPPORT_EMAIL || "support@instantlify.com",
  /** Country or state whose law governs the terms, and where disputes are heard. */
  governingLaw: "[Country / state]",
  /** Date these versions take effect. */
  effectiveDate: "10 November 2026",
  /** Days after which message content is removed (backend RETENTION_DAYS). */
  retentionDays: 90,
};
