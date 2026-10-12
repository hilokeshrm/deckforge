// DeckForge UI - vanilla JS single-page app
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const view = $("#view");
let timers = [];
const every = (fn, ms) => { fn(); timers.push(setInterval(fn, ms)); };

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const isJson = (r.headers.get("content-type") || "").includes("json");
  const data = isJson ? await r.json() : await r.text();
  if (!r.ok) throw new Error(data?.detail || data || r.statusText);
  return data;
}
function toast(msg, ms = 3200) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), ms);
}
const ago = ts => {
  if (!ts) return "";
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s ago`; if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`; return new Date(ts * 1000).toLocaleDateString();
};
const pad3 = v => String(v).padStart(3, "0");
const statusChip = s => `<span class="status ${esc(s)}">${esc(s)}</span>`;

// ---------- header status ----------
async function headerStatus() {
  try {
    const s = await api("/api/status");
    const el = $("#agentState");
    el.className = "agent-state " + (s.busy ? "busy" : "idle");
    el.querySelector("span").textContent = s.busy ? `working: ${s.current || "…"}` : "agent idle";
    const b = $("#qbadge"); b.hidden = !s.queued; b.textContent = s.queued;
  } catch { $("#agentState span").textContent = "offline"; }
}
setInterval(headerStatus, 3000); headerStatus();

// ---------- file drop helper ----------
function dropzone(el, list, onChange, accept = "") {
  const input = document.createElement("input");
  input.type = "file"; input.multiple = true; input.hidden = true; if (accept) input.accept = accept;
  el.after(input);
  const render = () => { onChange(list); };
  el.onclick = () => input.click();
  input.onchange = () => { list.push(...input.files); input.value = ""; render(); };
  el.ondragover = e => { e.preventDefault(); el.classList.add("over"); };
  el.ondragleave = () => el.classList.remove("over");
  el.ondrop = e => { e.preventDefault(); el.classList.remove("over"); list.push(...e.dataTransfer.files); render(); };
}
function fileChips(box, list, rerender) {
  box.innerHTML = list.map((f, i) => `<span class="chip">${esc(f.name)} <small class="meta">${(f.size / 1024).toFixed(0)} KB</small><button data-i="${i}" title="remove">✕</button></span>`).join("");
  $$("button", box).forEach(b => b.onclick = e => { e.stopPropagation(); list.splice(+b.dataset.i, 1); rerender(list); });
}
async function templateOptions(selected = "") {
  const ts = await api("/api/templates");
  return ts.map(t => `<option value="${esc(t.name)}" ${t.name === selected ? "selected" : ""}>${esc(t.name)}</option>`).join("");
}

// ---------- pages ----------
const pages = {};

pages.new = async () => {
  const files = [];
  view.innerHTML = `
  <h1>New presentation</h1>
  <p class="sub">Drop in documents, data, images or links. The agent reads everything, plans the story and builds an animated HTML deck in your brand.</p>
  <div class="grid cols-2">
    <div class="card">
      <div class="drop" id="drop"><strong>Drop files here</strong> or click to browse<br><small>PDF, Word, PowerPoint, Excel/CSV, text, Markdown, HTML, images, audio</small></div>
      <div class="files" id="files"></div>
      <label>Brief <span class="hint">what the deck should say, for whom, anything to emphasise</span></label>
      <textarea id="brief" placeholder="e.g. 10-slide board update on Q3 results. Lead with revenue growth, end with next quarter's priorities."></textarea>
      <label>Links <span class="hint">one URL per line (optional)</span></label>
      <textarea id="urls" style="min-height:60px" placeholder="https://…"></textarea>
    </div>
    <div class="card">
      <h2>Options</h2>
      <label>Brand template</label><select id="template">${await templateOptions()}</select>
      <div class="row">
        <div><label>Slides</label><input id="slides" type="number" min="3" max="40" value="10"></div>
        <div><label>Deck name <span class="hint">optional</span></label><input id="deck" type="text" placeholder="auto"></div>
      </div>
      <label>Audience</label><input id="audience" type="text" placeholder="e.g. board of directors">
      <label><input id="pptx" type="checkbox"> Also export PowerPoint (.pptx)</label>
      <label><input id="pdf" type="checkbox"> Also export PDF</label>
      <div class="actions"><button class="primary" id="go">Build deck ✨</button></div>
    </div>
  </div>`;
  const rerender = l => fileChips($("#files"), l, rerender);
  dropzone($("#drop"), files, rerender);
  $("#go").onclick = async () => {
    const fd = new FormData();
    fd.append("action", "create");
    ["template", "slides", "deck", "audience"].forEach(k => fd.append(k, $("#" + k).value));
    fd.append("instructions", $("#brief").value);
    fd.append("urls", $("#urls").value);
    fd.append("formats", [$("#pptx").checked && "pptx", $("#pdf").checked && "pdf"].filter(Boolean).join(","));
    files.forEach(f => fd.append("files", f));
    $("#go").disabled = true;
    try { const r = await api("/api/jobs", {method: "POST", body: fd}); location.hash = "#/job/" + r.id; }
    catch (e) { toast(e.message); $("#go").disabled = false; }
  };
};

pages.job = async (id) => {
  view.innerHTML = `<h1>Job</h1><p class="sub">${esc(id)}</p><div class="card" id="jobcard"><div class="progress-line"></div></div>`;
  every(async () => {
    let j; try { j = await api("/api/jobs/" + encodeURIComponent(id)); } catch { return; }
    const live = j.status === "running" || j.status === "queued";
    $("#jobcard").innerHTML = `
      ${live ? '<div class="progress-line"></div>' : ""}
      <div class="kv" style="margin-top:12px"><b>Status</b><span>${statusChip(j.status || "queued")}</span>
        <b>Action</b><span>${esc(j.action)}</span>${j.deck ? `<b>Deck</b><span>${esc(j.deck)} ${j.version ? "v" + pad3(j.version) : ""}</span>` : ""}</div>
      ${j.error ? `<pre class="log" style="color:var(--err)">${esc(j.traceback || j.error)}</pre>` : ""}
      ${(j.warnings || []).length ? `<ul class="warnlist">${j.warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      <pre class="log">${esc((j.log || []).join("\n") || "waiting for the agent…")}</pre>
      <div class="actions">${j.status === "done" && j.deck && j.action !== "brand" ? `<a class="btn primary" href="#/deck/${esc(j.deck)}">Open deck →</a>` : ""}
      ${j.status === "done" && j.action === "brand" ? `<a class="btn primary" href="#/brands">View template →</a>` : ""}</div>`;
  }, 1500);
};

pages.decks = async () => {
  const decks = await api("/api/decks");
  view.innerHTML = `<h1>Decks</h1><p class="sub">${decks.length} presentation(s)</p>
  ${decks.length ? `<div class="grid cols-3">${decks.map(d => `
    <a class="card deck-card" href="#/deck/${esc(d.name)}">
      <div class="thumb"><iframe loading="lazy" src="/files/decks/${esc(d.name)}/v${pad3(d.latest)}.html?static=1#1" tabindex="-1"></iframe></div>
      <div><strong>${esc(d.title)}</strong><div class="meta">${d.slides} slides · v${pad3(d.latest)} · ${esc(d.template)} · ${ago(d.updated)}</div></div>
    </a>`).join("")}</div>` : `<div class="card empty">No decks yet. <a href="#/new">Create one</a>.</div>`}`;
};

pages.deck = async (name, query) => {
  const v = query.get("v");
  const d = await api(`/api/decks/${encodeURIComponent(name)}${v ? "?version=" + v : ""}`);
  const ver = pad3(d.version);
  const src = `/files/decks/${esc(d.name)}/v${ver}.html`;
  const has = ext => d.files.includes(`v${ver}.${ext}`);
  view.innerHTML = `
  <div class="toolbar"><h1 class="grow">${esc(d.deck.title)}</h1>
    <select id="ver">${d.versions.map(x => `<option value="${x}" ${x === d.version ? "selected" : ""}>v${pad3(x)}</option>`).join("")}</select>
  </div>
  <div class="viewer">
    <div>
      <div class="stagebox"><iframe id="frame" src="${src}" allow="fullscreen"></iframe></div>
      <div class="toolbar">
        <button class="sm" id="prev">← Prev</button><button class="sm" id="next">Next →</button>
        <span class="grow"></span>
        <a class="btn sm" href="${src}" target="_blank">Present ↗</a>
        <a class="btn sm" href="${src}?download=1" download>HTML</a>
        ${has("pptx") ? `<a class="btn sm" href="/files/decks/${esc(d.name)}/v${ver}.pptx?download=1">PPTX</a>` : `<button class="sm" data-export="pptx">Export PPTX</button>`}
        ${has("pdf") ? `<a class="btn sm" href="/files/decks/${esc(d.name)}/v${ver}.pdf?download=1">PDF</a>` : `<button class="sm" data-export="pdf">Export PDF</button>`}
      </div>
    </div>
    <div class="card">
      <div class="tabs">${["Slides", "Change", "Restyle", "JSON", "History"].map((t, i) => `<button data-tab="${t}" class="${i ? "" : "on"}">${t}</button>`).join("")}</div>
      <div id="tab"></div>
    </div>
  </div>`;
  const frame = $("#frame");
  let cur = 0;
  const go = i => { cur = Math.max(0, Math.min(d.deck.slides.length - 1, i)); frame.contentWindow.postMessage({deckGo: cur}, "*"); $$(".outline li").forEach((li, k) => li.classList.toggle("on", k === cur)); };
  $("#prev").onclick = () => go(cur - 1); $("#next").onclick = () => go(cur + 1);
  $("#ver").onchange = e => (location.hash = `#/deck/${d.name}?v=${e.target.value}`);
  $$("[data-export]").forEach(b => b.onclick = async () => {
    const fd = new FormData(); fd.append("action", "export"); fd.append("deck", d.name); fd.append("formats", b.dataset.export);
    const r = await api("/api/jobs", {method: "POST", body: fd}); location.hash = "#/job/" + r.id;
  });
  const submit = async fd => { fd.append("deck", d.name); const r = await api("/api/jobs", {method: "POST", body: fd}); location.hash = "#/job/" + r.id; };
  const tabs = {
    Slides: () => `<ul class="outline">${d.deck.slides.map((s, i) => `<li data-i="${i}"><span class="n">${i + 1}</span><span>${esc(s.title || s.quote || "(untitled)")}</span><span class="lay">${esc(s.layout)}</span></li>`).join("")}</ul>
      ${d.history[0]?.outputs ? "" : ""}`,
    Change: () => `<label>What should change?</label>
      <textarea id="instr" placeholder="e.g. Slide 3: turn the bullets into a column chart. Make the title slide punchier. Add a slide about risks."></textarea>
      <div class="drop" id="cdrop" style="padding:14px;margin-top:10px"><small>Attach new material or images (optional)</small></div><div class="files" id="cfiles"></div>
      <div class="actions"><button class="primary" id="apply">Apply change</button></div>`,
    Restyle: async () => `<label>Template</label><select id="rtpl">${await templateOptions(d.deck.template)}</select>
      <label>Extra style instructions <span class="hint">optional, uses the LLM</span></label><textarea id="rinstr" style="min-height:70px" placeholder="e.g. more visual, fewer words per slide"></textarea>
      <div class="actions"><button class="primary" id="restyle">Restyle</button></div>`,
    JSON: () => `<p class="meta">Edit text, layouts or data directly. Saving renders a new version without calling the LLM.</p>
      <textarea class="code" id="json">${esc(JSON.stringify(d.deck, null, 2))}</textarea>
      <div class="actions"><button class="primary" id="savejson">Save as new version</button></div>`,
    History: () => `<table><tr><th>Ver</th><th>Change</th><th></th></tr>${d.history.map(h => `<tr><td>v${pad3(h.version)}</td><td>${esc(h.note)}<div class="meta">${ago(h.time)}</div></td>
      <td>${h.version !== d.versions.at(-1) ? `<button class="sm" data-revert="${h.version}">Restore</button>` : ""}</td></tr>`).join("")}</table>`,
  };
  const show = async t => {
    $$(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
    $("#tab").innerHTML = await tabs[t]();
    if (t === "Slides") $$(".outline li").forEach(li => li.onclick = () => go(+li.dataset.i));
    if (t === "Change") {
      const files = []; const rr = l => fileChips($("#cfiles"), l, rr); dropzone($("#cdrop"), files, rr);
      $("#apply").onclick = () => { if (!$("#instr").value.trim() && !files.length) return toast("Describe the change first");
        const fd = new FormData(); fd.append("action", "edit"); fd.append("instructions", $("#instr").value); files.forEach(f => fd.append("files", f)); submit(fd).catch(e => toast(e.message)); };
    }
    if (t === "Restyle") $("#restyle").onclick = () => { const fd = new FormData(); fd.append("action", "restyle"); fd.append("template", $("#rtpl").value); fd.append("instructions", $("#rinstr").value); submit(fd).catch(e => toast(e.message)); };
    if (t === "JSON") $("#savejson").onclick = async () => {
      let body; try { body = JSON.parse($("#json").value); } catch (e) { return toast("Invalid JSON: " + e.message); }
      try { const r = await api(`/api/decks/${d.name}`, {method: "PUT", headers: {"content-type": "application/json"}, body: JSON.stringify(body)}); location.hash = "#/job/" + r.id; }
      catch (e) { toast(e.message, 6000); }
    };
    if (t === "History") $$("[data-revert]").forEach(b => b.onclick = () => { const fd = new FormData(); fd.append("action", "revert"); fd.append("version", b.dataset.revert); submit(fd).catch(e => toast(e.message)); });
  };
  $$(".tabs button").forEach(b => b.onclick = () => show(b.dataset.tab));
  show("Slides");
};

pages.brands = async () => {
  const ts = await api("/api/templates");
  const files = [];
  view.innerHTML = `<h1>Brands & templates</h1>
  <p class="sub">Upload a logo, colours, fonts, images, a sample .pptx or a brand-guidelines PDF. They're saved as a reusable template.</p>
  <div class="grid cols-3">${ts.map(t => `
    <div class="card deck-card">
      <div class="thumb">${t.preview ? `<iframe loading="lazy" src="/files/templates/${esc(t.name)}/preview.html?static=1#1" tabindex="-1"></iframe>` : `<div class="empty">no preview yet</div>`}</div>
      <div style="display:flex;align-items:center;gap:10px"><strong>${esc(t.name)}</strong>
        <span class="swatches" style="margin-left:auto">${["primary", "accent", "accent2", "background", "text"].map(k => t.colors?.[k] ? `<i style="background:${esc(t.colors[k])}" title="${k} ${esc(t.colors[k])}"></i>` : "").join("")}</span></div>
      <div class="meta">${esc(t.fonts?.heading || "")} / ${esc(t.fonts?.body || "")}</div>
      ${t.preview ? `<a class="btn sm" target="_blank" href="/files/templates/${esc(t.name)}/preview.html">Open preview ↗</a>` : ""}
    </div>`).join("")}</div>
  <div class="card" style="margin-top:24px">
    <h2>New brand template</h2>
    <div class="row"><div><label>Name</label><input id="bname" type="text" placeholder="acme"></div>
      <div><label>Logo <span class="hint">PNG with transparency is best</span></label><input id="blogo" type="file" accept="image/*"></div></div>
    <label>Colours <span class="hint">leave untouched to auto-detect from the logo / sample deck</span></label>
    <div class="colorrow">${["primary", "accent", "accent2", "background", "text"].map(k => `<div><label><input type="checkbox" data-use="${k}"> ${k}</label><input type="color" id="c_${k}" value="${{primary: "#1d4ed8", accent: "#f59e0b", accent2: "#10b981", background: "#ffffff", text: "#111827"}[k]}"></div>`).join("")}</div>
    <div class="row">
      <div><label>Heading font</label><input id="fh" type="text" placeholder="e.g. Montserrat"></div>
      <div><label>Body font</label><input id="fb" type="text" placeholder="e.g. Inter"></div>
    </div>
    <label>Font stylesheet URLs <span class="hint">optional, e.g. a Google Fonts link (one per line)</span></label>
    <textarea id="fcss" style="min-height:50px"></textarea>
    <div class="row">
      <div><label>Slide transition</label><select id="trans"><option>slide</option><option>fade</option><option>zoom</option></select></div>
      <div><label>Element animation</label><select id="anim"><option>rise</option><option>fade</option><option>zoom</option><option>slide</option></select></div>
      <div><label>Title background</label><select id="tbg"><option>primary</option><option>image</option><option>background</option></select></div>
      <div><label>Logo position</label><select id="lpos"><option>top-right</option><option>top-left</option><option>bottom-right</option><option>bottom-left</option></select></div>
    </div>
    <div class="row"><div><label>Tone of voice</label><input id="tone" type="text" placeholder="confident, plain English"></div>
      <div><label>Footer</label><input id="foot" type="text" placeholder="Acme Inc. · Confidential"></div></div>
    <label>Other brand files <span class="hint">images (name a file "background" for title slides), sample .pptx, guideline PDF/DOCX</span></label>
    <div class="drop" id="bdrop" style="padding:16px"><small>Drop files or click</small></div><div class="files" id="bfiles"></div>
    <div class="actions"><button class="primary" id="bgo">Build template</button></div>
  </div>`;
  const rr = l => fileChips($("#bfiles"), l, rr); dropzone($("#bdrop"), files, rr);
  $("#bgo").onclick = async () => {
    const name = $("#bname").value.trim(); if (!name) return toast("Give the template a name");
    const fd = new FormData(); fd.append("name", name);
    $$("[data-use]").forEach(cb => { if (cb.checked) fd.append(cb.dataset.use, $("#c_" + cb.dataset.use).value); });
    fd.append("heading_font", $("#fh").value); fd.append("body_font", $("#fb").value); fd.append("font_css", $("#fcss").value);
    fd.append("transition", $("#trans").value); fd.append("animation", $("#anim").value);
    fd.append("title_background", $("#tbg").value); fd.append("logo_position", $("#lpos").value);
    fd.append("tone", $("#tone").value); fd.append("footer", $("#foot").value);
    if ($("#blogo").files[0]) fd.append("logo", $("#blogo").files[0]);
    files.forEach(f => fd.append("files", f));
    try { const r = await api("/api/templates", {method: "POST", body: fd}); location.hash = "#/job/" + r.id; } catch (e) { toast(e.message); }
  };
};

pages.queue = async () => {
  view.innerHTML = `<h1>Queue</h1><p class="sub">Jobs from the UI, the CLI and files dropped into <code>inbox/</code>.</p><div class="card" id="jobs"></div>`;
  every(async () => {
    const jobs = await api("/api/jobs");
    $("#jobs").innerHTML = jobs.length ? `<table><tr><th>Status</th><th>Job</th><th>Deck</th><th>Updated</th></tr>${jobs.map(j => `
      <tr><td>${statusChip(j.status)}</td><td><a href="#/job/${esc(j.id)}">${esc(j.action || "")}</a> <span class="meta">${esc(j.title || j.id)}</span>
        ${j.error ? `<div style="color:var(--err);font-size:13px">${esc(j.error)}</div>` : ""}</td>
        <td>${j.deck && j.status === "done" && j.action !== "brand" ? `<a href="#/deck/${esc(j.deck)}">${esc(j.deck)}</a>` : esc(j.deck || j.template || "")}${j.version ? ` v${pad3(j.version)}` : ""}</td>
        <td class="meta">${ago(j.updated)}</td></tr>`).join("")}</table>` : `<div class="empty">No jobs yet.</div>`;
  }, 3000);
};

pages.settings = async () => {
  const s = await api("/api/settings");
  const st = await api("/api/status");
  const llm = s.llm;
  const provOpts = sel => s.providers.map(p => `<option ${p === sel ? "selected" : ""}>${p}</option>`).join("");
  const avail = p => st.providers[p]?.available ? `<span class="pill-ok">● available</span>` : `<span class="pill-no">○ not configured</span>`;
  view.innerHTML = `<h1>Settings</h1><p class="sub">Pick which model does what. Local Ollama runs on your GPU; API keys for OpenAI / Anthropic go in <code>.env</code>.</p>
  <div class="grid cols-2">
    <div class="card"><h2>Task routing</h2>
      <table>${s.tasks.map(t => `<tr><td><b>${t}</b></td><td><select data-route="${t}">${provOpts(llm.routing?.[t] || llm.default_provider)}</select></td></tr>`).join("")}</table>
      <label>Fallback order <span class="hint">comma separated</span></label><input id="fallback" type="text" value="${esc((llm.fallback_order || []).join(", "))}">
      <h2 style="margin-top:22px">Quality checks</h2>
      <label><input type="checkbox" id="qa_review" ${s.qa.vision_review !== false ? "checked" : ""}> Visual review of rendered slides</label>
      <label><input type="checkbox" id="qa_fix" ${s.qa.auto_fix !== false ? "checked" : ""}> Auto-fix problems found by the review</label>
      <label>Always export <span class="hint">besides HTML</span></label>
      <label><input type="checkbox" id="f_pptx" ${(s.render.formats || []).includes("pptx") ? "checked" : ""}> PPTX</label>
      <label><input type="checkbox" id="f_pdf" ${(s.render.formats || []).includes("pdf") ? "checked" : ""}> PDF</label>
    </div>
    <div class="card"><h2>Providers</h2>
      <h3>Ollama (local GPU) ${avail("ollama")}</h3>
      <div class="row"><div><label>URL</label><input id="o_url" type="text" value="${esc(llm.ollama?.url)}"></div>
        <div><label>Context (num_ctx)</label><input id="o_ctx" type="number" value="${esc(llm.ollama?.num_ctx)}"></div></div>
      <div class="row"><div><label>Text model</label><input id="o_text" type="text" value="${esc(llm.ollama?.text_model)}"></div>
        <div><label>Vision model</label><input id="o_vis" type="text" value="${esc(llm.ollama?.vision_model)}"></div></div>
      <label><input type="checkbox" id="o_think" ${llm.ollama?.think ? "checked" : ""}> Thinking mode (slower, better plans)</label>
      <div class="meta">${st.providers.ollama?.installed ? "Installed: " + esc(st.providers.ollama.installed.join(", ")) : ""}</div>
      <h3>OpenAI ${avail("openai")}</h3>
      <label>Model</label><input id="oa_model" type="text" value="${esc(llm.openai?.model)}">
      <h3>Anthropic ${avail("anthropic")}</h3>
      <div class="row"><div><label>Model</label><input id="an_model" type="text" value="${esc(llm.anthropic?.model)}"></div>
        <div><label>Effort</label><select id="an_effort">${["low", "medium", "high", "xhigh", "max"].map(e => `<option ${e === llm.anthropic?.effort ? "selected" : ""}>${e}</option>`).join("")}</select></div></div>
    </div>
  </div>
  <div class="actions"><button class="primary" id="save">Save settings</button><button id="gpu">Run GPU check</button><button id="gpupull">GPU check + pull models</button></div>
  <div class="card" id="gpuout" style="margin-top:20px" hidden></div>`;
  $("#save").onclick = async () => {
    const routing = {}; $$("[data-route]").forEach(sel => (routing[sel.dataset.route] = sel.value));
    const formats = ["html", $("#f_pptx").checked && "pptx", $("#f_pdf").checked && "pdf"].filter(Boolean);
    const body = {llm: {routing, fallback_order: $("#fallback").value.split(",").map(x => x.trim()).filter(Boolean),
      ollama: {url: $("#o_url").value, num_ctx: +$("#o_ctx").value, text_model: $("#o_text").value, vision_model: $("#o_vis").value, think: $("#o_think").checked},
      openai: {model: $("#oa_model").value}, anthropic: {model: $("#an_model").value, effort: $("#an_effort").value}},
      qa: {vision_review: $("#qa_review").checked, auto_fix: $("#qa_fix").checked}, render: {formats}};
    try { await api("/api/settings", {method: "PUT", headers: {"content-type": "application/json"}, body: JSON.stringify(body)}); toast("Saved"); }
    catch (e) { toast(e.message); }
  };
  const gpu = async pull => {
    const box = $("#gpuout"); box.hidden = false; box.innerHTML = `<div class="progress-line"></div><p class="meta">Checking GPU${pull ? " and pulling models (can take a while)" : ""}…</p>`;
    try {
      const r = await api("/api/gpu-check?pull=" + pull, {method: "POST"});
      box.innerHTML = `<h2>GPU check</h2><div class="kv">
        <b>GPU</b><span>${r.gpus.length ? r.gpus.map(g => `${esc(g.name)} · ${g.vram_gb} GB (driver ${esc(g.driver)})`).join("<br>") : "none detected"}</span>
        <b>Text model</b><span>${esc(r.text_model)}</span><b>Vision model</b><span>${esc(r.vision_model)}</span>
        <b>Loaded</b><span>${r.loaded.map(m => `${esc(m.name)}: ${m.gpu_pct}% on GPU (${m.vram_gb}/${m.size_gb} GB)`).join("<br>") || "-"}</span></div>
        ${r.warnings.length ? `<ul class="warnlist">${r.warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : `<p class="pill-ok">All good: models run fully on the GPU.</p>`}`;
    } catch (e) { box.innerHTML = `<p style="color:var(--err)">${esc(e.message)}</p>`; }
  };
  $("#gpu").onclick = () => gpu(false); $("#gpupull").onclick = () => gpu(true);
};

// ---------- router ----------
async function route() {
  timers.forEach(clearInterval); timers = [];
  const [path, qs] = (location.hash.slice(2) || "new").split("?");
  const [page, ...rest] = path.split("/");
  $$("nav a").forEach(a => a.classList.toggle("on", a.dataset.nav === (page === "deck" ? "decks" : page === "job" ? "queue" : page)));
  try { await (pages[page] || pages.new)(decodeURIComponent(rest.join("/")), new URLSearchParams(qs)); }
  catch (e) { view.innerHTML = `<div class="card empty">${esc(e.message)}</div>`; }
}
addEventListener("hashchange", route);
route();
