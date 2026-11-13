/** Public operator and contact details shared by legal pages and the footer. */
export const LEGAL = {
  /** Legal name of the company that operates Instantlify. */
  company: "SKY INNOVA SERVICES (PRIVATE) LIMITED",
  /** Registered business address. */
  address: "Flat No. 02, Block 1/B, Street 01, Sector I-8/1, Pakistan",
  /** Contact for privacy requests and data protection questions. */
  privacyEmail:
    process.env.INSTANTLIFY_PRIVACY_EMAIL || "support@instantlify.com",
  supportPhone: "+92 324 8686799",
  supportPhoneHref: "+923248686799",
  /** General support contact. */
  supportEmail:
    process.env.INSTANTLIFY_SUPPORT_EMAIL || "support@instantlify.com",
  /** Country or state whose law governs the terms, and where disputes are heard. */
  governingLaw: "Pakistan",
  /** Date these versions take effect. */
  effectiveDate: "13 November 2026",
  /** Days after which message content is removed (backend RETENTION_DAYS). */
  retentionDays: 90,
};
