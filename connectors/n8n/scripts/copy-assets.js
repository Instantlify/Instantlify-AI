// Copies node icons next to the compiled nodes so n8n can serve them.
const fs = require("fs");
const path = require("path");

const source = path.join(__dirname, "..", "nodes", "Nemio", "nemio.svg");
const target = path.join(__dirname, "..", "dist", "nodes", "Nemio", "nemio.svg");
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.copyFileSync(source, target);
