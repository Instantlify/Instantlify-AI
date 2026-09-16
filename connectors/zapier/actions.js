"use strict";

const crypto = require("crypto");
const { trimSlash } = require("./authentication");

const STAGES = ["new", "qualified", "pitched", "booked", "won", "lost"];

const sendMessage = {
  key: "send_message",
  noun: "Message",
  display: {
    label: "Send Message",
    description:
      "Queues a reply into a conversation through Nemio's normal delivery pipeline (opt-out and messaging-window rules apply).",
  },
  operation: {
    inputFields: [
      {
        key: "conversation_id",
        label: "Conversation ID",
        required: true,
        helpText: "From a Nemio trigger (`conversation_id`) or the inbox URL.",
      },
      { key: "text", label: "Text", required: true, type: "text" },
    ],
    perform: (z, bundle) =>
      z
        .request({
          method: "POST",
          url: `${trimSlash(bundle.authData.base_url)}/api/v1/conversations/${bundle.inputData.conversation_id}/messages/`,
          body: {
            text: bundle.inputData.text,
            idempotency_key: crypto.randomUUID(),
          },
        })
        .then((response) => response.data),
    sample: { delivery_id: "7d2f6c2a-0000-4a2b-8c3d-4e5f6a7b8c9d", status: "queued" },
  },
};

const updateLead = {
  key: "update_lead",
  noun: "Lead",
  display: {
    label: "Update Lead",
    description: "Updates a lead's name, email, stage, tags or custom fields.",
  },
  operation: {
    inputFields: [
      { key: "lead_id", label: "Lead ID", required: true },
      { key: "name", label: "Name" },
      { key: "email", label: "Email" },
      { key: "stage", label: "Stage", choices: STAGES },
      {
        key: "tags",
        label: "Tags",
        list: true,
        helpText: "Replaces the lead's tags.",
      },
      {
        key: "fields",
        label: "Custom fields",
        dict: true,
        helpText: "Merged into the lead's custom fields.",
      },
    ],
    perform: (z, bundle) => {
      const body = {};
      for (const key of ["name", "email", "stage", "tags", "fields"]) {
        if (bundle.inputData[key] !== undefined && bundle.inputData[key] !== "") {
          body[key] = bundle.inputData[key];
        }
      }
      return z
        .request({
          method: "PATCH",
          url: `${trimSlash(bundle.authData.base_url)}/api/v1/leads/${bundle.inputData.lead_id}/`,
          body,
        })
        .then((response) => response.data);
    },
    sample: {
      id: "3f6b0c1e-2b6c-4b1a-9d7f-1a2b3c4d5e6f",
      name: "Sample lead",
      email: "lead@example.com",
      stage: "qualified",
      tags: ["vip"],
      fields: {},
      opted_out: false,
    },
  },
};

const findLead = {
  key: "find_lead",
  noun: "Lead",
  display: {
    label: "Find Lead",
    description: "Finds a lead by email address.",
  },
  operation: {
    inputFields: [{ key: "email", label: "Email", required: true }],
    perform: (z, bundle) =>
      z
        .request({
          url: `${trimSlash(bundle.authData.base_url)}/api/v1/leads/`,
          params: { email: bundle.inputData.email, limit: 1 },
        })
        .then((response) => response.data.results),
    sample: updateLead.operation.sample,
  },
};

module.exports = {
  creates: { [sendMessage.key]: sendMessage, [updateLead.key]: updateLead },
  searches: { [findLead.key]: findLead },
};
