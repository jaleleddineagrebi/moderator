"use strict";

const PAGES_CFG = window.MODERATOR_PAGES || null;
const isStaticMode = () => Boolean(PAGES_CFG && PAGES_CFG.static_mode);
const POLL_MS = isStaticMode() ? 5000 : 3000;
let state = null;
let liveRunId = null;
let selectedRunId = null; // null = follow live run
let openStep = null;
const renderedKeys = { approvals: "", outputs: "", runs: "", banner: "" };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const activeRunId = () => selectedRunId || liveRunId || (state && state.run_id) || "";
const isArchived = () => Boolean(selectedRunId && liveRunId && selectedRunId !== liveRunId);
const isReadOnly = () => isStaticMode() || isArchived();
const fileUrl = (rel) => {
  const encoded = rel.split("/").map(encodeURIComponent).join("/");
  if (isStaticMode()) return `data/runs/${encodeURIComponent(activeRunId())}/${encoded}`;
  return isArchived() ? `/api/runs/${encodeURIComponent(selectedRunId)}/files/${encoded}` : `/files/${encoded}`;
};
const STATUS_LABEL = {
  queued: "queued", running: "running", waiting_for_approval: "needs you", done: "done",
  failed: "failed", needs_revision: "revising", blocked: "blocked", idle: "ready",
};

// Theme

$("theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
});

// Run switcher & retry all

$("run-select").addEventListener("change", (ev) => {
  const val = ev.target.value;
  selectedRunId = val === liveRunId ? null : val;
  renderedKeys.approvals = "";
  renderedKeys.outputs = "";
  poll();
});

$("retry-all-btn").addEventListener("click", async () => {
  $("retry-all-btn").disabled = true;
  await fetch("/api/retry-failed", { method: "POST" }).catch(() => {});
  $("retry-all-btn").disabled = false;
  poll();
});

// Polling

async function poll() {
  try {
    if (isStaticMode()) {
      const bust = `t=${Date.now()}`;
      const runsRes = await fetch(`data/runs.json?${bust}`, { cache: "no-store" });
      if (!runsRes.ok) throw new Error(runsRes.status);
      const runsData = await runsRes.json();
      liveRunId = runsData.live_run_id;
      renderRunSelect(runsData.runs || []);
      const targetId = selectedRunId || liveRunId;
      if (targetId) {
        const stRes = await fetch(`data/runs/${encodeURIComponent(targetId)}/state.json?${bust}`, { cache: "no-store" });
        if (!stRes.ok) throw new Error(stRes.status);
        state = await stRes.json();
      } else if (runsData.seed_state) {
        state = runsData.seed_state;
      } else {
        throw new Error("no runs exported yet");
      }
      $("conn").hidden = true;
      render();
      return;
    }

    const endpoint = isArchived() ? `/api/runs/${encodeURIComponent(selectedRunId)}/state` : "/api/state";
    const [res, runsRes] = await Promise.all([
      fetch(endpoint, { cache: "no-store" }),
      fetch("/api/runs", { cache: "no-store" }).catch(() => null),
    ]);
    if (!res.ok) throw new Error(res.status);
    state = await res.json();
    if (runsRes && runsRes.ok) {
      const runsData = await runsRes.json();
      liveRunId = runsData.live_run_id;
      renderRunSelect(runsData.runs || []);
    }
    $("conn").hidden = true;
    render();
  } catch (e) {
    $("conn").hidden = false;
  }
}

function renderRunSelect(runs) {
  const sel = $("run-select");
  if (runs.length <= 1) {
    sel.hidden = true;
    return;
  }
  const key = JSON.stringify([selectedRunId || liveRunId, runs.map((r) => [r.run_id, r.status])]);
  if (key === renderedKeys.runs) return;
  renderedKeys.runs = key;
  sel.hidden = false;
  const active = selectedRunId || liveRunId;
  sel.innerHTML = runs.map((r) => {
    const tag = r.has_uploads ? "published" : (r.is_live ? "● latest" : r.status);
    return `<option value="${esc(r.run_id)}" ${r.run_id === active ? "selected" : ""}>${esc(r.run_id)} (${esc(tag)})</option>`;
  }).join("");
}

function displayStatus(id) {
  const s = state.steps[id];
  if (s.status === "queued" && s.depends_on.some((d) => state.steps[d].status !== "done")) return "blocked";
  return s.status;
}

function badge(status) {
  return `<span class="badge s-${status}">${esc(STATUS_LABEL[status] || status)}</span>`;
}

function formatDuration(secs) {
  secs = Math.max(0, Math.round(secs));
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
}

function stepElapsed(s) {
  if (!s.started_at) return "";
  const end = s.ended_at ? new Date(s.ended_at) : new Date();
  return formatDuration((end - new Date(s.started_at)) / 1000);
}

function render() {
  document.title = `${state.workflow_title} · Moderator`;
  $("wf-title").textContent = state.workflow_title;
  $("run-id").textContent = state.is_seed ? "awaiting first workflow run" : state.run_id;
  $("archive-badge").hidden = !isArchived();
  const pagesBadge = $("pages-badge");
  if (pagesBadge) pagesBadge.hidden = !isStaticMode();
  const ghBtn = $("gh-actions-btn");
  if (ghBtn && PAGES_CFG && PAGES_CFG.actions_url) {
    ghBtn.href = PAGES_CFG.actions_url;
    ghBtn.hidden = false;
  }
  const stCls = state.status === "done" ? "done" : state.status === "failed" ? "failed" : state.status === "idle" ? "queued" : "running";
  $("run-status").className = `badge s-${stCls}`;
  $("run-status").textContent = STATUS_LABEL[state.status] || state.status;
  $("retry-all-btn").hidden = isReadOnly() || state.status !== "failed";
  renderPagesBanner();
  renderOverview();
  renderApprovals();
  renderCheckpoints();
  renderPipeline();
  renderCards();
  renderNotifications();
  if (openStep && state.steps[openStep]) renderDrawer();
}

function renderPagesBanner() {
  const banner = $("pages-banner");
  if (!banner) return;
  const pm = state.pages_meta || {};
  const uploads = pm.uploads || [];
  const pending = Object.entries(state.checkpoints || {}).filter(([, cp]) => cp.status === "pending");
  const key = JSON.stringify([state.run_id, state.status, state.is_seed, uploads, pending.map(([k]) => k), pm.issue_url, pm.gh_run_url]);
  if (key === renderedKeys.banner) return;
  renderedKeys.banner = key;

  if (uploads.length > 0) {
    banner.hidden = false;
    banner.className = "card pages-banner is-done";
    const pills = uploads.map((u) =>
      `<a class="yt-pill" href="${esc(u.url)}" target="_blank" rel="noopener">▶ Watch ${esc((u.lang || "").toUpperCase())} Short (${esc(u.privacy)}) · ${esc(u.channel || "YouTube")}</a>`
    ).join("");
    banner.innerHTML = `<div class="row-between"><h2>Published to YouTube</h2>${pm.gh_run_url ? `<a class="btn link-btn" href="${esc(pm.gh_run_url)}" target="_blank" rel="noopener">Action Logs</a>` : ""}</div><div class="yt-links">${pills}</div>`;
    return;
  }

  if (isStaticMode() && state.is_seed) {
    banner.hidden = false;
    banner.className = "card pages-banner";
    const actUrl = (PAGES_CFG && PAGES_CFG.actions_url) || "#";
    banner.innerHTML = `<div class="row-between"><h2>Moderator Multi-Agent Pipeline Ready</h2><a class="btn primary link-btn" href="${esc(actUrl)}" target="_blank" rel="noopener">Trigger First YouTube Short →</a></div>
      <div class="muted">Click any agent in the pipeline or cards below to inspect its tools &amp; fallback strategies. Once you trigger <strong>Generate Short</strong> in GitHub Actions, live agent progress, previews, QA reports, and YouTube links appear here automatically.</div>`;
    return;
  }

  if (isStaticMode() && pending.length > 0) {
    const [cpId, cp] = pending[0];
    const step = state.steps[cp.step];
    const stepVer = step.ended_at || step.started_at || step.attempt;
    const issueHref = pm.issue_url || (PAGES_CFG && PAGES_CFG.issues_url) || "#";
    banner.hidden = false;
    banner.className = "card pages-banner is-waiting";
    banner.innerHTML = `
      <div class="row-between">
        <h2>Checkpoint ${esc(cpId)}: ${esc(cp.title)}</h2>
        <div class="actions">
          ${pm.gh_run_url ? `<a class="btn link-btn" href="${esc(pm.gh_run_url)}" target="_blank" rel="noopener">Action Run</a>` : ""}
          <a class="btn primary link-btn" href="${esc(issueHref)}" target="_blank" rel="noopener">Approve or Reject on GitHub Issue →</a>
        </div>
      </div>
      <div class="muted">Preview the generated Short(s), thumbnails, and QA report below, then comment one of these commands on the GitHub Review Issue (click to copy):</div>
      <div class="actions">
        <button type="button" class="cmd-chip" data-copy="/approve">/approve (private)</button>
        <button type="button" class="cmd-chip" data-copy="/approve unlisted">/approve unlisted</button>
        <button type="button" class="cmd-chip" data-copy="/approve public">/approve public</button>
        <button type="button" class="cmd-chip" data-copy="/reject">/reject</button>
      </div>
      <div class="approval-outputs">${outputsHtml(step.outputs, stepVer, true)}</div>`;
    banner.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigator.clipboard?.writeText(btn.dataset.copy);
        const orig = btn.textContent;
        btn.textContent = `Copied: ${btn.dataset.copy}`;
        setTimeout(() => (btn.textContent = orig), 1400);
      });
    });
    wireTextPreviews(banner);
    return;
  }

  banner.hidden = true;
}

function renderOverview() {
  const steps = Object.values(state.steps);
  const pct = steps.length ? Math.round(steps.reduce((a, s) => a + (s.status === "done" ? 100 : s.progress), 0) / steps.length) : 0;
  $("ov-pct").textContent = pct + "%";
  $("ov-bar").style.width = pct + "%";
  $("ov-steps").textContent = `${steps.filter((s) => s.status === "done").length}/${steps.length}`;
  const spent = "$" + (state.cost.total_usd || 0).toFixed(2);
  const budget = state.cost.budget_usd;
  $("ov-cost").textContent = budget != null ? `${spent} / $${Number(budget).toFixed(2)}` : spent;
  renderParams();
  tickElapsed();
}

function renderParams() {
  const p = state.params || {};
  const shown = [];
  if (p.niche) shown.push(["Niche", p.niche]);
  if (p.topic) shown.push(["Topic", p.topic]);
  if (p.languages) shown.push(["Languages", Array.isArray(p.languages) ? p.languages.join(", ") : p.languages]);
  if (p.style) shown.push(["Style", p.style]);
  if (p.auto_approve && p.auto_approve.length) shown.push(["Auto-approve", p.auto_approve.join(", ")]);
  const strip = $("ov-params");
  strip.hidden = shown.length === 0;
  strip.innerHTML = shown.map(([k, v]) => `<span class="param-chip" title="${esc(v)}"><strong>${esc(k)}:</strong> ${esc(v)}</span>`).join("");
}

function tickElapsed() {
  if (!state) return;
  if (state.is_seed || !state.started_at) {
    $("ov-elapsed").textContent = "0:00";
    return;
  }
  const end = state.ended_at ? new Date(state.ended_at) : new Date();
  $("ov-elapsed").textContent = formatDuration((end - new Date(state.started_at)) / 1000);
}

// Approvals

function upstreamOf(stepId) {
  const seen = new Set();
  const visit = (id) => state.steps[id].depends_on.forEach((d) => { if (!seen.has(d)) { seen.add(d); visit(d); } });
  visit(stepId);
  return Object.keys(state.steps).filter((id) => seen.has(id));
}

function renderApprovals() {
  const pending = isReadOnly() ? [] : Object.entries(state.checkpoints).filter(([, cp]) => cp.status === "pending");
  const key = JSON.stringify([selectedRunId, pending.map(([id, cp]) => [id, cp.options, state.steps[cp.step].outputs])]);
  if (key === renderedKeys.approvals) return; // keep what the user is typing
  renderedKeys.approvals = key;
  const box = $("approvals");
  box.hidden = pending.length === 0;
  box.innerHTML = pending.map(([id, cp]) => {
    const step = state.steps[cp.step];
    const stepVer = step.ended_at || step.started_at || step.attempt;
    const routes = [cp.step, ...upstreamOf(cp.step)];
    const options = cp.type === "choice" ? `<div class="options">${cp.options.map((o) => `
        <label class="option"><input type="radio" name="choice-${esc(id)}" value="${esc(o.id)}">
          <div><div class="opt-label" dir="auto">${esc(o.label)}</div><div class="opt-detail" dir="auto">${esc(o.detail || "")}</div></div>
        </label>`).join("")}</div>` : "";
    return `<form class="approval" data-cp="${esc(id)}">
      <div class="row-between"><h2>Checkpoint ${esc(id)}: ${esc(cp.title)}</h2>
        <button type="button" class="btn" data-open="${esc(cp.step)}">Open ${esc(step.title)}</button></div>
      ${options}
      <label class="label" for="c-${esc(id)}">Comment (required to request changes)</label>
      <textarea id="c-${esc(id)}" name="comment" dir="auto" placeholder="What should change?"></textarea>
      <div class="actions">
        <button type="submit" class="btn primary" name="action" value="approve" ${cp.type === "choice" ? "disabled" : ""}>Approve</button>
        <button type="submit" class="btn" name="action" value="request_changes">Request changes</button>
        <span class="muted">send to</span>
        <select name="route_to" style="width:auto">${routes.map((r) => `<option value="${esc(r)}" ${r === cp.route_to ? "selected" : ""}>${esc(state.steps[r].title)}</option>`).join("")}</select>
        <span class="error-text" role="alert"></span>
      </div>
      <div class="approval-outputs">${outputsHtml(step.outputs, stepVer, true)}</div>
    </form>`;
  }).join("");
  box.querySelectorAll("form").forEach(wireApproval);
  box.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => openDrawer(b.dataset.open)));
  wireTextPreviews(box);
}

function wireApproval(form) {
  const approve = form.querySelector('[value="approve"]');
  form.addEventListener("change", () => {
    if (form.querySelector('input[type="radio"]')) approve.disabled = !form.querySelector("input[type=radio]:checked");
  });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const action = ev.submitter.value;
    const data = new FormData(form);
    const err = form.querySelector(".error-text");
    if (action === "request_changes" && !data.get("comment").trim()) {
      err.textContent = "Write what should change first.";
      return;
    }
    form.querySelectorAll("button").forEach((b) => (b.disabled = true));
    const cp = form.dataset.cp;
    const res = await fetch(`/api/checkpoints/${encodeURIComponent(cp)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, comment: data.get("comment"), choice: data.get(`choice-${cp}`), route_to: data.get("route_to") }),
    });
    if (!res.ok) {
      err.textContent = (await res.json().catch(() => ({}))).detail || "Request failed";
      form.querySelectorAll("button").forEach((b) => (b.disabled = false));
      return;
    }
    renderedKeys.approvals = "";
    poll();
  });
}

// Pipeline

function renderPipeline() {
  const svg = $("pipeline");
  const ids = Object.keys(state.steps);
  if (!ids.length) { svg.innerHTML = ""; return; }
  const depth = state.pipeline.depth;
  const W = 168, H = 58, GX = 56, GY = 18, PAD = 8;
  const cols = {};
  ids.forEach((id) => (cols[depth[id]] ||= []).push(id));
  const maxRows = Math.max(...Object.values(cols).map((c) => c.length));
  const pos = {};
  Object.entries(cols).forEach(([d, list]) => {
    const offset = ((maxRows - list.length) * (H + GY)) / 2;
    list.forEach((id, i) => (pos[id] = { x: PAD + d * (W + GX), y: PAD + offset + i * (H + GY) }));
  });
  const width = PAD * 2 + (Object.keys(cols).length) * (W + GX) - GX;
  const height = PAD * 2 + maxRows * (H + GY) - GY;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);

  const defs = `<defs>
    <marker id="m-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
      <path class="arrow" d="M0,1 L7,4 L0,7 z"/>
    </marker>
    <marker id="m-arrow-live" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
      <path class="arrow-live" d="M0,1 L7,4 L0,7 z"/>
    </marker>
  </defs>`;
  const edges = ids.flatMap((id) => state.steps[id].depends_on.map((d) => {
    const a = pos[d], b = pos[id];
    const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x - 2, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
    const live = state.steps[d].status === "done";
    return `<path class="edge ${live ? "live" : ""}" marker-end="url(#${live ? "m-arrow-live" : "m-arrow"})" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"/>`;
  }));
  const nodes = ids.map((id) => {
    const s = state.steps[id], st = displayStatus(id), p = pos[id];
    const agent = state.agents[s.agent]?.title || s.agent;
    const prog = st === "done" ? 100 : s.progress;
    const cp = s.checkpoint ? `<text class="cp" x="${W - 8}" y="16" text-anchor="end">⏸${esc(s.checkpoint)}</text>` : "";
    return `<g class="node s-${st}" data-step="${esc(id)}" transform="translate(${p.x},${p.y})" tabindex="0">
      <title>${esc(s.title)}: ${esc(STATUS_LABEL[st])}</title>
      <rect class="box" width="${W}" height="${H}" rx="8"/>
      <text x="10" y="20">${esc(clip(s.title, 20))}</text>
      <text class="sub" x="10" y="37">${esc(clip(agent, 16))} · ${esc(STATUS_LABEL[st])}</text>
      ${cp}
      <rect class="prog" x="0" y="${H - 4}" width="${(W * prog) / 100}" height="4" rx="2"/>
    </g>`;
  });
  svg.innerHTML = defs + edges.join("") + nodes.join("");
  svg.querySelectorAll(".node").forEach((n) => {
    n.addEventListener("click", () => openDrawer(n.dataset.step));
    n.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDrawer(n.dataset.step); } });
  });
}

const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

// Agent cards

function renderCards() {
  $("cards").innerHTML = Object.entries(state.steps).map(([id, s]) => {
    const st = displayStatus(id);
    const agent = state.agents[s.agent] || { title: s.agent, role: "" };
    const last = s.logs[s.logs.length - 1];
    const task = st === "running" ? `${s.title} · attempt ${s.retries + 1}${s.strategy && s.strategy !== "default" ? ` (${s.strategy})` : ""}` : s.title;
    const dur = stepElapsed(s);
    const metaLeft = [dur && `⏱ ${dur}`, s.retries > 0 && `retries: ${s.retries}/${s.max_retries}`].filter(Boolean).join(" · ");
    const metaRight = s.cost_usd > 0 ? `$${s.cost_usd.toFixed(3)}` : "";
    return `<button class="agent-card s-${st}" data-step="${esc(id)}">
      <div class="row-between"><h3>${esc(agent.title)}</h3>${badge(st)}</div>
      <div class="role">${esc(agent.role)}</div>
      <div class="task"><span class="muted">Task:</span> ${esc(task)}</div>
      <div class="row-between"><div class="bar" style="flex:1;margin:0 10px 0 0"><div class="bar-fill" style="width:${st === "done" ? 100 : s.progress}%"></div></div><span class="mono">${st === "done" ? 100 : s.progress}%</span></div>
      <div class="lastlog" dir="auto">${last ? esc(last.msg) : "<span class='muted'>no activity yet</span>"}</div>
      ${(metaLeft || metaRight) ? `<div class="card-meta mono"><span>${esc(metaLeft)}</span><span>${esc(metaRight)}</span></div>` : ""}
    </button>`;
  }).join("");
  $("cards").querySelectorAll(".agent-card").forEach((c) => c.addEventListener("click", () => openDrawer(c.dataset.step)));
}

const CP_STATUS = {
  idle: ["s-queued", "not reached yet"], pending: ["s-waiting_for_approval", "waiting for you (see above)"],
  approved: ["s-done", "approved"], changes_requested: ["s-needs_revision", "changes requested"],
};

function renderCheckpoints() {
  $("checkpoints").innerHTML = Object.entries(state.checkpoints).map(([id, cp]) => {
    const [cls, label] = CP_STATUS[cp.status] || ["s-queued", cp.status];
    const chosen = cp.options.find((o) => o.id === cp.choice);
    const extra = [chosen && `choice: ${chosen.label}`, cp.comment && `comment: “${cp.comment}”`, cp.decided_at && timeOf(cp.decided_at)]
      .filter(Boolean).join(" · ");
    return `<li><span class="badge ${cls}">${esc(label)}</span><span dir="auto"><strong>${esc(id)}</strong> ${esc(cp.title)}${extra ? ` <span class="muted">· ${esc(extra)}</span>` : ""}</span></li>`;
  }).join("") || `<li class="muted">This workflow has no checkpoints.</li>`;
}

function renderNotifications() {
  const items = state.notifications.slice(-10).reverse();
  $("notifications").innerHTML = items.length
    ? items.map((n) => `<li class="n-${esc(n.level)}"><span class="ts mono">${esc(timeOf(n.ts))}</span><span dir="auto">${esc(n.msg)}</span></li>`).join("")
    : `<li class="muted">Nothing yet.</li>`;
}

const timeOf = (ts) => (ts ? new Date(ts).toLocaleTimeString() : "");

// Outputs and previews

function outputsHtml(outputs, stepVer = "", compact = false) {
  const entries = Object.entries(outputs || {}).flatMap(([name, v]) => (Array.isArray(v) ? v.map((p, i) => [`${name} ${i + 1}`, p]) : [[name, v]]));
  if (!entries.length) return compact ? "" : `<p class="muted">No outputs yet.</p>`;
  return entries.map(([name, rel]) => {
    const url = fileUrl(rel) + `?v=${encodeURIComponent(stepVer || "")}`;
    const ext = rel.split(".").pop().toLowerCase();
    let media = "";
    if (["png", "jpg", "jpeg", "webp", "gif"].includes(ext)) media = `<img src="${url}" alt="${esc(name)}" loading="lazy">`;
    else if (["mp3", "wav", "m4a", "ogg"].includes(ext)) media = `<audio controls preload="none" src="${url}"></audio>`;
    else if (["mp4", "webm", "mov"].includes(ext)) media = `<video controls preload="metadata" src="${url}"></video>`;
    else if (["json", "txt", "md", "srt", "ass", "csv", "yaml"].includes(ext))
      media = `<details ${compact && ext === "md" ? "open" : ""} data-src="${url}"><summary>Show content</summary><pre class="text" dir="auto">Loading…</pre></details>`;
    return `<div class="output"><div class="row-between"><strong>${esc(name)}</strong><a href="${url}" target="_blank" rel="noopener" class="mono">${esc(rel)}</a></div>${media}</div>`;
  }).join("");
}

function wireTextPreviews(root) {
  root.querySelectorAll("details[data-src]").forEach((d) => {
    const load = async () => {
      if (d.dataset.loaded) return;
      d.dataset.loaded = "1";
      try {
        const res = await fetch(d.dataset.src);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        let shown = text;
        try { shown = JSON.stringify(JSON.parse(text), null, 2); } catch (e) {}
        d.querySelector("pre").textContent = shown;
      } catch (err) {
        delete d.dataset.loaded;
        d.querySelector("pre").textContent = `Could not load preview (${err.message}).`;
      }
    };
    d.addEventListener("toggle", () => d.open && load());
    if (d.open) load();
  });
}

// Drawer

let drawerStickBottom = true;

function openDrawer(id) {
  openStep = id;
  drawerStickBottom = true;
  renderedKeys.outputs = "";
  renderDrawer();
  if (!$("drawer").open) $("drawer").showModal();
}

$("d-close").addEventListener("click", () => $("drawer").close());
$("drawer").addEventListener("close", () => (openStep = null));
$("drawer").addEventListener("click", (e) => { if (e.target === $("drawer")) $("drawer").close(); });

function renderDrawer() {
  const s = state.steps[openStep];
  if (!s) return;
  const agent = state.agents[s.agent] || { title: s.agent, role: "", tools: [], inputs: [], outputs: [] };
  const st = displayStatus(openStep);
  $("d-title").innerHTML = `${esc(agent.title)} · ${esc(s.title)} ${badge(st)}`;
  $("d-role").textContent = agent.role;

  const body = $("d-body");
  // Remember open error trace disclosures & log scroll position before updating
  const prevLogs = $("d-logs");
  let prevScrollTop = 0;
  if (prevLogs) {
    drawerStickBottom = prevLogs.scrollHeight - prevLogs.scrollTop - prevLogs.clientHeight <= 32;
    prevScrollTop = prevLogs.scrollTop;
  }
  const openTraces = new Set(
    Array.from(body.querySelectorAll("details[data-trace][open]")).map((el) => el.dataset.trace)
  );

  const stepVer = s.ended_at || s.started_at || s.attempt;
  const outKey = JSON.stringify([selectedRunId, openStep, s.outputs, stepVer]);
  let outputsBox = body.querySelector("#d-outputs");
  const keepOutputs = outputsBox && outKey === renderedKeys.outputs;
  if (keepOutputs) outputsBox.remove(); // re-attach the same node so playing media is not interrupted

  body.innerHTML = `
    <section><dl class="kv">
      <dt>Status</dt><dd>${badge(st)}</dd>
      <dt>Progress</dt><dd>${st === "done" ? 100 : s.progress}%</dd>
      <dt>Attempts</dt><dd>${s.attempt} total · retries this round ${s.retries}/${s.max_retries}${s.strategy ? ` · strategy <span class="mono">${esc(s.strategy)}</span>` : ""}</dd>
      <dt>Started</dt><dd>${esc(timeOf(s.started_at)) || "–"}</dd>
      <dt>Ended</dt><dd>${esc(timeOf(s.ended_at)) || "–"}${s.started_at ? ` <span class="muted">(${esc(stepElapsed(s))})</span>` : ""}</dd>
      <dt>Cost</dt><dd>$${(s.cost_usd || 0).toFixed(3)}</dd>
      <dt>Depends on</dt><dd>${s.depends_on.map((d) => esc(state.steps[d].title)).join(", ") || "–"}</dd>
      <dt>Tools</dt><dd>${esc((agent.tools || []).join(", "))}</dd>
      <dt>Strategies</dt><dd>${esc((agent.strategies || []).join(" → "))}</dd>
    </dl>
    ${!isReadOnly() && s.status === "failed" ? `<div class="actions" style="margin-top:12px"><button class="btn primary" id="d-retry">Retry this step</button><span class="error-text"></span></div>` : ""}
    </section>
    ${s.feedback.length ? `<section><h2>Feedback received</h2>${s.feedback.map((f) => `<div class="fb" dir="auto"><strong>${esc(f.from)}</strong> <span class="muted">${esc(timeOf(f.ts))}</span>\n${esc(f.comment)}</div>`).join("")}</section>` : ""}
    <section><h2>Inputs received</h2>${Object.keys(s.inputs).length ? `<pre class="text" dir="auto">${esc(JSON.stringify(s.inputs, null, 2))}</pre>` : `<p class="muted">${esc((agent.inputs || []).join(", ")) || "None recorded."}</p>`}</section>
    <section id="d-outputs-slot"><h2>Outputs</h2></section>
    <section><h2>Errors (${s.errors.length})</h2>${s.errors.length ? s.errors.map((e, idx) => `<div class="err"><strong>Attempt ${e.attempt}</strong> <span class="muted">${esc(e.strategy)} · ${esc(timeOf(e.ts))}</span><div dir="auto">${esc(e.error)}</div>${e.trace ? `<details data-trace="${idx}" ${openTraces.has(String(idx)) ? "open" : ""}><summary class="muted">trace</summary><pre>${esc(e.trace)}</pre></details>` : ""}</div>`).join("") : `<p class="muted">None.</p>`}</section>
    <section><h2>Log (${s.logs.length})</h2><div class="logs mono" id="d-logs">${s.logs.map((l) => `<div class="l-${esc(l.level)}" dir="auto"><span class="muted">${esc(timeOf(l.ts))}</span> ${esc(l.msg)}</div>`).join("") || `<span class="muted">Empty.</span>`}</div></section>`;

  if (!keepOutputs) {
    outputsBox = document.createElement("div");
    outputsBox.id = "d-outputs";
    outputsBox.style.display = "grid";
    outputsBox.style.gap = "10px";
    outputsBox.innerHTML = outputsHtml(s.outputs, stepVer);
    wireTextPreviews(outputsBox);
    renderedKeys.outputs = outKey;
  }
  body.querySelector("#d-outputs-slot").appendChild(outputsBox);
  const logs = $("d-logs");
  logs.scrollTop = drawerStickBottom ? logs.scrollHeight : prevScrollTop;
  logs.addEventListener("scroll", () => {
    drawerStickBottom = logs.scrollHeight - logs.scrollTop - logs.clientHeight <= 32;
  });

  const retry = $("d-retry");
  if (retry) retry.addEventListener("click", async () => {
    retry.disabled = true;
    const res = await fetch(`/api/steps/${encodeURIComponent(openStep)}/retry`, { method: "POST" });
    if (!res.ok) retry.nextElementSibling.textContent = (await res.json().catch(() => ({}))).detail || "Retry failed";
    poll();
  });
}

poll();
setInterval(poll, POLL_MS);
setInterval(tickElapsed, 1000);
