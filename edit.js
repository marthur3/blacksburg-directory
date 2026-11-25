/* Owner edit mode. Loaded only with ?edit=1 or a stored token.
   Edits stage in this browser, then save as one commit to overrides.csv through the GitHub API.
   Shares globals with index.html: all, byId, shown, state, groups, cfg, DATA, render, esc, slug, $. */

const LS = { token: "bd_token", pending: "bd_pending", saved: "bd_saved", on: "bd_edit" };
const FLAGS = ["Wrong category", "Closed?", "Duplicate?", "Check in person", "Favorite", "Follow up"];
const HIDE_REASONS = ["Closed", "Duplicate", "Not a business", "Not relevant"];
const API = "https://api.github.com";

const ed = { added: new Set(), records: [], orig: new Map(), pending: emptyEdits(), saved: [], log: [], showHidden: false, toast: null, busy: false };

function emptyEdits() { return { listings: {}, rules: {}, adds: {} }; }
function lsGet(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }
function lsSet(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch {} }
const kindOf = r => (r.category || "").trim().toLowerCase();
const count = o => Object.keys(o.listings).length + Object.keys(o.rules).length + Object.keys(o.adds || {}).length;

function initEdit() {
  lsSet(LS.on, 1);
  document.body.classList.add("editing"); setCompact(); setTimeout(() => map && map.resize(), 350);
  ed.records = DATA.businesses.map(b => ({ ...b })).concat((DATA.hidden || []).map(h => ({ ...h, hidden: true })));
  ed.records.forEach(r => ed.orig.set(r.id, { ...r }));
  ed.pending = { ...emptyEdits(), ...lsGet(LS.pending, {}) };
  // Saved edits stay applied on top of the page data until a rebuild newer than the save arrives.
  ed.saved = lsGet(LS.saved, []).filter(s => !DATA.built || s.at > DATA.built);
  lsSet(LS.saved, ed.saved);

  document.head.insertAdjacentHTML("beforeend", `<style>${ED_CSS}</style>`);
  $("masthead").insertAdjacentHTML("afterend", `<div id="edbar"></div><div id="edpanel" hidden></div>`);
  $("sort").insertAdjacentHTML("beforeend", `<option value="conf">Least certain first</option>`);
  document.body.insertAdjacentHTML("beforeend", `<datalist id="kinds">${[...new Set(ed.records.map(kindOf).filter(Boolean))].sort().map(k => `<option value="${esc(k)}">`).join("")}</datalist>`);

  $("edbar").addEventListener("click", onBarClick);
  $("edbar").addEventListener("change", onBarChange);
  $("edpanel").addEventListener("click", onPanelClick);
  $("edpanel").addEventListener("change", onBarChange);
  $("edpanel").addEventListener("submit", onTokenSubmit);
  $("list").addEventListener("change", onEditorChange);
  $("list").addEventListener("click", onEditorClick);
  applyEdits();
}

/* Rebuilds every record from its original, then layers saved and pending edits on top. */
function applyEdits() {
  // Staged additions are rebuilt on every pass, so undo removes them cleanly.
  ed.records = ed.records.filter(r => !ed.added.has(r.id));
  ed.added.forEach(id => ed.orig.delete(id)); ed.added.clear();
  for (const layer of [...ed.saved.map(s => s.edits), ed.pending]) {
    for (const [id, a] of Object.entries(layer.adds || {})) {
      if (ed.orig.has(id)) continue;
      const rec = { id, name: a.name, group: a.group, category: a.category || "", address: a.address || "", town: a.town || "",
        lat: a.lat, lng: a.lng, website: a.website || "", phone: a.phone || "", social: "", google_place_id: "",
        notes: a.notes || "", flag: "", source: "manual" };
      ed.records.push(rec); ed.orig.set(id, { ...rec }); ed.added.add(id);
    }
  }
  for (const r of ed.records) {
    const o = ed.orig.get(r.id);
    for (const k of Object.keys(r)) if (!(k in o)) delete r[k];
    Object.assign(r, o);
  }
  for (const layer of [...ed.saved.map(s => s.edits), ed.pending]) {
    for (const [kind, rule] of Object.entries(layer.rules)) {
      for (const r of ed.records) {
        if (kindOf(ed.orig.get(r.id)) !== kind) continue;
        if (rule.group) { if (r.group !== rule.group) r.was_group ??= r.group; r.group = rule.group; }
        if (rule.hide) { r.hidden = true; r.hidden_by = "kind"; }
      }
    }
    for (const [id, p] of Object.entries(layer.listings)) {
      const r = ed.records.find(x => x.id === id);
      if (!r) continue;
      if (p.group && p.group !== r.group) { r.was_group ??= r.group; r.group = p.group; }
      for (const k of ["category", "notes", "flag"]) if (k in p) r[k] = p[k];
      if (typeof p.hide === "string") { r.hidden = true; r.hidden_by = "listing"; r.hidden_reason = p.hide; }
      if (p.hide === false) { r.hidden = false; }
    }
  }
  for (const r of ed.records) {
    r.edited = !!(ed.pending.listings[r.id] || ed.pending.adds[r.id]);
    r.isNew = !!r.first_seen && r.first_seen >= CUTOFF;
    r.hay = [r.name, r.category, r.group, r.address, r.town, r.notes, r.flag].join(" ").toLowerCase();
  }
  all = ed.records.filter(r => !r.hidden || ed.showHidden);
  all.sort((a, b) => a.name.localeCompare(b.name, "en", { sensitivity: "base" }));
  byId.clear(); all.forEach(b => byId.set(b.id, b));
  lsSet(LS.pending, ed.pending);
  drawBar();
  render();
  if (!$("edpanel").hidden && $("edpanel").dataset.view === "patterns") drawPatterns();
}

function stage(id, change, label) {
  ed.log.push(JSON.stringify(ed.pending));
  const o = ed.orig.get(id), p = { ...(ed.pending.listings[id] || {}), ...change };
  // A staged value equal to the original is no edit at all.
  if (p.group === o.group && !effectiveRule(kindOf(o))) delete p.group;
  for (const k of ["category", "notes", "flag"]) if (k in p && p[k] === (o[k] || "")) delete p[k];
  if (p.hide === false && !o.hidden) delete p.hide;
  if (typeof p.hide === "string" && o.hidden && o.hidden_by === "listing" && o.hidden_reason === p.hide) delete p.hide;
  if (Object.keys(p).length) ed.pending.listings[id] = p; else delete ed.pending.listings[id];
  ed.toast = label || null;
  applyEdits();
}
function stageRule(kind, rule) {
  ed.log.push(JSON.stringify(ed.pending));
  ed.pending.rules[kind] = rule;
  // Listing edits the rule now covers are redundant.
  for (const [id, p] of Object.entries(ed.pending.listings)) {
    if (kindOf(ed.orig.get(id)) !== kind) continue;
    if (rule.group && p.group === rule.group) delete p.group;
    if (rule.hide && typeof p.hide === "string") delete p.hide;
    if (!Object.keys(p).length) delete ed.pending.listings[id];
  }
  ed.toast = null;
  applyEdits();
}
function effectiveRule(kind) {
  return ed.pending.rules[kind] || ed.saved.map(s => s.edits.rules[kind]).filter(Boolean).pop()
    || (DATA.rules || []).find(r => r.kind === kind) || null;
}

/* Bar */
function drawBar() {
  const n = count(ed.pending), sug = suggestions().length;
  $("edbar").innerHTML = `
    <div class="edrow"><strong>${n ? `${n} unsaved` : ed.saved.length ? "Saved" : "Editing"}</strong>
      <span>${n ? `<button type="button" data-act="save" class="go"${ed.busy ? " disabled" : ""}>${ed.busy ? "Saving" : "Save"}</button>
      <button type="button" data-act="undo"${ed.log.length ? "" : " disabled"}>Undo</button>` : ""}
      <button type="button" data-act="tools">Tools${sug ? ` (${sug})` : ""}</button></span></div>
    ${ed.toast ? `<div class="edtoast">${ed.toast}</div>` : ""}`;
}
function onBarClick(e) {
  const act = e.target.dataset.act;
  if (act === "save") save();
  if (act === "undo" && ed.log.length) { ed.pending = JSON.parse(ed.log.pop()); ed.toast = null; applyEdits(); }
  if (act === "tools") togglePanel("patterns");
  if (e.target.dataset.rule) applyRuleButton(e.target);
}
function onBarChange(e) {
  if (e.target.dataset.act === "hidden") { ed.showHidden = e.target.checked; applyEdits(); }
  if (e.target.dataset.act === "flag") { state.flag = e.target.value; closePanel(); reset(); }
}
function applyRuleButton(btn) {
  const kind = btn.dataset.kind;
  stageRule(kind, btn.dataset.rule === "hide" ? { hide: true } : { group: btn.dataset.group });
}

/* Editor inside an open listing */
function badgeHtml(b) {
  return (b.hidden ? `<span class="tag hid">Hidden${b.hidden_reason ? `, ${esc(b.hidden_reason.toLowerCase())}` : ""}</span>` : "")
    + (b.edited ? `<span class="tag">Unsaved</span>` : "")
    + (b.flag ? b.flag.split("; ").map(f => `<span class="tag fl">${esc(f)}</span>`).join("") : "");
}
function editorHtml(b) {
  const flags = (b.flag || "").split("; ").filter(Boolean);
  return `<form class="ed" data-id="${esc(b.id)}" onsubmit="return false">
    <label>Group <select name="group">${DATA.groups.map(g => `<option${g === b.group ? " selected" : ""}>${esc(g)}</option>`).join("")}</select></label>
    <label>Kind <input name="category" list="kinds" value="${esc(b.category)}" autocomplete="off"></label>
    <div class="flags">${FLAGS.map(f => `<button type="button" data-flag="${esc(f)}" aria-pressed="${flags.includes(f)}">${esc(f)}</button>`).join("")}</div>
    <label>Note <textarea name="notes" rows="2" placeholder="Shown on the public listing">${esc(b.notes)}</textarea></label>
    <div class="edacts">${b.hidden
      ? `<button type="button" data-unhide>Put back on the directory</button>`
      : `<select name="hide"><option value="">Hide this listing</option>${HIDE_REASONS.map(r => `<option>${r}</option>`).join("")}</select>`}
      <small>${b.was_group ? `Was ${esc(b.was_group)}. ` : ""}${b.conf ? `Source confidence ${Math.round(b.conf * 100)}%.` : ""}</small></div>
  </form>`;
}
function onEditorChange(e) {
  const f = e.target.closest("form.ed"); if (!f) return;
  const id = f.dataset.id, o = ed.orig.get(id), kind = kindOf(o), v = e.target.value.trim();
  const peers = ed.records.filter(r => r.id !== id && !r.hidden && kindOf(ed.orig.get(r.id)) === kind);
  if (e.target.name === "group") {
    const rest = peers.filter(r => r.group !== v).length;
    stage(id, { group: v }, kind && rest ? `Moved to ${esc(v)}. <button type="button" data-rule="group" data-kind="${esc(kind)}" data-group="${esc(v)}">Move the other ${rest} “${esc(kind)}” too</button>` : null);
  } else if (e.target.name === "category") stage(id, { category: v.toLowerCase() });
  else if (e.target.name === "notes") stage(id, { notes: v });
  else if (e.target.name === "hide" && v) {
    stage(id, { hide: v }, `Hidden as ${esc(v.toLowerCase())}.` + (kind && peers.length && v !== "Closed" && v !== "Duplicate" ? ` <button type="button" data-rule="hide" data-kind="${esc(kind)}">Hide the other ${peers.length} “${esc(kind)}” too</button>` : ""));
  }
}
function onEditorClick(e) {
  const f = e.target.closest("form.ed"); if (!f) return;
  const id = f.dataset.id, r = ed.records.find(x => x.id === id);
  if (e.target.dataset.flag) {
    const set = new Set((r.flag || "").split("; ").filter(Boolean)), fl = e.target.dataset.flag;
    set.has(fl) ? set.delete(fl) : set.add(fl);
    stage(id, { flag: FLAGS.filter(x => set.has(x)).join("; ") });
  }
  if ("unhide" in e.target.dataset) stage(id, { hide: false }, "Back on the directory.");
}

/* Patterns: what the corrections so far say about whole kinds of listing */
function suggestions() {
  const moves = {}, hides = {}, out = [];
  for (const r of ed.records) {
    const o = ed.orig.get(r.id), kind = kindOf(o);
    if (!kind || effectiveRule(kind)) continue;
    if (!r.hidden && r.was_group && r.group !== r.was_group) ((moves[kind] ??= {})[r.group] ??= []).push(r);
    if (r.hidden && r.hidden_by === "listing" && !/^(closed|duplicate)$/i.test(r.hidden_reason || "")) (hides[kind] ??= []).push(r);
  }
  for (const [kind, byGroup] of Object.entries(moves)) for (const [group, rs] of Object.entries(byGroup)) {
    const peers = ed.records.filter(r => !r.hidden && kindOf(ed.orig.get(r.id)) === kind);
    const rest = peers.filter(r => r.group !== group).length;
    if (rs.length >= 2 && rest) out.push({ type: "group", kind, group, n: rs.length, total: peers.length, rest });
  }
  for (const [kind, rs] of Object.entries(hides)) {
    const rest = ed.records.filter(r => !r.hidden && kindOf(ed.orig.get(r.id)) === kind).length;
    if (rs.length >= 2 && rest) out.push({ type: "hide", kind, n: rs.length, total: rs.length + rest, rest });
  }
  return out.sort((a, b) => b.n / b.total - a.n / a.total);
}
function closedSignal() {
  const closed = ed.records.filter(r => r.hidden && /closed/i.test(r.hidden_reason || "") && r.conf).map(r => r.conf).sort((a, b) => a - b);
  if (closed.length < 5) return null;
  const median = closed[Math.floor(closed.length / 2)];
  return { n: closed.length, median, below: ed.records.filter(r => !r.hidden && r.conf && r.conf <= median).length };
}
function drawPatterns() {
  const sug = suggestions(), cs = closedSignal();
  const moved = ed.records.filter(r => !r.hidden && r.was_group).length, hid = ed.records.filter(r => r.hidden).length;
  const rules = Object.entries({ ...Object.fromEntries((DATA.rules || []).map(r => [r.kind, r])), ...Object.assign({}, ...ed.saved.map(s => s.edits.rules)), ...ed.pending.rules });
  const hiddenN = ed.records.filter(r => r.hidden).length;
  const flagged = FLAGS.map(f => [f, ed.records.filter(r => !r.hidden && (r.flag || "").split("; ").includes(f)).length]).filter(v => v[1]);
  $("edpanel").innerHTML = `<div class="edrow"><h2>Tools</h2><button type="button" data-act="close">Back to the list</button></div>
    <div class="edview"><label><input type="checkbox" data-act="hidden"${ed.showHidden ? " checked" : ""}> Show hidden listings (${hiddenN})</label>
      <select data-act="flag" aria-label="Filter by flag"><option value="">Show any flag</option>${flagged.map(([f, c]) => `<option value="${esc(f)}"${state.flag === f ? " selected" : ""}>Only “${esc(f)}” (${c})</option>`).join("")}</select></div>
    ${ed.saved.length ? `<p>Your saved changes already show here. The public page catches up in a few minutes.</p>` : ""}
    <h2>Patterns in your corrections</h2>
    <p>${moved} regrouped, ${hid} hidden so far.</p>
    ${sug.length ? `<ul>${sug.map(s => s.type === "group"
      ? `<li>You moved ${s.n} of ${s.total} “${esc(s.kind)}” listings to ${esc(s.group)}. <button type="button" data-rule="group" data-kind="${esc(s.kind)}" data-group="${esc(s.group)}">Move the other ${s.rest}</button></li>`
      : `<li>You hid ${s.n} of ${s.total} “${esc(s.kind)}” listings. <button type="button" data-rule="hide" data-kind="${esc(s.kind)}">Hide the other ${s.rest}</button></li>`).join("")}</ul>`
      : `<p>No pattern yet. One appears after you move or hide two listings of the same kind.</p>`}
    ${cs ? `<p>Half of the ${cs.n} listings you hid as closed had source confidence of ${Math.round(cs.median * 100)}% or less. ${cs.below} visible listings sit at or below that. <button type="button" data-act="leastcertain">Review them, least certain first</button></p>`
      : `<p>Hide five closed listings and this panel will show whether low source confidence predicts closures.</p>`}
    ${rules.length ? `<h2>Rules for whole kinds</h2><ul>${rules.map(([k, r]) => `<li>“${esc(k)}” ${r.hide ? "is hidden" : `goes to ${esc(r.group)}`}</li>`).join("")}</ul>` : ""}
    <p><button type="button" data-act="add" class="go">Add a missing business</button> <button type="button" data-act="account">GitHub token and account</button></p>`;
}
function drawAccount(msg) {
  const has = !!lsGet(LS.token);
  $("edpanel").innerHTML = `<h2>Saving needs a GitHub token</h2>
    <p>${has ? "A token is stored in this browser. It is sent only to api.github.com as an Authorization header — never in a URL, log, or commit." : `Fine-grained token for <b>${esc(cfg.repo)}</b> only, Contents: Read and write. Create one at <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">github.com/settings/personal-access-tokens/new</a> (90-day expiry is plenty). It stays in this browser.`}</p>
    <p>Do not paste a token on a shared computer. Other Pages sites on this <code>*.github.io</code> origin can read localStorage.</p>
    <form id="tokform"><input name="token" type="password" placeholder="github_pat_…" autocomplete="off" aria-label="GitHub token">
      <button class="go">${has ? "Replace token" : "Store token"}</button></form>
    ${msg ? `<p class="msg">${msg}</p>` : ""}
    <p><button type="button" data-act="signout">Leave edit mode on this device</button> <button type="button" data-act="close">Close</button></p>`;
}
/* The tools panel takes over the list area while open, so nothing gets squeezed. */
function closePanel() { $("edpanel").hidden = true; $("panel").classList.remove("paneling"); $("mapwrap").classList.remove("aiming"); }

/* Add a listing the feed lacks. Its location is wherever the map's crosshair sits. */
function drawAdd(msg) {
  const towns = [...$("town").options].map(o => o.value).filter(Boolean);
  $("edpanel").innerHTML = `<div class="edrow"><h2>Add a missing business</h2><button type="button" data-act="close">Cancel</button></div>
    <p>Move the map until the crosshair sits on the building. Searching the list for a neighbor and tapping it gets you close.</p>
    <form id="addform" class="ed">
      <label>Name <input name="name" required autocomplete="off"></label>
      <label>Group <select name="group">${DATA.groups.map(g => `<option${g === "Professional Services" ? " selected" : ""}>${esc(g)}</option>`).join("")}</select></label>
      <label>Kind <input name="category" list="kinds" autocomplete="off" placeholder="professional service"></label>
      <label>Street <input name="address" autocomplete="off"></label>
      <label>Town <select name="town">${towns.map(t => `<option>${esc(t)}</option>`).join("")}</select></label>
      <label>Web <input name="website" type="url" placeholder="https://" autocomplete="off"></label>
      <label>Phone <input name="phone" type="tel" autocomplete="off"></label>
      <label>Note <input name="notes" autocomplete="off" placeholder="Shown on the public listing"></label>
      <div class="edacts"><button class="go">Add at the crosshair</button><small id="addpos"></small></div>
      ${msg ? `<p class="msg">${msg}</p>` : ""}
    </form>`;
  const show = () => { const c = map?.getCenter(), el = $("addpos"); if (c && el) el.textContent = `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`; };
  show(); if (map && !ed.aimHooked) { map.on("move", show); ed.aimHooked = true; ed.showAim = show; }
}
function onAddSubmit(e) {
  const f = Object.fromEntries([...new FormData(e.target)].map(([k, v]) => [k, String(v).trim()]));
  if (!map) return drawAdd("The map is not available, so there is no location to use.");
  if (!f.name) return;
  const c = map.getCenter();
  let id = "manual-" + slug(f.name), n = 2;
  while (ed.orig.has(id) || ed.pending.adds[id]) id = `manual-${slug(f.name)}-${n++}`;
  ed.log.push(JSON.stringify(ed.pending));
  ed.pending.adds[id] = { ...f, category: f.category.toLowerCase(), lat: +c.lat.toFixed(6), lng: +c.lng.toFixed(6) };
  ed.toast = `Added ${esc(f.name)}. Save to publish it.`;
  closePanel(); applyEdits();
  state.q = ""; $("q").value = ""; select(id, false);
}
function openPanel(view) {
  const p = $("edpanel");
  p.hidden = false; p.dataset.view = view; $("panel").classList.add("paneling");
  $("mapwrap").classList.toggle("aiming", view === "add");
  view === "patterns" ? drawPatterns() : view === "add" ? drawAdd() : drawAccount();
}
function togglePanel(view) {
  const p = $("edpanel");
  if (!p.hidden && p.dataset.view === view) closePanel(); else openPanel(view);
}
function onPanelClick(e) {
  const act = e.target.dataset.act;
  if (e.target.dataset.rule) applyRuleButton(e.target);
  if (act === "close") closePanel();
  if (act === "account") openPanel("account");
  if (act === "add") openPanel("add");
  if (act === "leastcertain") { state.sort = "conf"; $("sort").value = "conf"; closePanel(); reset(); }
  if (act === "signout") { [LS.token, LS.on].forEach(k => lsSet(k, null)); location.href = location.pathname; }
}
async function onTokenSubmit(e) {
  e.preventDefault();
  if (e.target.id === "addform") return onAddSubmit(e);
  const token = new FormData(e.target).get("token").trim(); if (!token) return;
  if (!/^(github_pat_|ghp_)/.test(token)) {
    drawAccount("That does not look like a GitHub token (it should start with github_pat_ or ghp_). Nothing was stored.");
    return;
  }
  try { await gh(token, `/repos/${cfg.repo}/contents/overrides.csv?ref=${cfg.branch || "main"}`); lsSet(LS.token, token); drawAccount("Token works. You can save now."); }
  catch (err) { drawAccount(`GitHub rejected that token: ${esc(err.message)}`); }
}

/* Save: one commit to overrides.csv. Token is only sent here, as Authorization, to api.github.com. */
async function gh(token, path, opts = {}) {
  const allowed = `/repos/${cfg.repo}/contents/overrides.csv`;
  if (!path.startsWith(allowed)) throw new Error("unexpected GitHub path");
  const url = API + path;
  if (!url.startsWith(API + "/repos/")) throw new Error("unexpected GitHub URL");
  const r = await fetch(url, { ...opts, headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${token}`, "X-GitHub-Api-Version": "2022-11-28" } });
  if (!r.ok) throw new Error(`${r.status} ${(await r.json().catch(() => ({}))).message || r.statusText}`);
  return r.json();
}
const b64decode = s => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, "")), c => c.charCodeAt(0)));
const b64encode = s => { let b = ""; new TextEncoder().encode(s).forEach(c => b += String.fromCharCode(c)); return btoa(b); };

function parseCsv(text) {
  const rows = []; let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(cell); cell = ""; if (row.some(x => x !== "")) rows.push(row); row = []; }
    else cell += c;
  }
  row.push(cell); if (row.some(x => x !== "")) rows.push(row);
  return rows;
}
const csvCell = v => { const s = String(v ?? ""); return /[",\r\n]|^\s|\s$/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };

function mergeCsv(text, edits) {
  const raw = parseCsv(text), header = raw[0].map(h => h.trim());
  if (!header.includes("flag")) header.push("flag");
  let rows = raw.slice(1).map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""])));
  const isRule = r => r.action === "rule-group" || r.action === "rule-hide";

  for (const [kind, rule] of Object.entries(edits.rules)) {
    rows = rows.filter(r => !(isRule(r) && r.category.trim().toLowerCase() === kind));
    rows.push(rule.hide ? { action: "rule-hide", category: kind } : { action: "rule-group", category: kind, group: rule.group });
  }
  for (const [id, a] of Object.entries(edits.adds || {})) {
    rows = rows.filter(r => !(r.id === id && r.action === "add"));
    rows.push({ action: "add", id, ...a });
  }
  for (const [id, p] of Object.entries(edits.listings)) {
    const added = rows.find(r => r.id === id && r.action === "add");
    if (typeof p.hide === "string") {
      rows = rows.filter(r => !(r.id === id && !isRule(r)));
      rows.push({ action: "hide", id, name: ed.orig.get(id)?.name || "", notes: p.hide });
      continue;
    }
    if (p.hide === false) rows = rows.filter(r => !(r.id === id && r.action === "hide"));
    let row = added || rows.find(r => r.id === id && r.action === "edit");
    // An edit row, even an empty one, also lifts a kind-wide hide off this listing.
    if (!row) { row = { action: "edit", id }; rows.push(row); }
    for (const k of ["group", "category", "notes", "flag"]) if (k in p) row[k] = p[k] === "" ? (added ? "" : "-") : p[k];
  }
  return [header.join(","), ...rows.map(r => header.map(h => csvCell(r[h])).join(","))].join("\n") + "\n";
}

async function save() {
  const token = lsGet(LS.token);
  if (!token) { openPanel("account"); drawAccount("Store a token first. Your changes stay staged here."); return; }
  ed.busy = true; drawBar();
  const path = `/repos/${cfg.repo}/contents/overrides.csv`, branch = cfg.branch || "main", n = count(ed.pending);
  try {
    for (let attempt = 0; ; attempt++) {
      const file = await gh(token, `${path}?ref=${branch}`);
      const body = { message: `Directory edits: ${n} ${n === 1 ? "change" : "changes"}`, content: b64encode(mergeCsv(b64decode(file.content), ed.pending)), sha: file.sha, branch };
      try { await gh(token, path, { method: "PUT", body: JSON.stringify(body) }); break; }
      catch (err) { if (attempt || !/^409/.test(err.message)) throw err; }
    }
    ed.saved.push({ at: new Date().toISOString(), edits: ed.pending }); lsSet(LS.saved, ed.saved);
    ed.pending = emptyEdits(); ed.log = [];
    ed.toast = `Saved ${n} ${n === 1 ? "change" : "changes"}. The public page rebuilds in a few minutes.`;
  } catch (err) {
    ed.toast = `Save failed: ${esc(err.message)}. Your changes are still staged.`;
  }
  ed.busy = false; applyEdits();
}

const ED_CSS = `
  #panel.paneling > #filters, #panel.paneling > #status, #panel.paneling > #body, #panel.paneling > footer { display: none; }
  #mapwrap.aiming::after { content: ""; position: absolute; left: 50%; top: 50%; width: 28px; height: 28px; margin: -14px 0 0 -14px; pointer-events: none; z-index: 2;
    background: linear-gradient(var(--maroon), var(--maroon)) center / 2px 100% no-repeat, linear-gradient(var(--maroon), var(--maroon)) center / 100% 2px no-repeat; }
  #addform { border-top: 0; padding-top: 0; }
  #edbar { padding: 6px 20px; background: #fff7e0; border-bottom: 1px solid #e3cf8f; font-size: 13px; }
  .edrow { display: flex; flex-wrap: wrap; gap: 6px 10px; justify-content: space-between; align-items: center; }
  .edrow.sub { margin-top: 6px; justify-content: flex-start; color: var(--lichen); }
  .edrow.sub label { display: inline-flex; gap: 5px; align-items: center; }
  #edbar button, #edpanel button, form.ed button, form.ed select, form.ed input, form.ed textarea, #edbar select, #edpanel input {
    font: inherit; font-size: 13px; padding: 5px 9px; border: 1px solid var(--spruce); border-radius: 3px; background: #fff; color: var(--spruce); }
  #edbar button, #edpanel button, form.ed button { cursor: pointer; }
  #edbar button:disabled { opacity: .45; cursor: default; }
  #edbar .go, #edpanel .go { background: var(--maroon); border-color: var(--maroon); color: #fff; }
  .edtoast { margin-top: 6px; padding: 6px 8px; background: #fff; border-left: 3px solid var(--maroon); }
  .edrow { flex-wrap: nowrap; } .edrow > span { display: flex; gap: 6px; flex: none; }
  .edview { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; margin: 8px 0 12px; }
  .edview label { display: inline-flex; gap: 6px; align-items: center; } #edpanel select { font: inherit; font-size: 13px; padding: 5px 6px; }
  #edpanel { flex: 1; min-height: 0; padding: 12px 20px; overflow-y: auto; background: var(--chalk); border-bottom: 1px solid var(--stone); font-size: 14px; }
  #edpanel h2 { margin: 0 0 6px; font-size: 16px; font-stretch: 78%; }
  #edpanel p, #edpanel ul { margin: 0 0 8px; } #edpanel ul { padding-left: 18px; } #edpanel li { margin-bottom: 6px; }
  #edpanel input[type="password"] { width: 100%; margin-bottom: 6px; } #edpanel .msg { color: var(--maroon); }
  form.ed { display: grid; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--stone); }
  form.ed label { display: grid; grid-template-columns: 48px 1fr; gap: 8px; align-items: center; font-size: 13px; color: var(--lichen); }
  form.ed textarea { resize: vertical; } form.ed select, form.ed input { min-width: 0; width: 100%; }
  .flags { display: flex; flex-wrap: wrap; gap: 5px; }
  .flags button { border-style: dashed; }
  .flags button[aria-pressed="true"] { border-style: solid; background: var(--spruce); color: var(--chalk); }
  .edacts { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; } .edacts select { width: auto; } .edacts small { color: var(--lichen); }
  .tag { margin-left: 6px; padding: 0 5px; font-size: 11px; font-weight: 700; font-stretch: 100%; border: 1px solid var(--spruce); border-radius: 2px; vertical-align: 2px; white-space: nowrap; }
  .tag.hid { background: var(--spruce); color: var(--chalk); } .tag.fl { border-color: var(--maroon); color: var(--maroon); }
  @media (max-width: 820px) { #edbar, #edpanel { padding-left: 14px; padding-right: 14px; } }
`;
