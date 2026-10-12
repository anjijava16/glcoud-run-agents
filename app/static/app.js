// Minimal chat client: no build step, no framework. Talks to the FastAPI routes
// under /api/v1 and reads Server-Sent Events from /api/v1/chat/stream.
(() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    messages: $("messages"), empty: $("empty"), input: $("input"), send: $("send"),
    composer: $("composer"), sessions: $("sessions"), customer: $("customer"),
    newChat: $("newChat"), title: $("chatTitle"), trace: $("showTrace"),
    sidebar: $("sidebar"), toggle: $("toggleSidebar"),
  };

  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  };

  let userId = store.get("userId", null);
  if (!userId) { userId = "web-" + Math.random().toString(36).slice(2, 10); store.set("userId", userId); }
  let sessionId = null;
  let busy = false;

  // ---------- API helper (handles optional X-API-Key) ----------
  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    const key = store.get("apiKey", "");
    if (key) headers["X-API-Key"] = key;
    const res = await fetch(path, { ...opts, headers });
    if (res.status === 401) {
      const k = prompt("This deployment needs an API key:");
      if (k) { store.set("apiKey", k); return api(path, opts); }
    }
    return res;
  }

  // ---------- tiny, safe markdown ----------
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function md(text) {
    const lines = esc(text).split("\n");
    let html = "", list = null;
    const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
    for (const raw of lines) {
      const line = raw.trimEnd();
      const ul = line.match(/^\s*[-*•]\s+(.*)/), ol = line.match(/^\s*\d+[.)]\s+(.*)/);
      const kind = ul ? "ul" : ol ? "ol" : null;
      if (kind) {
        if (list !== kind) { if (list) html += `</${list}>`; html += `<${kind}>`; list = kind; }
        html += `<li>${inline((ul || ol)[1])}</li>`;
        continue;
      }
      if (list) { html += `</${list}>`; list = null; }
      if (line.trim()) html += `<p>${inline(line.replace(/^#+\s*/, ""))}</p>`;
    }
    if (list) html += `</${list}>`;
    return html;
  }

  // ---------- rendering ----------
  function addMessage(role, text = "") {
    els.empty.style.display = "none";
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const trace = document.createElement("div");
    trace.className = "meta trace";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = md(text);
    if (role === "assistant") wrap.append(trace);
    wrap.append(bubble);
    els.messages.append(wrap);
    scroll();
    return { wrap, bubble, trace };
  }
  const scroll = () => (els.messages.scrollTop = els.messages.scrollHeight);
  const chip = (parent, text, cls = "") => {
    const c = document.createElement("span");
    c.className = `chip ${cls}`; c.textContent = text; parent.append(c); scroll(); return c;
  };
  function clearMessages() {
    els.messages.querySelectorAll(".msg").forEach((m) => m.remove());
    els.empty.style.display = "";
  }

  // ---------- sessions ----------
  async function loadSessions() {
    const res = await api(`/api/v1/sessions?user_id=${encodeURIComponent(userId)}`);
    if (!res.ok) return;
    const list = await res.json();
    els.sessions.innerHTML = "";
    for (const s of list) {
      const li = document.createElement("li");
      if (s.session_id === sessionId) li.className = "active";
      const open = document.createElement("button");
      open.className = "open"; open.textContent = s.title || "Untitled chat";
      open.onclick = () => openSession(s.session_id);
      const del = document.createElement("button");
      del.className = "del"; del.textContent = "✕"; del.title = "Delete";
      del.onclick = async () => {
        await api(`/api/v1/sessions/${s.session_id}?user_id=${encodeURIComponent(userId)}`, { method: "DELETE" });
        if (s.session_id === sessionId) newChat();
        loadSessions();
      };
      li.append(open, del);
      els.sessions.append(li);
    }
  }

  async function openSession(id) {
    const res = await api(`/api/v1/sessions/${id}?user_id=${encodeURIComponent(userId)}`);
    if (!res.ok) return;
    const s = await res.json();
    sessionId = s.session_id;
    clearMessages();
    els.title.textContent = s.title || "Conversation";
    if (s.state.customer_id) els.customer.value = s.state.customer_id;
    for (const m of s.messages) {
      const r = addMessage(m.role, m.text);
      if (m.role === "assistant") chip(r.trace, m.author, "agent");
    }
    els.sidebar.classList.remove("open");
    loadSessions();
  }

  function newChat() {
    sessionId = null;
    clearMessages();
    els.title.textContent = "New conversation";
    loadSessions();
    els.input.focus();
  }

  // ---------- sending + SSE parsing ----------
  async function send(text) {
    if (busy || !text.trim()) return;
    busy = true; els.send.disabled = true;
    addMessage("user", text);
    if (!sessionId) els.title.textContent = text.slice(0, 60);
    const out = addMessage("assistant");
    out.bubble.classList.add("typing");
    let buffer = "", streamed = "";

    try {
      const res = await api("/api/v1/chat/stream", {
        method: "POST",
        body: JSON.stringify({ message: text, user_id: userId, session_id: sessionId, customer_id: els.customer.value }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, idx); buffer = buffer.slice(idx + 2);
          const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          const evt = JSON.parse(dataLine.slice(6));
          switch (evt.type) {
            case "session": sessionId = evt.session_id; break;
            case "agent": chip(out.trace, evt.agent, "agent"); break;
            case "tool_call":
              if (evt.name === "transfer_to_agent") chip(out.trace, `→ ${evt.args.agent_name}`);
              else chip(out.trace, `⚙ ${evt.name}`);
              break;
            case "tool_result":
              if (evt.status && evt.status !== "success") chip(out.trace, `${evt.name}: ${evt.status}`, "fail");
              break;
            case "delta": streamed += evt.text; out.bubble.innerHTML = md(streamed); scroll(); break;
            case "final": streamed = evt.text; out.bubble.innerHTML = md(streamed); scroll(); break;
            case "error": out.bubble.classList.add("error"); out.bubble.textContent = evt.message; break;
            case "done": chip(out.trace, `${(evt.latency_ms / 1000).toFixed(1)}s`); break;
          }
        }
      }
      if (!streamed && !out.bubble.classList.contains("error")) out.bubble.textContent = "(no response)";
    } catch (err) {
      out.bubble.classList.add("error");
      out.bubble.textContent = `Couldn't reach the assistant (${err.message}).`;
    } finally {
      out.bubble.classList.remove("typing");
      busy = false; els.send.disabled = false;
      loadSessions();
    }
  }

  // ---------- wiring ----------
  els.composer.addEventListener("submit", (e) => {
    e.preventDefault();
    const t = els.input.value; els.input.value = ""; autosize(); send(t);
  });
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); els.composer.requestSubmit(); }
  });
  const autosize = () => { els.input.style.height = "auto"; els.input.style.height = els.input.scrollHeight + "px"; };
  els.input.addEventListener("input", autosize);
  document.querySelectorAll(".suggestions button").forEach((b) => (b.onclick = () => send(b.dataset.q)));
  els.newChat.onclick = newChat;
  els.customer.onchange = () => { store.set("customerId", els.customer.value); newChat(); };
  els.trace.onchange = () => els.messages.classList.toggle("hide-trace", !els.trace.checked);
  els.toggle.onclick = () => els.sidebar.classList.toggle("open");

  (async function init() {
    const res = await api("/api/v1/customers");
    const customers = res.ok ? await res.json() : [{ customer_id: "CUST-001", name: "Demo", tier: "standard" }];
    for (const c of customers) {
      const o = document.createElement("option");
      o.value = c.customer_id; o.textContent = `${c.name} (${c.tier})`;
      els.customer.append(o);
    }
    els.customer.value = store.get("customerId", customers[0].customer_id);
    loadSessions();
  })();
})();
