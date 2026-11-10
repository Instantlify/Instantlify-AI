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
  } catch {}
  if (!visitor) {
    visitor = "v-" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
    try {
      localStorage.setItem(storageKey, visitor);
    } catch {}
  }

  var config = {
    title: "Chat with us",
    greeting: "",
    color: "#347359",
    bot_enabled: true,
    position: "right",
    launcher_label: "Chat",
    logo_url: "",
    quick_replies: [],
  };
  // Visitor-facing text; the embed can force a language with data-lang="es".
  var STRINGS = {
    en: { open: "Open chat", close: "Close chat", placeholder: "Write a message", message: "Message", send: "Send", ai: "AI assistant and team", team: "Our team replies here" },
    es: { open: "Abrir chat", close: "Cerrar chat", placeholder: "Escribe un mensaje", message: "Mensaje", send: "Enviar", ai: "Asistente de IA y equipo", team: "Nuestro equipo responde aquí" },
    de: { open: "Chat öffnen", close: "Chat schließen", placeholder: "Nachricht schreiben", message: "Nachricht", send: "Senden", ai: "KI-Assistent und Team", team: "Unser Team antwortet hier" },
    fr: { open: "Ouvrir le chat", close: "Fermer le chat", placeholder: "Écrivez un message", message: "Message", send: "Envoyer", ai: "Assistant IA et équipe", team: "Notre équipe vous répond ici" },
    ru: { open: "Открыть чат", close: "Закрыть чат", placeholder: "Напишите сообщение", message: "Сообщение", send: "Отправить", ai: "ИИ-ассистент и команда", team: "Наша команда ответит здесь" },
    sr: { open: "Otvori čet", close: "Zatvori čet", placeholder: "Napišite poruku", message: "Poruka", send: "Pošalji", ai: "AI asistent i tim", team: "Naš tim odgovara ovde" },
  };
  var lang = (script.getAttribute("data-lang") || navigator.language || "en").slice(0, 2).toLowerCase();
  var text = STRINGS[lang] || STRINGS.en;
  var open = false;
  var seen = {};
  var timer = null;
  var messageCount = 0;

  var style = document.createElement("style");
  style.textContent =
    ".nemio-chat-button{position:fixed;bottom:20px;min-width:56px;height:56px;padding:0 18px;border-radius:28px;border:0;color:#fff;cursor:pointer;box-shadow:0 10px 30px rgba(0,0,0,.2);z-index:2147483000;font:600 14px system-ui,sans-serif}" +
    ".nemio-chat-panel{position:fixed;bottom:88px;width:340px;max-width:calc(100vw - 32px);height:480px;max-height:calc(100vh - 110px);display:none;flex-direction:column;border-radius:16px;overflow:hidden;background:#fff;box-shadow:0 20px 60px rgba(0,0,0,.25);z-index:2147483000;font:14px system-ui,sans-serif;color:#1f2937}" +
    ".nemio-chat-panel.open{display:flex}" +
    ".nemio-chat-head{padding:12px 16px;color:#fff;font-weight:700;display:flex;gap:10px;align-items:center}" +
    ".nemio-chat-head img{width:32px;height:32px;border-radius:50%;object-fit:cover;background:#fff}" +
    ".nemio-chat-head small{display:block;font-weight:400;opacity:.85;font-size:12px}" +
    ".nemio-chat-log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px;background:#f8fafc}" +
    ".nemio-chat-msg{max-width:80%;padding:9px 12px;border-radius:14px;line-height:1.4;white-space:pre-wrap;word-break:break-word}" +
    ".nemio-chat-msg.in{align-self:flex-end;color:#fff;border-bottom-right-radius:4px}" +
    ".nemio-chat-msg.out{align-self:flex-start;background:#e5e7eb;border-bottom-left-radius:4px}" +
    ".nemio-chat-actions{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start;max-width:90%}" +
    ".nemio-chat-actions button,.nemio-chat-actions a{padding:7px 12px;border-radius:999px;border:1px solid;background:#fff;font:inherit;font-size:13px;cursor:pointer;text-decoration:none}" +
    ".nemio-chat-form{display:flex;gap:8px;padding:10px;border-top:1px solid #e5e7eb}" +
    ".nemio-chat-form input{flex:1;padding:10px 12px;border:1px solid #d1d5db;border-radius:999px;font:inherit}" +
    ".nemio-chat-form button{padding:0 16px;border:0;border-radius:999px;color:#fff;font:inherit;font-weight:600;cursor:pointer}";
  document.head.appendChild(style);

  var button = document.createElement("button");
  button.className = "nemio-chat-button";
  button.type = "button";
  button.setAttribute("aria-label", text.open);
  button.textContent = config.launcher_label;
  var panel = document.createElement("div");
  panel.className = "nemio-chat-panel";
  panel.setAttribute("role", "dialog");
  panel.innerHTML =
    '<div class="nemio-chat-head"><img alt="" hidden><div><span></span><small></small></div></div>' +
    '<div class="nemio-chat-log" aria-live="polite"></div>' +
    '<form class="nemio-chat-form"><input type="text" maxlength="2000" placeholder="' + text.placeholder + '" aria-label="' + text.message + '" required><button type="submit">' + text.send + "</button></form>";
  document.body.appendChild(panel);
  document.body.appendChild(button);
  var head = panel.querySelector(".nemio-chat-head");
  var logo = head.querySelector("img");
  var log = panel.querySelector(".nemio-chat-log");
  var form = panel.querySelector("form");
  var input = form.querySelector("input");

  function actionRow(items) {
    var row = document.createElement("div");
    row.className = "nemio-chat-actions";
    items.forEach(function (item) {
      var el;
      if (item.url) {
        el = document.createElement("a");
        el.href = item.url;
        el.target = "_blank";
        el.rel = "noopener noreferrer";
      } else {
        el = document.createElement("button");
        el.type = "button";
        el.addEventListener("click", function () {
          send(item.payload || item.title);
        });
      }
      el.textContent = item.title;
      el.style.color = config.color;
      el.style.borderColor = config.color;
      row.appendChild(el);
    });
    return row;
  }

  function paint() {
    var side = config.position === "left" ? "left" : "right";
    var other = side === "left" ? "right" : "left";
    [button, panel].forEach(function (el) {
      el.style[side] = "20px";
      el.style[other] = "auto";
    });
    button.style.background = config.color;
    button.textContent = open ? "×" : config.launcher_label || "Chat";
    head.style.background = config.color;
    head.querySelector("span").textContent = config.title;
    head.querySelector("small").textContent = config.bot_enabled ? text.ai : text.team;
    if (config.logo_url && /^https:\/\//.test(config.logo_url)) {
      logo.src = config.logo_url;
      logo.hidden = false;
    } else {
      logo.hidden = true;
    }
    form.querySelector("button").style.background = config.color;
    if (config.greeting && !log.querySelector("[data-greeting]")) {
      var greeting = document.createElement("div");
      greeting.className = "nemio-chat-msg out";
      greeting.setAttribute("data-greeting", "1");
      greeting.textContent = config.greeting;
      log.insertBefore(greeting, log.firstChild);
    }
    var quick = log.querySelector("[data-quick]");
    var replies = (config.quick_replies || []).slice(0, 5);
    if (messageCount === 0 && replies.length && !quick) {
      var row = actionRow(
        replies.map(function (text) {
          return { title: text };
        }),
      );
      row.setAttribute("data-quick", "1");
      var anchor = log.querySelector("[data-greeting]");
      log.insertBefore(row, anchor ? anchor.nextSibling : log.firstChild);
    } else if (messageCount > 0 && quick) {
      quick.remove();
    }
  }

  function append(message) {
    if (seen[message.id]) return;
    seen[message.id] = true;
    messageCount += 1;
    var row = document.createElement("div");
    row.className = "nemio-chat-msg " + (message.direction === "inbound" ? "in" : "out");
    if (message.direction === "inbound") row.style.background = config.color;
    row.textContent = message.text;
    log.appendChild(row);
    if (message.direction !== "inbound" && message.buttons && message.buttons.length) {
      log.appendChild(actionRow(message.buttons));
    }
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
        (body.messages || []).forEach(append);
        paint();
      })
      .catch(function () {});
  }

  function send(text) {
    text = String(text || "").trim();
    if (!text) return Promise.resolve();
    return fetch(api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "omit",
      body: JSON.stringify({ visitor: visitor, text: text }),
    }).then(function (response) {
      if (!response.ok) throw new Error("send failed");
      return sync();
    });
  }

  button.addEventListener("click", function () {
    open = !open;
    panel.classList.toggle("open", open);
    button.setAttribute("aria-label", open ? text.close : text.open);
    paint();
    clearInterval(timer);
    if (open) {
      sync();
      input.focus();
      // Faster refresh while the visitor is looking at the conversation.
      timer = setInterval(sync, 2500);
    }
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    send(text).catch(function () {
      input.value = text;
    });
  });

  sync();
})();
