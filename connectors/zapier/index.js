"use strict";

const { version: platformVersion } = require("zapier-platform-core");
const { version } = require("./package.json");
const { authentication, addApiKey } = require("./authentication");
const { triggers } = require("./triggers");
const { creates, searches } = require("./actions");

module.exports = {
  version,
  platformVersion,
  authentication,
  beforeRequest: [addApiKey],
  triggers,
  creates,
  searches,
};
