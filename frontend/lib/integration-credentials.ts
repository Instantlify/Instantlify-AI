/** Operational destinations are public options; tokens remain write-only credentials. */
export function integrationConfiguration(
  provider: string,
  values: Record<string, string>,
  existingOptions: Record<string, string> = {},
) {
  const optionFields: Record<string, string[]> = {
    google_calendar: ["calendar_id"],
    google_sheets: ["spreadsheet_id", "range"],
    calcom: ["event_type_id"],
    slack: ["channel_id"],
    elevenlabs: ["voice_id", "model"],
    inworld: ["voice_id", "model"],
    minimax: ["voice_id", "model"],
    vapi: ["agent_id", "phone_number_id"],
    retell: ["agent_id", "from_number"],
    heygen: ["avatar_id", "voice_id"],
    airtable: ["base_id", "table_id"],
    notion: ["database_id", "page_id"],
    shopify: ["shop_domain"],
    jotform: ["form_id", "email_question", "name_question", "region"],
    gohighlevel: ["location_id"],
    attio: [],
    stripe: [],
    gmail: ["sender_email"],
    outlook: [],
    mailerlite: ["group_id"],
    klaviyo: ["list_id"],
  };
  const aliases: Record<string, string> =
    provider === "slack"
      ? { bot_token: "access_token", default_channel: "channel_id" }
      : provider === "stripe"
        ? { api_key: "secret_key" }
        : {};
  const credentials: Record<string, string> = {};
  const options = { ...existingOptions };
  for (const [originalKey, raw] of Object.entries(values)) {
    const key = aliases[originalKey] || originalKey;
    if (["redirect_url", "client_id", "client_secret"].includes(key)) continue;
    const value = raw.trim();
    if ((optionFields[provider] || []).includes(key)) options[key] = value;
    else if (value) credentials[key] = value;
  }
  return { credentials, options };
}
