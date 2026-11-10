"use strict";

const crypto = require("crypto");
const { trimSlash } = require("./authentication");

const TOLERANCE_SECONDS = 300;

/** Every outbound webhook event Instantlify emits, with Zapier-facing labels. */
const EVENTS = [
  ["lead.created", "New Lead", "Triggers when a new lead is created."],
  ["lead.updated", "Updated Lead", "Triggers when a lead's details change."],
  ["lead.hot", "Hot Lead", "Triggers when a lead is classified as hot."],
  ["message.received", "New Inbound Message", "Triggers when a customer sends any inbound message."],
  ["message.sent", "Message Sent", "Triggers when a reply is delivered."],
  [
    "conversation.handoff",
    "Human Handoff Requested",
    "Triggers when a conversation needs a human.",
  ],
  ["call.booked", "Call Booked", "Triggers when the agent books a call."],
  ["payment.paid", "Payment Received", "Triggers when an in-chat payment is paid."],
];

/** Zapier prefixes raw request headers (e.g. `Http-X-Nemio-Signature`); match loosely. */
const header = (bundle, name) => {
  const headers = (bundle.rawRequest && bundle.rawRequest.headers) || {};
  const wanted = name.toLowerCase();
  for (const key of Object.keys(headers)) {
    const normalized = key.toLowerCase().replace(/^http-/, "");
    if (normalized === wanted) return headers[key];
  }
  return undefined;
};

/** Verify `t=<unix>,v1=<hmac>` over `<t>.<raw body>` with the subscription secret. */
const verifySignature = (z, bundle) => {
  const secret = bundle.subscribeData && bundle.subscribeData.secret;
  const raw = bundle.rawRequest && bundle.rawRequest.content;
  const signature = header(bundle, "x-nemio-signature");
  if (!secret || typeof raw !== "string" || !signature) {
    throw new z.errors.Error("Missing webhook signature", "SignatureError", 400);
  }
  const parts = Object.fromEntries(
    signature.split(",").map((piece) => piece.split("=", 2)),
  );
  const timestamp = Number(parts.t);
  if (!Number.isFinite(timestamp) || !parts.v1) {
    throw new z.errors.Error("Malformed webhook signature", "SignatureError", 400);
  }
  if (Math.abs(Date.now() / 1000 - timestamp) > TOLERANCE_SECONDS) {
    throw new z.errors.Error("Stale webhook signature", "SignatureError", 400);
  }
  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${timestamp}.${raw}`)
    .digest("hex");
  const given = Buffer.from(String(parts.v1), "utf8");
  const wanted = Buffer.from(expected, "utf8");
  if (given.length !== wanted.length || !crypto.timingSafeEqual(given, wanted)) {
    throw new z.errors.Error("Invalid webhook signature", "SignatureError", 400);
  }
};

/** Zapier needs a unique `id` per delivery; the record's own id stays as `resource_id`. */
const flatten = (envelope, deliveryId) => {
  const data = envelope.data || {};
  return {
    ...data,
    resource_id: data.id,
    id: deliveryId || `${envelope.event}:${data.id}:${envelope.occurred_at}`,
    event: envelope.event,
    occurred_at: envelope.occurred_at,
    workspace_id: envelope.workspace_id,
  };
};

const makeTrigger = ([event, label, description]) => ({
  key: event.replace(".", "_"),
  noun: label.replace(/^(New|Updated|Hot) /, "") || label,
  display: { label, description },
  operation: {
    type: "hook",
    performSubscribe: (z, bundle) =>
      z
        .request({
          method: "POST",
          url: `${trimSlash(bundle.authData.base_url)}/api/v1/webhooks/`,
          body: { url: bundle.targetUrl, events: [event] },
        })
        .then((response) => response.data),
    performUnsubscribe: (z, bundle) =>
      z
        .request({
          method: "DELETE",
          url: `${trimSlash(bundle.authData.base_url)}/api/v1/webhooks/${bundle.subscribeData.id}/`,
        })
        .then(() => ({})),
    perform: (z, bundle) => {
      verifySignature(z, bundle);
      const envelope = bundle.cleanedRequest;
      if (!envelope || envelope.event !== event) return [];
      return [flatten(envelope, header(bundle, "x-nemio-delivery"))];
    },
    performList: (z, bundle) =>
      z
        .request({
          url: `${trimSlash(bundle.authData.base_url)}/api/v1/webhooks/sample/${event}/`,
        })
        .then((response) => response.data.map((envelope) => flatten(envelope))),
    sample: {
      id: "3f6b0c1e-2b6c-4b1a-9d7f-1a2b3c4d5e6f",
      event,
      occurred_at: "2026-01-01T12:00:00+00:00",
      workspace_id: "0b9d2f5a-1111-4a2b-8c3d-4e5f6a7b8c9d",
      name: "Sample lead",
      stage: "new",
    },
  },
});

const triggers = Object.fromEntries(
  EVENTS.map((entry) => {
    const trigger = makeTrigger(entry);
    return [trigger.key, trigger];
  }),
);

module.exports = { triggers, verifySignature, EVENTS, header };
