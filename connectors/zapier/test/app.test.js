"use strict";

const crypto = require("crypto");
const nock = require("nock");
const zapier = require("zapier-platform-core");
const App = require("../index");

const appTester = zapier.createAppTester(App);
zapier.tools.env.inject();

const BASE = "https://nemio.example.com";
const authData = { base_url: `${BASE}/`, api_key: "nmk_test" };

const signed = (secret, body, at = Math.floor(Date.now() / 1000)) => {
  const digest = crypto
    .createHmac("sha256", secret)
    .update(`${at}.${body}`)
    .digest("hex");
  return `t=${at},v1=${digest}`;
};

afterEach(() => nock.cleanAll());

describe("authentication", () => {
  it("sends the API key and labels the connection", async () => {
    nock(BASE, { reqheaders: { "x-api-key": "nmk_test" } })
      .get("/api/v1/me/")
      .reply(200, { workspace: { id: "w", name: "Acme" } });
    const result = await appTester(App.authentication.test, { authData });
    expect(result.workspace.name).toBe("Acme");
  });
});

describe("hook triggers", () => {
  const trigger = App.triggers.lead_hot;

  it("subscribes to the right event and unsubscribes by id", async () => {
    nock(BASE)
      .post("/api/v1/webhooks/", { url: "https://hooks.zapier.com/x", events: ["lead.hot"] })
      .reply(201, { id: "sub-1", secret: "whsec_abc" });
    const subscribed = await appTester(trigger.operation.performSubscribe, {
      authData,
      targetUrl: "https://hooks.zapier.com/x",
    });
    expect(subscribed).toEqual({ id: "sub-1", secret: "whsec_abc" });
    nock(BASE).delete("/api/v1/webhooks/sub-1/").reply(204);
    await appTester(trigger.operation.performUnsubscribe, {
      authData,
      subscribeData: subscribed,
    });
  });

  it("accepts a correctly signed delivery and flattens the payload", async () => {
    const body = JSON.stringify({
      event: "lead.hot",
      workspace_id: "w",
      occurred_at: "2026-01-01T00:00:00+00:00",
      data: { id: "lead-1", name: "Jo" },
    });
    const results = await appTester(trigger.operation.perform, {
      authData,
      subscribeData: { id: "sub-1", secret: "whsec_abc" },
      cleanedRequest: JSON.parse(body),
      rawRequest: {
        content: body,
        headers: {
          "Http-X-Nemio-Signature": signed("whsec_abc", body),
          "Http-X-Nemio-Delivery": "delivery-9",
        },
      },
    });
    expect(results).toEqual([
      {
        id: "delivery-9",
        resource_id: "lead-1",
        event: "lead.hot",
        occurred_at: "2026-01-01T00:00:00+00:00",
        workspace_id: "w",
        name: "Jo",
      },
    ]);
  });

  it("rejects bad or stale signatures", async () => {
    const body = JSON.stringify({ event: "lead.hot", data: { id: "x" } });
    const base = {
      authData,
      subscribeData: { id: "sub-1", secret: "whsec_abc" },
      cleanedRequest: JSON.parse(body),
    };
    await expect(
      appTester(trigger.operation.perform, {
        ...base,
        rawRequest: {
          content: body,
          headers: { "Http-X-Nemio-Signature": signed("wrong", body) },
        },
      }),
    ).rejects.toThrow(/Invalid webhook signature/);
    await expect(
      appTester(trigger.operation.perform, {
        ...base,
        rawRequest: {
          content: body,
          headers: {
            "Http-X-Nemio-Signature": signed(
              "whsec_abc",
              body,
              Math.floor(Date.now() / 1000) - 3600,
            ),
          },
        },
      }),
    ).rejects.toThrow(/Stale webhook signature/);
    await expect(
      appTester(trigger.operation.perform, { ...base, rawRequest: { content: body, headers: {} } }),
    ).rejects.toThrow(/Missing webhook signature/);
  });

  it("ignores deliveries for other events on the same hook", async () => {
    const body = JSON.stringify({ event: "lead.created", data: { id: "x" } });
    const results = await appTester(trigger.operation.perform, {
      authData,
      subscribeData: { id: "sub-1", secret: "whsec_abc" },
      cleanedRequest: JSON.parse(body),
      rawRequest: {
        content: body,
        headers: { "Http-X-Nemio-Signature": signed("whsec_abc", body) },
      },
    });
    expect(results).toEqual([]);
  });

  it("loads samples for the Zap editor", async () => {
    nock(BASE)
      .get("/api/v1/webhooks/sample/lead.hot/")
      .reply(200, [{ event: "lead.hot", workspace_id: "w", data: { id: "lead-1", stage: "new" } }]);
    const results = await appTester(trigger.operation.performList, { authData });
    expect(results[0]).toMatchObject({ resource_id: "lead-1", event: "lead.hot", stage: "new" });
  });

  it("defines one trigger per Nemio event", () => {
    expect(Object.keys(App.triggers).sort()).toEqual([
      "call_booked",
      "conversation_handoff",
      "lead_created",
      "lead_hot",
      "lead_updated",
      "message_received",
      "message_sent",
      "payment_paid",
    ]);
  });
});

describe("actions", () => {
  it("sends a message with a fresh idempotency key", async () => {
    nock(BASE)
      .post("/api/v1/conversations/c-1/messages/", (body) => {
        expect(body.text).toBe("Hi there");
        expect(body.idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
        return true;
      })
      .reply(202, { delivery_id: "d-1", status: "queued" });
    const result = await appTester(App.creates.send_message.operation.perform, {
      authData,
      inputData: { conversation_id: "c-1", text: "Hi there" },
    });
    expect(result).toEqual({ delivery_id: "d-1", status: "queued" });
  });

  it("patches only the lead fields that were supplied", async () => {
    nock(BASE)
      .patch("/api/v1/leads/l-1/", { stage: "won", tags: ["vip"] })
      .reply(200, { id: "l-1", stage: "won", tags: ["vip"] });
    const result = await appTester(App.creates.update_lead.operation.perform, {
      authData,
      inputData: { lead_id: "l-1", stage: "won", tags: ["vip"], name: "" },
    });
    expect(result.stage).toBe("won");
  });

  it("finds a lead by email", async () => {
    nock(BASE)
      .get("/api/v1/leads/")
      .query({ email: "jo@example.com", limit: 1 })
      .reply(200, { results: [{ id: "l-1", email: "jo@example.com" }], next_cursor: null });
    const results = await appTester(App.searches.find_lead.operation.perform, {
      authData,
      inputData: { email: "jo@example.com" },
    });
    expect(results).toEqual([{ id: "l-1", email: "jo@example.com" }]);
  });
});
