/* Nemio website chat widget. Embed with:
   <script src="https://<your nemio host>/widget.js" data-workspace="<workspace id>" async></script>
   Messages land in the workspace inbox; replies from the team or the AI agent show here. */
(function () {
  var script = document.currentScript;
  if (!script) return;
  var workspace = script.getAttribute("data-workspace");
  if (!workspace) return;
  var origin = new URL(script.src, location.href).origin;
  var api = origin + "/api/public/webchat/" + workspace + "/";
  var storageKey = "nemio:webchat:visitor";
  var visitor = "";
  try {
    visitor = localStorage.getItem(storageKey) || "";
  } catch (e) {}
  if (!visitor) {
    visitor = "v-" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
    try {
      localStorage.setItem(storageKey, visitor);
    } catch (e) {}
  }

  var config = { title: "Chat with us", greeting: "", color: "#347359", bot_enabled: true };
  var open = false;
  var seen = {};
  var timer = null;

  var style = document.createElement("style");
  style.textContent =
    ".nemio-chat-button{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;color:#fff;cursor:pointer;box-shadow:0 10px 30px rgba(0,0,0,.2);z-index:2147483000;font:600 14px system-ui,sans-serif}" +
    ".nemio-chat-panel{position:fixed;right:20px;bottom:88px;width:340px;max-width:calc(100vw - 32px);height:460px;max-height:calc(100vh - 110px);display:none;flex-direction:column;border-radius:16px;overflow:hidden;background:#fff;box-shadow:0 20px 60px rgba(0,0,0,.25);z-index:2147483000;font:14px system-ui,sans-serif;color:#1f2937}" +
    ".nemio-chat-panel.open{display:flex}" +
    ".nemio-chat-head{padding:14px 16px;color:#fff;font-weight:700}" +
    ".nemio-chat-head small{display:block;font-weight:400;opacity:.85;font-size:12px}" +
    ".nemio-chat-log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px;background:#f8fafc}" +
    ".nemio-chat-msg{max-width:80%;padding:9px 12px;border-radius:14px;line-height:1.4;white-space:pre-wrap;word-break:break-word}" +
    ".nemio-chat-msg.in{align-self:flex-end;color:#fff;border-bottom-right-radius:4px}" +
    ".nemio-chat-msg.out{align-self:flex-start;background:#e5e7eb;border-bottom-left-radius:4px}" +
    ".nemio-chat-form{display:flex;gap:8px;padding:10px;border-top:1px solid #e5e7eb}" +
    ".nemio-chat-form input{flex:1;padding:10px 12px;border:1px solid #d1d5db;border-radius:999px;font:inherit}" +
    ".nemio-chat-form button{padding:0 16px;border:0;border-radius:999px;color:#fff;font:inherit;font-weight:600;cursor:pointer}";
  document.head.appendChild(style);

  var button = document.createElement("button");
  button.className = "nemio-chat-button";
  button.type = "button";
  button.setAttribute("aria-label", "Open chat");
  button.textContent = "Chat";
  var panel = document.createElement("div");
  panel.className = "nemio-chat-panel";
  panel.setAttribute("role", "dialog");
  panel.innerHTML =
    '<div class="nemio-chat-head"><span></span><small></small></div>' +
    '<div class="nemio-chat-log" aria-live="polite"></div>' +
    '<form class="nemio-chat-form"><input type="text" maxlength="2000" placeholder="Write a message" aria-label="Message" required><button type="submit">Send</button></form>';
  document.body.appendChild(panel);
  document.body.appendChild(button);
  var head = panel.querySelector(".nemio-chat-head");
  var log = panel.querySelector(".nemio-chat-log");
  var form = panel.querySelector("form");
  var input = form.querySelector("input");

  function paint() {
    button.style.background = config.color;
    head.style.background = config.color;
    head.querySelector("span").textContent = config.title;
    head.querySelector("small").textContent = config.bot_enabled ? "AI assistant and team" : "Our team replies here";
    form.querySelector("button").style.background = config.color;
    if (config.greeting && !log.querySelector("[data-greeting]")) {
      var greeting = document.createElement("div");
      greeting.className = "nemio-chat-msg out";
      greeting.setAttribute("data-greeting", "1");
      greeting.textContent = config.greeting;
      log.insertBefore(greeting, log.firstChild);
    }
  }

  function append(message) {
    if (seen[message.id]) return;
    seen[message.id] = true;
    var row = document.createElement("div");
    row.className = "nemio-chat-msg " + (message.direction === "inbound" ? "in" : "out");
    if (message.direction === "inbound") row.style.background = config.color;
    row.textContent = message.text;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function sync() {
    return fetch(api + "?visitor=" + encodeURIComponent(visitor), { credentials: "omit" })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (body) {
        if (!body) return;
        config = body;
        paint();
        (body.messages || []).forEach(append);
      })
      .catch(function () {});
  }

  button.addEventListener("click", function () {
    open = !open;
    panel.classList.toggle("open", open);
    button.setAttribute("aria-label", open ? "Close chat" : "Open chat");
    if (open) {
      sync();
      input.focus();
      clearInterval(timer);
      timer = setInterval(sync, 4000);
    } else {
      clearInterval(timer);
    }
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    fetch(api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "omit",
      body: JSON.stringify({ visitor: visitor, text: text }),
    })
      .then(function (response) {
        if (!response.ok) throw new Error("send failed");
        return sync();
      })
      .catch(function () {
        input.value = text;
      });
  });

  sync();
})();
