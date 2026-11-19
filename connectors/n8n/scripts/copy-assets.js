// Copies node icons next to the compiled nodes so n8n can serve them.
const fs = require("fs");
const path = require("path");

const source = path.join(__dirname, "..", "nodes", "Instantlify", "instantlify.svg");
const target = path.join(__dirname, "..", "dist", "nodes", "Instantlify", "instantlify.svg");
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.copyFileSync(source, target);
