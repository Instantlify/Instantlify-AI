import { randomUUID } from "crypto";
import type {
  IDataObject,
  IExecuteFunctions,
  IHttpRequestMethods,
  INodeExecutionData,
  INodeType,
  INodeTypeDescription,
} from "n8n-workflow";
import { NodeOperationError } from "n8n-workflow";

const STAGES = ["new", "qualified", "pitched", "booked", "won", "lost"];

export class Nemio implements INodeType {
  description: INodeTypeDescription = {
    displayName: "Nemio",
    name: "nemio",
    icon: "file:nemio.svg",
    group: ["transform"],
    version: 1,
    subtitle: '={{$parameter["operation"] + ": " + $parameter["resource"]}}',
    description: "Read and update leads, list conversations and send replies in Nemio",
    defaults: { name: "Nemio" },
    inputs: ["main"],
    outputs: ["main"],
    credentials: [{ name: "nemioApi", required: true }],
    properties: [
      {
        displayName: "Resource",
        name: "resource",
        type: "options",
        noDataExpression: true,
        options: [
          { name: "Lead", value: "lead" },
          { name: "Conversation", value: "conversation" },
          { name: "Message", value: "message" },
        ],
        default: "lead",
      },
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: { show: { resource: ["lead"] } },
        options: [
          { name: "Get", value: "get", action: "Get a lead" },
          { name: "Get Many", value: "getAll", action: "List leads" },
          { name: "Update", value: "update", action: "Update a lead" },
        ],
        default: "get",
      },
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: { show: { resource: ["conversation"] } },
        options: [{ name: "Get Many", value: "getAll", action: "List conversations" }],
        default: "getAll",
      },
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: { show: { resource: ["message"] } },
        options: [
          { name: "Get Many", value: "getAll", action: "List messages in a conversation" },
          { name: "Send", value: "send", action: "Send a message" },
        ],
        default: "send",
      },
      {
        displayName: "Lead ID",
        name: "leadId",
        type: "string",
        default: "",
        required: true,
        displayOptions: { show: { resource: ["lead"], operation: ["get", "update"] } },
      },
      {
        displayName: "Conversation ID",
        name: "conversationId",
        type: "string",
        default: "",
        required: true,
        displayOptions: { show: { resource: ["message"] } },
      },
      {
        displayName: "Text",
        name: "text",
        type: "string",
        typeOptions: { rows: 3 },
        default: "",
        required: true,
        displayOptions: { show: { resource: ["message"], operation: ["send"] } },
        description:
          "Queued through Nemio's delivery pipeline; opt-out and messaging-window rules apply",
      },
      {
        displayName: "Update Fields",
        name: "updateFields",
        type: "collection",
        placeholder: "Add Field",
        default: {},
        displayOptions: { show: { resource: ["lead"], operation: ["update"] } },
        options: [
          { displayName: "Name", name: "name", type: "string", default: "" },
          { displayName: "Email", name: "email", type: "string", default: "" },
          {
            displayName: "Stage",
            name: "stage",
            type: "options",
            options: STAGES.map((stage) => ({ name: stage, value: stage })),
            default: "new",
          },
          {
            displayName: "Tags",
            name: "tags",
            type: "string",
            default: "",
            description: "Comma-separated; replaces the lead's tags",
          },
          {
            displayName: "Custom Fields (JSON)",
            name: "fields",
            type: "json",
            default: "{}",
            description: "Merged into the lead's custom fields",
          },
          { displayName: "Opted Out", name: "opted_out", type: "boolean", default: false },
        ],
      },
      {
        displayName: "Filters",
        name: "filters",
        type: "collection",
        placeholder: "Add Filter",
        default: {},
        displayOptions: { show: { operation: ["getAll"], resource: ["lead", "conversation"] } },
        options: [
          {
            displayName: "Stage",
            name: "stage",
            type: "options",
            options: STAGES.map((stage) => ({ name: stage, value: stage })),
            default: "new",
          },
          { displayName: "Tag", name: "tag", type: "string", default: "" },
          { displayName: "Email", name: "email", type: "string", default: "" },
          { displayName: "Lead ID", name: "lead", type: "string", default: "" },
          {
            displayName: "Status",
            name: "status",
            type: "options",
            options: [
              { name: "Open", value: "open" },
              { name: "Closed", value: "closed" },
              { name: "Needs Human", value: "needs_human" },
            ],
            default: "open",
          },
        ],
      },
      {
        displayName: "Limit",
        name: "limit",
        type: "number",
        typeOptions: { minValue: 1, maxValue: 200 },
        default: 50,
        displayOptions: { show: { operation: ["getAll"] } },
      },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const results: INodeExecutionData[] = [];
    const credentials = await this.getCredentials("nemioApi");
    const baseURL = String(credentials.baseUrl).replace(/\/+$/, "");

    const request = async (
      method: IHttpRequestMethods,
      path: string,
      body?: IDataObject,
      qs?: IDataObject,
    ) =>
      (await this.helpers.httpRequestWithAuthentication.call(this, "nemioApi", {
        method,
        url: `${baseURL}${path}`,
        body,
        qs,
        json: true,
      })) as IDataObject;

    for (let i = 0; i < items.length; i += 1) {
      const resource = this.getNodeParameter("resource", i) as string;
      const operation = this.getNodeParameter("operation", i) as string;
      try {
        let output: IDataObject | IDataObject[];
        if (resource === "lead" && operation === "get") {
          output = await request("GET", `/api/v1/leads/${this.getNodeParameter("leadId", i)}/`);
        } else if (resource === "lead" && operation === "update") {
          const fields = this.getNodeParameter("updateFields", i) as IDataObject;
          const body: IDataObject = {};
          for (const key of ["name", "email", "stage", "opted_out"]) {
            if (fields[key] !== undefined && fields[key] !== "") body[key] = fields[key];
          }
          if (typeof fields.tags === "string" && fields.tags !== "") {
            body.tags = fields.tags
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean);
          }
          if (fields.fields !== undefined && fields.fields !== "") {
            body.fields =
              typeof fields.fields === "string"
                ? (JSON.parse(fields.fields) as IDataObject)
                : (fields.fields as IDataObject);
          }
          output = await request(
            "PATCH",
            `/api/v1/leads/${this.getNodeParameter("leadId", i)}/`,
            body,
          );
        } else if (operation === "getAll") {
          const filters = this.getNodeParameter("filters", i, {}) as IDataObject;
          const qs: IDataObject = { limit: this.getNodeParameter("limit", i) };
          for (const [key, value] of Object.entries(filters)) {
            if (value !== undefined && value !== "") qs[key] = value;
          }
          const path =
            resource === "lead"
              ? "/api/v1/leads/"
              : resource === "conversation"
                ? "/api/v1/conversations/"
                : `/api/v1/conversations/${this.getNodeParameter("conversationId", i)}/messages/`;
          const page = await request("GET", path, undefined, qs);
          output = (page.results as IDataObject[]) ?? [];
        } else if (resource === "message" && operation === "send") {
          output = await request(
            "POST",
            `/api/v1/conversations/${this.getNodeParameter("conversationId", i)}/messages/`,
            { text: this.getNodeParameter("text", i), idempotency_key: randomUUID() },
          );
        } else {
          throw new NodeOperationError(
            this.getNode(),
            `Unsupported operation ${resource}.${operation}`,
            { itemIndex: i },
          );
        }
        const rows = Array.isArray(output) ? output : [output];
        results.push(
          ...rows.map((json) => ({ json, pairedItem: { item: i } }) as INodeExecutionData),
        );
      } catch (error) {
        if (this.continueOnFail()) {
          results.push({
            json: { error: (error as Error).message },
            pairedItem: { item: i },
          });
          continue;
        }
        throw error;
      }
    }
    return [results];
  }
}
