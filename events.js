/* Month/list calendar for events/index.html. Reads JSON from data-src. */
(function () {
  const root = document.getElementById("calendar");
  if (!root) return;

  const src = root.dataset.src || "../events.json";
  const TZ = "America/New_York";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
  const pad = n => String(n).padStart(2, "0");
  const parse = iso => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
  };
  const easternYmd = d => new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit"
  }).format(d);
  const monthName = (y, m) => new Date(y, m, 1).toLocaleString("en-US", { month: "long", year: "numeric" });
  const dayName = d => d.toLocaleString("en-US", {
    timeZone: TZ, weekday: "long", month: "long", day: "numeric", year: "numeric"
  });
  const timeOf = iso => {
    const d = parse(iso);
    if (!d) return "";
    if (/T\d{2}:\d{2}/.test(iso)) {
      return d.toLocaleTimeString("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
    }
    return "";
  };

  const state = { view: "month", cat: "", range: "upcoming", cursor: new Date() };
  state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth(), 1);
  let events = [];

  function readUrl() {
    const p = new URLSearchParams(location.search);
    if (p.get("view") === "list" || p.get("view") === "month") state.view = p.get("view");
    if (p.get("cat")) state.cat = p.get("cat");
    if (["upcoming", "month", "all"].includes(p.get("range"))) state.range = p.get("range");
    const m = p.get("month");
    if (m && /^\d{4}-\d{2}$/.test(m)) {
      const [y, mo] = m.split("-").map(Number);
      state.cursor = new Date(y, mo - 1, 1);
    }
  }
  function writeUrl() {
    const p = new URLSearchParams();
    if (state.view !== "month") p.set("view", state.view);
    if (state.cat) p.set("cat", state.cat);
    if (state.range !== "upcoming") p.set("range", state.range);
    p.set("month", `${state.cursor.getFullYear()}-${pad(state.cursor.getMonth() + 1)}`);
    const s = p.toString();
    try { history.replaceState(null, "", s ? "?" + s : location.pathname); } catch {}
  }

  function inRange(ev, now) {
    const start = parse(ev.start);
    if (!start) return false;
    if (state.range === "all") return true;
    if (state.range === "month") {
      const [ey, em] = easternYmd(start).split("-").map(Number);
      return ey === state.cursor.getFullYear() && em === state.cursor.getMonth() + 1;
    }
    const end = parse(ev.end || ev.start);
    return (end || start) >= new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }
  function filtered(now) {
    return events.filter(ev => (!state.cat || ev.category === state.cat) && inRange(ev, now));
  }

  function eventHref(ev) {
    return (ev.slug || ev.id) + "/";
  }

  function drawMonth(now, rows) {
    const y = state.cursor.getFullYear(), m = state.cursor.getMonth();
    const first = new Date(y, m, 1);
    const startWeek = first.getDay();
    const days = new Date(y, m + 1, 0).getDate();
    const byDay = {};
    rows.forEach(ev => {
      const d = parse(ev.start);
      if (!d) return;
      const [ey, em, ed] = easternYmd(d).split("-").map(Number);
      if (ey !== y || em !== m + 1) return;
      (byDay[ed] || (byDay[ed] = [])).push(ev);
    });
    const dow = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    let html = `<div class="cal-nav">
      <button type="button" data-shift="-1">Previous</button>
      <h2>${esc(monthName(y, m))}</h2>
      <button type="button" data-shift="1">Next</button>
    </div>
    <table class="cal" role="grid" aria-label="Events by day">
      <thead><tr>${dow.map(d => `<th>${d}</th>`).join("")}</tr></thead><tbody>`;
    let day = 1 - startWeek;
    for (let w = 0; w < 6; w++) {
      html += "<tr>";
      for (let i = 0; i < 7; i++, day++) {
        if (day < 1 || day > days) { html += `<td class="out"></td>`; continue; }
        const today = easternYmd(now) === `${y}-${pad(m + 1)}-${pad(day)}`;
        const list = byDay[day] || [];
        html += `<td class="${today ? "today" : ""}"><span class="num">${day}</span>`;
        list.forEach(ev => {
          html += `<a class="ev${ev.example ? " sample" : ""}" href="${esc(eventHref(ev))}">${esc(ev.title)}</a>`;
        });
        html += "</td>";
      }
      html += "</tr>";
      if (day > days) break;
    }
    html += "</tbody></table>";
    return html;
  }

  function drawList(now, rows) {
    rows = rows.slice().sort((a, b) => String(a.start).localeCompare(String(b.start)));
    if (!rows.length) return `<p class="empty">Nothing in this view. Try another category, or look at the whole month.</p>`;
    let html = `<ul class="event-list">`, last = "";
    rows.forEach(ev => {
      const d = parse(ev.start);
      const label = d ? dayName(d) : "Date to be set";
      if (label !== last) { html += `<li class="day-label">${esc(label)}</li>`; last = label; }
      const when = [timeOf(ev.start), timeOf(ev.end)].filter(Boolean);
      const t = when.length === 2 ? when.join(" – ") : when[0] || "";
      html += `<li><a class="event-card" href="${esc(eventHref(ev))}">
        <h3>${esc(ev.title)}${ev.example ? '<span class="badge">Sample</span>' : ""}</h3>
        <p>${esc([t, ev.venue, ev.town, ev.category].filter(Boolean).join(" · "))}</p>
      </a></li>`;
    });
    return html + "</ul>";
  }

  function render() {
    const now = new Date();
    const rows = filtered(now);
    const cats = [...new Set(events.map(e => e.category).filter(Boolean))].sort();
    const toolbar = `<div class="filters">
      <div class="view-toggle" role="group" aria-label="Calendar view">
        <button type="button" data-view="month" aria-pressed="${state.view === "month"}">Month</button>
        <button type="button" data-view="list" aria-pressed="${state.view === "list"}">List</button>
      </div>
      <label>Category
        <select id="cal-cat">
          <option value="">All</option>
          ${cats.map(c => `<option ${c === state.cat ? "selected" : ""}>${esc(c)}</option>`).join("")}
        </select>
      </label>
      <label>When
        <select id="cal-range">
          <option value="upcoming"${state.range === "upcoming" ? " selected" : ""}>Upcoming</option>
          <option value="month"${state.range === "month" ? " selected" : ""}>This month on the grid</option>
          <option value="all"${state.range === "all" ? " selected" : ""}>All dates</option>
        </select>
      </label>
    </div>`;
    const body = state.view === "list" ? drawList(now, rows) : drawMonth(now, rows);
    root.innerHTML = toolbar + body;
    writeUrl();
  }

  root.addEventListener("click", e => {
    const view = e.target.closest("[data-view]");
    if (view) { state.view = view.dataset.view; render(); return; }
    const shift = e.target.closest("[data-shift]");
    if (shift) {
      state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth() + Number(shift.dataset.shift), 1);
      render();
    }
  });
  root.addEventListener("change", e => {
    if (e.target.id === "cal-cat") { state.cat = e.target.value; render(); }
    if (e.target.id === "cal-range") { state.range = e.target.value; render(); }
  });

  readUrl();
  fetch(src, { cache: "no-cache" })
    .then(r => { if (!r.ok) throw new Error("Could not load events"); return r.json(); })
    .then(data => {
      events = (data.events || []).filter(ev => ev.title && ev.start);
      render();
    })
    .catch(err => {
      root.innerHTML = `<p class="empty">${esc(err.message)}. The list below is the static copy.</p>`;
    });
})();
