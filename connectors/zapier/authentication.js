"use strict";

/** Custom auth: a workspace API key from Integrations → API keys, sent as X-API-Key. */

const trimSlash = (value) => String(value || "").replace(/\/+$/, "");

const addApiKey = (request, z, bundle) => {
  if (bundle.authData && bundle.authData.api_key) {
    request.headers = request.headers || {};
    request.headers["X-API-Key"] = bundle.authData.api_key;
  }
  return request;
};

const test = (z, bundle) =>
  z
    .request({ url: `${trimSlash(bundle.authData.base_url)}/api/v1/me/` })
    .then((response) => response.data);

module.exports = {
  authentication: {
    type: "custom",
    fields: [
      {
        key: "base_url",
        label: "Nemio URL",
        required: true,
        helpText:
          "The address of your Nemio app, for example `https://app.example.com` (no trailing slash).",
      },
      {
        key: "api_key",
        label: "API key",
        required: true,
        type: "password",
        helpText:
          "Create one under **Integrations → API keys**. Triggers need the `write` scope so Zapier can subscribe to webhooks.",
      },
    ],
    test,
    connectionLabel: "{{workspace.name}}",
  },
  addApiKey,
  trimSlash,
};
