import type {
  IAuthenticateGeneric,
  ICredentialTestRequest,
  ICredentialType,
  INodeProperties,
} from "n8n-workflow";

export class NemioApi implements ICredentialType {
  name = "nemioApi";

  displayName = "Nemio API";

  documentationUrl = "https://github.com/nemio/nemio/blob/main/docs/PUBLIC_API.md";

  properties: INodeProperties[] = [
    {
      displayName: "Base URL",
      name: "baseUrl",
      type: "string",
      default: "",
      placeholder: "https://app.example.com",
      description: "Address of your Nemio deployment, without a trailing slash",
      required: true,
    },
    {
      displayName: "API Key",
      name: "apiKey",
      type: "string",
      typeOptions: { password: true },
      default: "",
      description:
        "Workspace API key from Integrations → API keys. The trigger needs the write scope.",
      required: true,
    },
  ];

  authenticate: IAuthenticateGeneric = {
    type: "generic",
    properties: {
      headers: {
        "X-API-Key": "={{$credentials.apiKey}}",
      },
    },
  };

  test: ICredentialTestRequest = {
    request: {
      baseURL: "={{$credentials.baseUrl.replace(/\\/+$/, \"\")}}",
      url: "/api/v1/me/",
    },
  };
}
