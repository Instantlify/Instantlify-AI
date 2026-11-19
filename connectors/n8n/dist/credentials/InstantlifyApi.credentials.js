"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.InstantlifyApi = void 0;
class InstantlifyApi {
    constructor() {
        this.name = "instantlifyApi";
        this.displayName = "Instantlify API";
        this.documentationUrl = "https://github.com/instantlify/instantlify/blob/main/docs/PUBLIC_API.md";
        this.properties = [
            {
                displayName: "Base URL",
                name: "baseUrl",
                type: "string",
                default: "",
                placeholder: "https://app.example.com",
                description: "Address of your Instantlify deployment, without a trailing slash",
                required: true,
            },
            {
                displayName: "API Key",
                name: "apiKey",
                type: "string",
                typeOptions: { password: true },
                default: "",
                description: "Workspace API key from Integrations → API keys. The trigger needs the write scope.",
                required: true,
            },
        ];
        this.authenticate = {
            type: "generic",
            properties: {
                headers: {
                    "X-API-Key": "={{$credentials.apiKey}}",
                },
            },
        };
        this.test = {
            request: {
                baseURL: "={{$credentials.baseUrl.replace(/\\/+$/, \"\")}}",
                url: "/api/v1/me/",
            },
        };
    }
}
exports.InstantlifyApi = InstantlifyApi;
