/* ============ RealMobile Benchmark — app logic ============ */
(function () {
  "use strict";

  /* ---------- helpers ---------- */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (v) => (v == null ? "—" : v.toFixed(1) + "%");

  /* ==========================================================
     LEADERBOARD
     ========================================================== */
  let LB = [], DOM = [];
  const lbState = { filter: "all", sort: "success" };

  function renderLeaderboard() {
    const body = $("#lbBody");
    if (!body) return;
    let rows = LB.filter((m) => lbState.filter === "all" || m.type === lbState.filter);
    const key = lbState.sort;
    rows.sort((a, b) => (b[key] == null ? -1 : b[key]) - (a[key] == null ? -1 : a[key]));

    const max = Math.max(...rows.map((m) => m[key] || 0)) || 1;
    const medals = ["🥇", "🥈", "🥉"];
    body.innerHTML = rows.map((m, i) => {
      const val = m[key];
      const barW = val == null ? 0 : Math.round((val / max) * 72);
      const typeTag = m.type === "ours" ? '<span class="tag ours">Ours</span>'
        : m.type === "proprietary" ? '<span class="tag proprietary">Proprietary</span>'
        : '<span class="tag opensource">Open-source</span>';
      const rank = i < 3 ? `<span class="medal">${medals[i]}</span>` : (i + 1);
      return `<tr class="${m.type === "ours" ? "ours-row" : ""}">
        <td class="rank-col">${rank}</td>
        <td class="model-name">${esc(m.model)}</td>
        <td>${typeTag}</td>
        <td class="num">${cell(m.success, key === "success", barW, max, m.success)}</td>
        <td class="num">${cell(m.progress, key === "progress", barW, max, m.progress)}</td>
      </tr>`;
    }).join("");
  }

  function cell(val, isSortCol, barW, max, raw) {
    if (val == null) return "—";
    if (!isSortCol) return pct(val);
    const w = Math.round((val / max) * 72);
    return `<span class="bar-cell"><span class="mini-bar" style="width:${w}px"></span>${pct(val)}</span>`;
  }

  function renderDomains() {
    const body = $("#domBody");
    if (!body) return;
    const rows = DOM.slice().sort((a, b) =>
      (b.foundation + b.safety + b.memory + b.reasoning) - (a.foundation + a.safety + a.memory + a.reasoning));
    body.innerHTML = rows.map((m) => `<tr class="${m.type === "ours" ? "ours-row" : ""}">
      <td class="model-name">${esc(m.model)}</td>
      <td class="num">${pct(m.foundation)}</td>
      <td class="num">${pct(m.safety)}</td>
      <td class="num">${pct(m.memory)}</td>
      <td class="num">${pct(m.reasoning)}</td>
    </tr>`).join("");
  }

  function wireLbControls() {
    $$("#lbFilter .seg-btn").forEach((b) => b.addEventListener("click", () => {
      $$("#lbFilter .seg-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active"); lbState.filter = b.dataset.f; renderLeaderboard();
    }));
    $$("#lbSort .seg-btn").forEach((b) => b.addEventListener("click", () => {
      $$("#lbSort .seg-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active"); lbState.sort = b.dataset.s; renderLeaderboard();
    }));
  }

  /* ==========================================================
     TASK EXPLORER
     ========================================================== */
  let TASKS = [], ALL_APPS = [];
  const exState = { q: "", app: "all", multiOnly: false };

  function srClass(v) { return v >= 0.999 ? "full" : v >= 0.5 ? "mid" : "low"; }

  function renderTasks() {
    const body = $("#taskBody");
    if (!body) return;
    const q = exState.q.trim().toLowerCase();
    let rows = TASKS.filter((t) => {
      if (exState.multiOnly && (t.apps || []).length < 2) return false;
      if (exState.app !== "all" && !(t.apps || []).includes(exState.app)) return false;
      if (q) {
        const hay = (t.query + " " + (t.apps || []).join(" ")).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    $("#taskCount").textContent =
      `${rows.length} of ${TASKS.length} tasks` +
      (exState.app !== "all" ? ` · ${exState.app}` : "") +
      (exState.multiOnly ? " · multi-app" : "");

    body.innerHTML = rows.map((t) => {
      const multi = (t.apps || []).length > 1;
      const pills = (t.apps || []).map((a) =>
        `<span class="app-pill${multi ? " multi" : ""}">${esc(a)}</span>`).join("");
      const nSub = countSubgoals(t.steprules);
      return `<tr data-id="${t.id}">
        <td class="rank-col">${t.id}</td>
        <td class="q">${esc(t.query)}</td>
        <td><div class="app-pills">${pills}</div></td>
        <td class="num">${nSub || "—"}</td>
      </tr>`;
    }).join("");

    $$("#taskBody tr").forEach((tr) =>
      tr.addEventListener("click", () => openTask(+tr.dataset.id)));
  }

  function countSubgoals(rules) {
    if (!rules) return 0;
    const scores = new Set();
    rules.split(/\n/).forEach((ln) => {
      const m = ln.match(/总分\s*[:：]\s*([0-9.]+)/);
      if (m) scores.add(m[1]);
    });
    return scores.size;
  }

  function parseRules(rules) {
    // Returns {steps:[{score,text}], veto:[...]}
    const out = { steps: [], veto: [] };
    if (!rules) return out;
    const lines = rules.split(/\n/).map((l) => l.trim()).filter(Boolean);
    let mode = "step";
    for (const ln of lines) {
      if (/^评分规则/.test(ln)) { mode = "step"; continue; }
      if (/^一票否决/.test(ln)) { mode = "veto"; continue; }
      const m = ln.match(/^(.*?)\s*→\s*总分\s*[:：]\s*([0-9.]+)\s*$/);
      if (m) {
        const text = m[1].trim();
        if (mode === "veto") out.veto.push(text);
        else out.steps.push({ text, score: m[2] });
        continue;
      }
      if (mode === "veto") {
        if (/^暂无$/.test(ln)) continue;
        out.veto.push(ln);
      } else if (out.steps.length) {
        // continuation of previous step
        out.steps[out.steps.length - 1].text += " " + ln;
      }
    }
    return out;
  }

  function openTask(id) {
    const t = TASKS.find((x) => x.id === id);
    if (!t) return;
    const multi = (t.apps || []).length > 1;
    const pills = (t.apps || []).map((a) =>
      `<span class="app-pill${multi ? " multi" : ""}">${esc(a)}</span>`).join("");
    const parsed = parseRules(t.steprules);

    let rubric;
    if (parsed.steps.length) {
      rubric = `<div class="m-rules"><h4>Sub-goal rubric</h4>` +
        parsed.steps.map((s) =>
          `<div class="rule-step"><span class="rule-score">${s.score}</span>
             <span class="rule-text">${esc(s.text)}</span></div>`).join("") +
        (parsed.veto.length ? parsed.veto.map((v) =>
          `<div class="rule-step rule-veto"><span class="rule-score">veto</span>
             <span class="rule-text">${esc(v)}</span></div>`).join("") : "") +
        `</div>`;
    } else if (t.steprules) {
      rubric = `<div class="m-rules"><h4>Scoring rubric</h4><pre class="m-raw">${esc(t.steprules)}</pre></div>`;
    } else {
      rubric = `<div class="m-rules"><h4>Scoring rubric</h4>
        <p style="color:var(--muted)">Rubric available in the benchmark repository.</p></div>`;
    }

    $("#modalBody").innerHTML = `
      <div class="m-id">Task #${t.id}</div>
      <h3>${esc(t.query)}</h3>
      <div class="m-meta">${pills}</div>
      ${rubric}`;
    $("#taskModal").classList.add("open");
    $("#taskModal").setAttribute("aria-hidden", "false");
  }

  function closeModal() {
    $("#taskModal").classList.remove("open");
    $("#taskModal").setAttribute("aria-hidden", "true");
  }

  function buildAppFilter() {
    const counts = {};
    TASKS.forEach((t) => (t.apps || []).forEach((a) => (counts[a] = (counts[a] || 0) + 1)));
    ALL_APPS = Object.keys(counts).filter((a) => a !== "Other")
      .sort((a, b) => counts[b] - counts[a]);
    const wrap = $("#appFilter");
    wrap.innerHTML =
      `<button class="seg-btn active" data-app="all">All apps</button>` +
      ALL_APPS.slice(0, 9).map((a) =>
        `<button class="seg-btn" data-app="${esc(a)}">${esc(a)} <span style="opacity:.6">${counts[a]}</span></button>`).join("");
    $$("#appFilter .seg-btn").forEach((b) => b.addEventListener("click", () => {
      $$("#appFilter .seg-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active"); exState.app = b.dataset.app; renderTasks();
    }));
  }

  function wireExplorer() {
    $("#taskSearch").addEventListener("input", (e) => { exState.q = e.target.value; renderTasks(); });
    $("#multiOnly").addEventListener("change", (e) => { exState.multiOnly = e.target.checked; renderTasks(); });
    $$("#taskModal [data-close]").forEach((el) => el.addEventListener("click", closeModal));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  }

  /* ==========================================================
     BOOT
     ========================================================== */
  async function boot() {
    try {
      const [lb, tf] = await Promise.all([
        fetch("leaderboard.json?v=5").then((r) => r.json()),
        fetch("tasks.json?v=5").then((r) => r.json()),
      ]);
      LB = lb.leaderboard || []; DOM = lb.domains || [];
      TASKS = (tf.tasks || []).sort((a, b) => a.id - b.id);
      renderLeaderboard(); renderDomains(); wireLbControls();
      buildAppFilter(); renderTasks(); wireExplorer();
    } catch (e) {
      console.error("RealMobile data load failed:", e);
    }
  }
  document.addEventListener("DOMContentLoaded", boot);

  /* citation copy (global for inline onclick) */
  window.copyCite = function (btn) {
    const txt = $("#bibtex").textContent;
    navigator.clipboard.writeText(txt).then(() => {
      const old = btn.textContent; btn.textContent = "Copied!";
      setTimeout(() => (btn.textContent = old), 1600);
    });
  };
})();
