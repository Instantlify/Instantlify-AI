import { createHmac, timingSafeEqual } from "crypto";
import type {
  IDataObject,
  IHookFunctions,
  INodeType,
  INodeTypeDescription,
  IWebhookFunctions,
  IWebhookResponseData,
} from "n8n-workflow";

const EVENTS = [
  "lead.created",
  "lead.updated",
  "lead.hot",
  "message.received",
  "message.sent",
  "conversation.handoff",
  "call.booked",
  "payment.paid",
];

const TOLERANCE_SECONDS = 300;

/** `t=<unix>,v1=<hex>` where v1 = HMAC-SHA256(secret, "<t>." + raw body). */
export function verifySignature(secret: string, header: string, rawBody: string): boolean {
  const parts: Record<string, string> = {};
  for (const piece of header.split(",")) {
    const [key, value] = piece.split("=", 2);
    if (key && value) parts[key.trim()] = value.trim();
  }
  const timestamp = Number(parts.t);
  if (!Number.isFinite(timestamp) || !parts.v1) return false;
  if (Math.abs(Date.now() / 1000 - timestamp) > TOLERANCE_SECONDS) return false;
  const expected = createHmac("sha256", secret).update(`${timestamp}.${rawBody}`).digest("hex");
  const given = Buffer.from(parts.v1, "utf8");
  const wanted = Buffer.from(expected, "utf8");
  return given.length === wanted.length && timingSafeEqual(given, wanted);
}

export class InstantlifyTrigger implements INodeType {
  description: INodeTypeDescription = {
    displayName: "Instantlify Trigger",
    name: "instantlifyTrigger",
    icon: "file:instantlify.svg",
    group: ["trigger"],
    version: 1,
    subtitle: '={{$parameter["events"].join(", ")}}',
    description: "Starts the workflow when Instantlify emits a signed webhook event",
    defaults: { name: "Instantlify Trigger" },
    inputs: [],
    outputs: ["main"],
    credentials: [{ name: "instantlifyApi", required: true }],
    webhooks: [
      {
        name: "default",
        httpMethod: "POST",
        responseMode: "onReceived",
        path: "webhook",
      },
    ],
    properties: [
      {
        displayName: "Events",
        name: "events",
        type: "multiOptions",
        options: EVENTS.map((event) => ({ name: event, value: event })),
        default: ["lead.hot"],
        required: true,
        description: "Instantlify events that trigger this workflow",
      },
    ],
  };

  webhookMethods = {
    default: {
      async checkExists(this: IHookFunctions): Promise<boolean> {
        const webhookUrl = this.getNodeWebhookUrl("default");
        const staticData = this.getWorkflowStaticData("node");
        const credentials = await this.getCredentials("instantlifyApi");
        const baseURL = String(credentials.baseUrl).replace(/\/+$/, "");
        const existing = (await this.helpers.httpRequestWithAuthentication.call(
          this,
          "instantlifyApi",
          { method: "GET", url: `${baseURL}/api/v1/webhooks/`, json: true },
        )) as IDataObject[];
        const match = existing.find((item) => item.url === webhookUrl && item.active);
        if (match && staticData.webhookId === match.id && staticData.secret) {
          return true;
        }
        // A subscription we no longer hold the secret for cannot be verified; recreate it.
        return false;
      },
      async create(this: IHookFunctions): Promise<boolean> {
        const webhookUrl = this.getNodeWebhookUrl("default");
        const events = this.getNodeParameter("events") as string[];
        const staticData = this.getWorkflowStaticData("node");
        const credentials = await this.getCredentials("instantlifyApi");
        const baseURL = String(credentials.baseUrl).replace(/\/+$/, "");
        const created = (await this.helpers.httpRequestWithAuthentication.call(
          this,
          "instantlifyApi",
          {
            method: "POST",
            url: `${baseURL}/api/v1/webhooks/`,
            body: { url: webhookUrl, events },
            json: true,
          },
        )) as IDataObject;
        staticData.webhookId = created.id;
        staticData.secret = created.secret;
        return true;
      },
      async delete(this: IHookFunctions): Promise<boolean> {
        const staticData = this.getWorkflowStaticData("node");
        if (!staticData.webhookId) return true;
        const credentials = await this.getCredentials("instantlifyApi");
        const baseURL = String(credentials.baseUrl).replace(/\/+$/, "");
        try {
          await this.helpers.httpRequestWithAuthentication.call(this, "instantlifyApi", {
            method: "DELETE",
            url: `${baseURL}/api/v1/webhooks/${staticData.webhookId}/`,
            json: true,
          });
        } catch {
          // Already gone (revoked key, deleted in the app): nothing to clean up.
        }
        delete staticData.webhookId;
        delete staticData.secret;
        return true;
      },
    },
  };

  async webhook(this: IWebhookFunctions): Promise<IWebhookResponseData> {
    const req = this.getRequestObject();
    const res = this.getResponseObject();
    const staticData = this.getWorkflowStaticData("node");
    const secret = String(staticData.secret ?? "");
    const signature = String(req.headers["x-instantlify-signature"] ?? "");
    const raw = (req as unknown as { rawBody?: Buffer }).rawBody;
    const rawBody = raw ? raw.toString("utf8") : JSON.stringify(req.body);
    if (!secret || !signature || !verifySignature(secret, signature, rawBody)) {
      res.status(401).send("invalid signature");
      return { noWebhookResponse: true };
    }
    const envelope = req.body as IDataObject;
    const events = this.getNodeParameter("events") as string[];
    if (!events.includes(String(envelope.event))) {
      return { workflowData: [[]] };
    }
    return {
      workflowData: [
        this.helpers.returnJsonArray({
          delivery_id: req.headers["x-instantlify-delivery"],
          event: envelope.event,
          occurred_at: envelope.occurred_at,
          workspace_id: envelope.workspace_id,
          ...((envelope.data as IDataObject) ?? {}),
        }),
      ],
    };
  }
}
