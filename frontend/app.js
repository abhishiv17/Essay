// Essay Feedback Coach: frontend (no build step). Talks to the FastAPI routes in app.py.
// Sections: utils, storage, API + friendly errors, init, input, onboarding tour, results, features.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const MIN_WORDS = 50;
const MAX_WORDS = 3000;
const state = { rubric: null, samples: [], result: null, activeTab: "essay", notes: [], errorFilter: "all" };

const escapeHtml = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const ERROR_LABELS = {
  grammar: "Grammar", spelling: "Spelling", punctuation: "Punctuation",
  capitalization: "Capitalization", word_choice: "Word choice", sentence_structure: "Sentence structure",
};

// ---------- Browser storage (per-viewer conveniences only; never required) ----------

const store = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem(`efc.${key}`);
      return v === null ? fallback : JSON.parse(v);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`efc.${key}`, JSON.stringify(value)); return true; } catch { return false; }
  },
};

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 2600);
}

// ---------- API + friendly errors ----------

class ApiError extends Error {
  constructor(status, detail) { super(detail); this.status = status; this.detail = detail; }
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const code = $("#access-code").value.trim();
  if (code) headers["X-Access-Code"] = code;
  let res;
  try {
    res = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError(0, "network");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return body;
}

function friendlyError(err) {
  const d = String(err.detail || err.message || "").toLowerCase();
  if (err.status === 0) return { title: "Can't reach the app server", text: "Check that the server is running (uvicorn app:app --reload), then try again." };
  if (err.status === 401) {
    $("#access-wrap").hidden = false;
    $("#access-code").focus();
    return { title: "Access code needed", text: "Enter the access code your team shared, then press Get feedback again." };
  }
  if (err.status === 422) return { title: "Please check the essay", text: err.detail };
  if (d.includes("rate limit") || d.includes("429")) return { title: "The free AI is busy right now", text: "Free models allow a limited number of requests per minute. Wait about a minute and try again.", raw: err.detail };
  if (d.includes("no api key") || d.includes("api key")) return { title: "The AI isn't set up yet", text: "Add GEMINI_API_KEY and GROQ_API_KEY to the .env file (see README), then restart the server.", raw: err.detail };
  if (d.includes("invalid json") || d.includes("cut off")) return { title: "The AI's answer came back incomplete", text: "This happens occasionally with free models. Please try again.", raw: err.detail };
  return { title: "The AI couldn't finish this essay", text: "Please try again in a moment.", raw: err.detail };
}

function showError(err) {
  const el = $("#error");
  if (!err) { el.hidden = true; el.innerHTML = ""; return; }
  const f = friendlyError(err);
  el.innerHTML = `<b>${escapeHtml(f.title)}</b>${escapeHtml(f.text)}` +
    (f.raw ? `<details><summary>Technical details</summary>${escapeHtml(f.raw)}</details>` : "");
  el.hidden = false;
}

// ---------- Init ----------

async function init() {
  const [health, rubric, samples] = await Promise.allSettled([api("/api/health"), api("/api/rubric"), api("/api/samples")]);

  const badge = $("#mode-badge");
  if (health.status === "fulfilled") {
    const h = health.value;
    badge.textContent = h.mock ? "Demo mode (sample feedback)" : "AI ready";
    badge.title = h.mock ? "MOCK_LLM=1: shows canned feedback without calling a model" : `Model: ${h.model}`;
    badge.classList.add(h.mock ? "mock" : "live");
    $("#access-wrap").hidden = !h.access_code_required;
  } else {
    badge.textContent = "Server offline";
    showError(health.reason);
  }
  if (rubric.status === "fulfilled") state.rubric = rubric.value;
  if (samples.status === "fulfilled") { state.samples = samples.value; renderSamples(); }

  restoreDraft();
  renderRecent();
  $("#student-mode").checked = store.get("studentMode", false);

  // URL options (handy for demo recordings): ?notour skips the tour, ?sample=<id> loads and runs a sample.
  const params = new URLSearchParams(location.search);
  const sample = state.samples.find((x) => x.id === params.get("sample"));
  if (sample) {
    loadSample(sample);
    generate();
  } else if (!params.has("notour") && !store.get("tour.input")) {
    setTimeout(() => startTour("input"), 700);
  }
}

// ---------- Input ----------

const SAMPLE_HINTS = {
  "1_strong_argumentative": "A strong essay: see real strengths recognized",
  "2_esl_grammar_errors": "An English learner's essay: corrections with the rule explained",
  "3_generic_cliche": "Clean grammar, generic ideas: originality and argument feedback",
  "4_narrative": "A personal story: feedback adapts to the essay type",
};

function renderSamples() {
  const list = $("#sample-list");
  list.innerHTML = "";
  for (const s of state.samples) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = s.title;
    chip.title = SAMPLE_HINTS[s.id] || "";
    chip.dataset.id = s.id;
    chip.addEventListener("click", () => loadSample(s));
    list.appendChild(chip);
  }
}

function loadSample(s) {
  $("#essay").value = s.text;
  $("#essay-type").value = /narrative/i.test(s.id) ? "Narrative" : "Argumentative";
  $("#grade-level").value = /esl/i.test(s.id) ? "English language learner" : "High school (Grades 9-12)";
  $$("#sample-list .chip").forEach((c) => c.classList.toggle("active", c.dataset.id === s.id));
  onEssayChange();
  toast(`"${s.title}" loaded. Press Get feedback.`);
}

const wordCount = () => ($("#essay").value.match(/\S+/g) || []).length;

function updateWordCount() {
  const n = wordCount();
  const label = $("#word-count");
  const fill = $("#meter-fill");
  fill.style.width = `${Math.min(n / MIN_WORDS, 1) * 100}%`;
  fill.classList.toggle("ok", n >= MIN_WORDS && n <= MAX_WORDS);
  if (n === 0) label.textContent = `0 words, ${MIN_WORDS} needed`;
  else if (n < MIN_WORDS) label.textContent = `${n} words, ${MIN_WORDS - n} more needed`;
  else if (n > MAX_WORDS) label.textContent = `${n.toLocaleString()} words, the maximum is ${MAX_WORDS.toLocaleString()}`;
  else label.textContent = `${n.toLocaleString()} words, ready`;
  $("#submit").disabled = n < MIN_WORDS || n > MAX_WORDS || state.loading;
  $("#clear-essay").hidden = n === 0;
}

let draftTimer;
function onEssayChange() {
  updateWordCount();
  clearTimeout(draftTimer);
  draftTimer = setTimeout(saveDraft, 400);
}

function saveDraft() {
  store.set("draft", {
    essay: $("#essay").value, grade: $("#grade-level").value,
    type: $("#essay-type").value, assignment: $("#assignment").value,
  });
}

function restoreDraft() {
  const d = store.get("draft");
  if (d) {
    $("#essay").value = d.essay || "";
    if (d.grade) $("#grade-level").value = d.grade;
    if (d.type) $("#essay-type").value = d.type;
    if (d.assignment) { $("#assignment").value = d.assignment; $(".more").open = true; }
  }
  updateWordCount();
}

$("#essay").addEventListener("input", () => {
  $$("#sample-list .chip").forEach((c) => c.classList.remove("active"));
  onEssayChange();
});
["#grade-level", "#essay-type", "#assignment"].forEach((s) => $(s).addEventListener("change", saveDraft));
$("#clear-essay").addEventListener("click", () => { $("#essay").value = ""; onEssayChange(); $("#essay").focus(); });
$("#file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $("#essay").value = await file.text();
  onEssayChange();
  toast(`Loaded ${file.name}`);
  e.target.value = "";
});
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !$("#submit").disabled) generate();
});

$("#hero-sample").addEventListener("click", () => {
  const s = state.samples.find((x) => /esl/i.test(x.id)) || state.samples[0];
  if (s) loadSample(s);
  $("#workspace").scrollIntoView({ behavior: "smooth" });
  setTimeout(() => $("#submit").focus({ preventScroll: true }), 500);
});
$("#hero-paste").addEventListener("click", () => {
  $("#workspace").scrollIntoView({ behavior: "smooth" });
  setTimeout(() => $("#essay").focus({ preventScroll: true }), 500);
});

// ---------- Generate ----------

const PROGRESS = [
  "Reading and cleaning up the text",
  "Checking grammar and mechanics",
  "Following the structure and flow",
  "Weighing the argument and evidence",
  "Looking for original ideas and voice",
  "Double-checking every quote against the essay",
];

function setView(view) {
  document.body.classList.remove("show-hero");
  $("#empty").hidden = view !== "empty";
  $("#loading").hidden = view !== "loading";
  $("#results").hidden = view !== "results";
  document.body.classList.toggle("has-result", view !== "empty");
}

function startProgress() {
  const ol = $("#progress-steps");
  ol.innerHTML = PROGRESS.map((p) => `<li>${p}</li>`).join("");
  const items = $$("li", ol);
  let i = 0;
  items[0].classList.add("active");
  const timer = setInterval(() => {
    if (i >= items.length - 1) return;
    items[i].classList.replace("active", "done");
    items[++i].classList.add("active");
  }, 4500);
  return () => { clearInterval(timer); items.forEach((li) => { li.classList.remove("active"); li.classList.add("done"); }); };
}

async function generate() {
  showError(null);
  state.loading = true;
  $("#submit").disabled = true;
  setView("loading");
  if (window.innerWidth < 980) $("#results-card").scrollIntoView({ behavior: "smooth" });
  const stop = startProgress();
  try {
    const result = await api("/api/feedback", {
      method: "POST",
      body: JSON.stringify({
        essay: $("#essay").value.trim(),
        grade_level: $("#grade-level").value,
        essay_type: $("#essay-type").value,
        assignment_prompt: $("#assignment").value,
      }),
    });
    stop();
    showResult(result);
    saveHistory(result);
    if (!store.get("tour.results") && !new URLSearchParams(location.search).has("notour")) {
      setTimeout(() => startTour("results"), 600);
    }
  } catch (err) {
    stop();
    showError(err);
    setView(state.result ? "results" : "empty");
  } finally {
    state.loading = false;
    updateWordCount();
  }
}

$("#submit").addEventListener("click", generate);

function showResult(result) {
  state.result = result;
  state.activeTab = "essay";
  state.errorFilter = "all";
  renderResults();
  setView("results");
}

// ---------- Results ----------

const label = (key) => state.rubric?.criteria?.[key]?.label ?? key;
const SHORT = { grammar: "Grammar", coherence: "Coherence", argument: "Argument", originality: "Originality" };
const short = (key) => SHORT[key] || label(key);
const maxScore = () => state.rubric?.max ?? 5;
const scoreColor = (s) => (s <= 2 ? "var(--bad)" : s === 3 ? "var(--warn)" : "var(--good)");

function criterionTip(key, score) {
  const c = state.rubric?.criteria?.[key];
  if (!c) return "";
  return `${c.question}\n${score}/5: ${c.levels?.[score] ?? ""}`;
}

function modelName(m) {
  if (!m || m === "mock") return "sample feedback (demo mode)";
  const [provider, model] = m.split(":");
  const nice = { gemini: "Gemini", groq: "Groq", ollama: "Ollama", anthropic: "Claude" }[provider] || provider;
  return model ? `${nice} (${model.split(" ")[0]})` : nice;
}

function renderResults() {
  const { feedback: fb, verification: v } = state.result;
  const max = maxScore();
  $("#results").classList.toggle("student-mode", $("#student-mode").checked);

  $("#overall-score").textContent = `${fb.overall_score}/${max}`;
  const ring = $("#overall-ring");
  ring.style.setProperty("--pct", (fb.overall_score / max) * 100);
  ring.style.setProperty("--ring", scoreColor(fb.overall_score));
  $("#overall-summary").textContent = fb.overall_summary;

  $("#criteria-bars").innerHTML = fb.criteria
    .map((c) => `<div class="bar">
        <span class="bar-label">${escapeHtml(short(c.criterion))}
          <span class="info" title="${escapeHtml(`${label(c.criterion)}: ${criterionTip(c.criterion, c.score)}`)}">i</span></span>
        <div class="bar-track"><div class="bar-fill s${c.score}" style="width:${(c.score / max) * 100}%"></div></div>
        <b>${c.score}/${max}</b></div>`)
    .join("");

  $("#top-strengths").innerHTML = fb.top_strengths.map((s) => `<li>${escapeHtml(s)}</li>`).join("");
  $("#top-priorities").innerHTML = fb.top_priorities.map((s) => `<li>${escapeHtml(s)}</li>`).join("");
  $("#exercise").textContent = fb.next_step_exercise;

  const verified = v.items_checked - v.items_unverified;
  $("#verification").textContent =
    `${verified} of ${v.items_checked} quotes checked against the essay` +
    `${v.dropped && v.items_unverified ? ` (${v.items_unverified} removed)` : ""} · ${modelName(state.result.model)}` +
    `${state.result.from_cache ? " · instant (saved result)" : ""}`;

  renderTabs();
}

function renderTabs() {
  const fb = state.result.feedback;
  const tabs = [
    { id: "essay", name: "Highlights" },
    ...fb.criteria.map((c) => ({ id: c.criterion, name: short(c.criterion), pill: `${c.score}` })),
    { id: "corrections", name: "Corrections", pill: `${fb.grammar_errors.length}` },
    { id: "stats", name: "Readability" },
  ];
  $("#tabs").innerHTML = tabs
    .map((t) => `<button class="tab" role="tab" type="button" data-tab="${t.id}" aria-selected="${t.id === state.activeTab}">
        ${escapeHtml(t.name)}${t.pill ? `<span class="pill">${t.pill}</span>` : ""}</button>`)
    .join("");

  const body = $("#tab-body");
  if (state.activeTab === "essay") body.innerHTML = annotatedEssay();
  else if (state.activeTab === "corrections") body.innerHTML = correctionsView();
  else if (state.activeTab === "stats") body.innerHTML = statsView();
  else body.innerHTML = criterionView(fb.criteria.find((c) => c.criterion === state.activeTab));
}

$("#tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (!tab) return;
  state.activeTab = tab.dataset.tab;
  renderTabs();
});

// Wrap an answer so "Try it yourself" mode can hide it behind a button.
const answer = (html, btn = "Show answer") =>
  `<span class="reveal-wrap"><span class="answer">${html}</span><button type="button" class="reveal-btn">${btn}</button></span>`;

// Find a quote in the essay: case-insensitive, whitespace-tolerant, supports "..." elisions.
function findSpan(quote, text) {
  const parts = (quote || "").replace(/^["'`\s]+|["'`\s]+$/g, "").split(/\s*(?:\.\.\.)\s*/).filter((p) => p.trim());
  const toPattern = (s) => s.trim().split(/\s+/).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+");
  let start = null;
  let pos = 0;
  for (const part of parts) {
    let m = null;
    for (const candidate of [part, part.replace(/[.,;:!?]+$/, "")]) {
      if (!candidate.trim()) continue;
      const re = new RegExp(toPattern(candidate), "gi");
      re.lastIndex = pos;
      m = re.exec(text);
      if (m) break;
    }
    if (!m) return null;
    if (start === null) start = m.index;
    pos = m.index + m[0].length;
  }
  return start === null ? null : [start, pos];
}

function annotatedEssay() {
  const { essay, feedback: fb } = state.result;
  const notes = [];
  // Priority when spans overlap: errors > improvements > strengths.
  for (const e of fb.grammar_errors)
    notes.push({ kind: "error", quote: e.quote, html: `<b>${escapeHtml(ERROR_LABELS[e.error_type] || e.error_type)}:</b> "${escapeHtml(e.quote)}" ${answer(`&rarr; <b>${escapeHtml(e.correction)}</b>`)}<br>${escapeHtml(e.explanation)}` });
  for (const c of fb.criteria)
    for (const i of c.improvements)
      notes.push({ kind: "improvement", quote: i.quote, html: `<b>${escapeHtml(label(c.criterion))}:</b> ${escapeHtml(i.issue)}<br><b>Try:</b> ${escapeHtml(i.suggestion)}${i.example_rewrite ? `<br>${answer(`<i>${escapeHtml(i.example_rewrite)}</i>`, "Show example")}` : ""}` });
  for (const c of fb.criteria)
    for (const s of c.strengths)
      notes.push({ kind: "strength", quote: s.quote, html: `<b>${escapeHtml(label(c.criterion))}:</b> ${escapeHtml(s.comment)}` });

  const spans = [];
  notes.forEach((n, idx) => {
    const span = n.quote && findSpan(n.quote, essay);
    if (!span) return;
    if (!spans.some((s) => span[0] < s.end && s.start < span[1])) spans.push({ start: span[0], end: span[1], kind: n.kind, idx });
  });
  spans.sort((a, b) => a.start - b.start);
  state.notes = notes;

  let html = "";
  let cursor = 0;
  for (const s of spans) {
    html += escapeHtml(essay.slice(cursor, s.start));
    html += `<mark class="${s.kind}" data-note="${s.idx}" tabindex="0">${escapeHtml(essay.slice(s.start, s.end))}</mark>`;
    cursor = s.end;
  }
  html += escapeHtml(essay.slice(cursor));

  const count = (k) => spans.filter((s) => s.kind === k).length;
  return `<div class="legend">
      <span><i style="background:var(--bad)"></i>${count("error")} corrections</span>
      <span><i style="background:var(--warn)"></i>${count("improvement")} to improve</span>
      <span><i style="background:var(--good)"></i>${count("strength")} strengths</span>
      <span>Click any highlight for the comment</span></div>
    <div class="essay-view">${html}</div>
    <div id="note-box" class="note-box"></div>`;
}

$("#tab-body").addEventListener("click", (e) => {
  const mark = e.target.closest("mark[data-note]");
  if (mark) showNote(mark);
  const chip = e.target.closest("[data-filter]");
  if (chip) { state.errorFilter = chip.dataset.filter; renderTabs(); }
  const goto = e.target.closest("[data-goto]");
  if (goto) { state.activeTab = goto.dataset.goto; renderTabs(); }
  const speakBtn = e.target.closest("[data-speak]");
  if (speakBtn) speak(speakBtn.dataset.speak, speakBtn);
});
$("#tab-body").addEventListener("keydown", (e) => {
  const mark = e.target.closest("mark[data-note]");
  if (mark && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); showNote(mark); }
});
function showNote(mark) {
  $$("mark.active").forEach((x) => x.classList.remove("active"));
  mark.classList.add("active");
  $("#note-box").innerHTML = state.notes[mark.dataset.note].html;
}

// "Try it yourself" reveal buttons work everywhere in the results.
$("#results").addEventListener("click", (e) => {
  const btn = e.target.closest(".reveal-btn");
  if (btn) btn.closest(".reveal-wrap").classList.add("revealed");
});
$("#student-mode").addEventListener("change", (e) => {
  store.set("studentMode", e.target.checked);
  $("#results").classList.toggle("student-mode", e.target.checked);
  $$(".reveal-wrap.revealed").forEach((w) => w.classList.remove("revealed"));
  toast(e.target.checked ? "Answers hidden. Try each fix first, then click Show." : "Answers visible");
});

const unverifiedTag = (item) => (item.verified === false ? `<span class="unverified">quote not found in essay</span>` : "");
const speakable = "speechSynthesis" in window;
const speakBtn = (text) => (speakable ? `<button type="button" class="speak-btn" data-speak="${escapeHtml(text)}" title="Read aloud" aria-label="Read aloud">
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/></svg></button>` : "");

function criterionView(c) {
  const max = maxScore();
  const rub = state.rubric?.criteria?.[c.criterion];
  const strengths = c.strengths
    .map((s) => `<div class="item strength">${speakBtn(s.comment)}${s.quote ? `<blockquote>"${escapeHtml(s.quote)}"${unverifiedTag(s)}</blockquote>` : ""}
      ${escapeHtml(s.comment)}</div>`)
    .join("");
  const improvements = c.improvements
    .map((i) => `<div class="item improvement">${speakBtn(`${i.issue} Try this: ${i.suggestion}`)}${i.quote ? `<blockquote>"${escapeHtml(i.quote)}"${unverifiedTag(i)}</blockquote>` : ""}
      <p><b>Issue:</b> ${escapeHtml(i.issue)}</p><p><b>Try:</b> ${escapeHtml(i.suggestion)}</p>
      ${i.example_rewrite ? `<p class="rewrite">${answer(escapeHtml(i.example_rewrite), "Show example rewrite")}</p>` : ""}</div>`)
    .join("");
  return `<div class="crit-head"><h3>${escapeHtml(label(c.criterion))}</h3><span class="crit-score" style="color:${scoreColor(c.score)}">${c.score}/${max}</span></div>
    ${rub ? `<p class="crit-desc">${escapeHtml(rub.question)} ${escapeHtml(c.score)}/5 means: ${escapeHtml(rub.levels?.[c.score] ?? "")}</p>` : ""}
    <p>${escapeHtml(c.summary)}</p>
    ${c.criterion === "grammar" ? errorPatternCard(false) : ""}
    ${c.criterion === "argument" ? argumentChecklist() : ""}
    ${improvements ? `<h4 class="section-title">To improve</h4>${improvements}` : ""}
    ${strengths ? `<h4 class="section-title">Strengths</h4>${strengths}` : ""}`;
}

// Which parts of a strong argument the essay contains (PERSUADE 2.0 element definitions).
function argumentChecklist() {
  const els = state.result.feedback.argument_structure || [];
  if (!els.length || /narrative|descriptive/i.test(state.result.options.essay_type)) return "";
  const defs = state.rubric?.argument_elements || {};
  const have = els.filter((e) => e.present).length;
  const rows = els.map((el) => {
    const def = defs[el.element] || { label: el.element, description: "" };
    return `<li class="${el.present ? "has" : "missing"}">
      <span class="tick" aria-hidden="true">${el.present ? "&#10003;" : "&#10007;"}</span>
      <span><b>${escapeHtml(def.label)}</b> <span class="muted">${el.present ? "" : "missing"}</span>
      ${el.present && el.quote ? `<span class="el-quote">"${escapeHtml(el.quote)}"</span>` : `<span class="el-desc">${escapeHtml(def.description)}</span>`}</span></li>`;
  }).join("");
  return `<h4 class="section-title">Argument structure: ${have} of ${els.length} parts present</h4><ul class="checklist">${rows}</ul>`;
}

// Feature #1: error-pattern summary ("your most common mistake").
function errorPatternCard(withFilters) {
  const errors = state.result.feedback.grammar_errors;
  if (!errors.length) return "";
  const counts = {};
  errors.forEach((e) => (counts[e.error_type] = (counts[e.error_type] || 0) + 1));
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const [topType, topCount] = sorted[0];
  const example = errors.find((e) => e.error_type === topType);
  const chips = withFilters
    ? `<div class="chips">${[["all", errors.length], ...sorted].map(([t, n]) =>
        `<button type="button" class="chip ${state.errorFilter === t ? "active" : ""}" data-filter="${t}">${t === "all" ? "All" : escapeHtml(ERROR_LABELS[t] || t)}<span class="count">${n}</span></button>`).join("")}</div>`
    : `<p><button type="button" class="link-btn small" data-goto="corrections">See all ${errors.length} corrections &rarr;</button></p>`;
  return `<div class="pattern-card">
      <b>Most common mistake: ${escapeHtml(ERROR_LABELS[topType] || topType)} (${topCount} of ${errors.length})</b>
      <p>For example "${escapeHtml(example.quote)}" ${answer(`&rarr; "${escapeHtml(example.correction)}"`)}. ${escapeHtml(example.explanation)}</p>
      ${chips}</div>`;
}

function correctionsView() {
  const all = state.result.feedback.grammar_errors;
  if (!all.length) return `<p class="muted">No grammar or mechanics errors found. Nice work!</p>`;
  const errors = state.errorFilter === "all" ? all : all.filter((e) => e.error_type === state.errorFilter);
  return `${errorPatternCard(true)}
    <table><thead><tr><th>You wrote</th><th>Correction</th><th>Type</th><th>Why</th></tr></thead><tbody>
    ${errors.map((e) => `<tr><td class="orig">${escapeHtml(e.quote)}</td><td class="fix">${answer(escapeHtml(e.correction))}</td>
      <td><span class="type-tag">${escapeHtml(ERROR_LABELS[e.error_type] || e.error_type)}</span></td><td>${escapeHtml(e.explanation)}${unverifiedTag(e)}</td></tr>`).join("")}
    </tbody></table>`;
}

// Feature #2: readability vs. target grade gauge.
const GRADE_TARGETS = {
  "Middle school (Grades 6-8)": [6, 8], "High school (Grades 9-12)": [9, 12],
  "English language learner": [6, 10], "Undergraduate": [12, 16],
};

function statsView() {
  const s = state.result.stats;
  const level = state.result.options.grade_level;
  const [lo, hi] = GRADE_TARGETS[level] || [9, 12];
  const scaleMax = 18;
  const g = Math.max(0, Math.min(scaleMax, s.grade_level));
  const pct = (x) => `${(x / scaleMax) * 100}%`;
  const verdict = s.grade_level < lo
    ? "Reads simpler than expected for this level. Try combining short sentences and using more precise words."
    : s.grade_level > hi
      ? "Harder to read than expected for this level. Try splitting long sentences."
      : "Right on target for this level.";
  const items = [
    [s.words, "words"], [s.paragraphs, "paragraphs"], [s.sentences, "sentences"],
    [s.avg_sentence_length, "words per sentence (avg)"], [s.long_sentences, "very long sentences (35+ words)"],
    [s.lexical_diversity, "vocabulary variety (0-1)"], [s.flesch_reading_ease, "reading ease (higher = easier)"],
  ];
  return `<h4 class="section-title" style="margin-top:0">Reading level
      <span class="info" title="Flesch-Kincaid grade: the US school grade that could comfortably read this text, based on sentence length and word length.">i</span></h4>
    <p>Reads at about <b>grade ${s.grade_level}</b>. Target for ${escapeHtml(level)}: grades ${lo}-${hi}.</p>
    <div class="gauge">
      <div class="gauge-track">
        <div class="gauge-band" style="left:${pct(lo)};width:${pct(hi - lo)}"></div>
        <div class="gauge-marker" style="left:${pct(g)}">Grade ${s.grade_level}</div>
      </div>
      <div class="gauge-scale"><span>0</span><span>6</span><span>12</span><span>18</span></div>
    </div>
    <p class="muted">${verdict}</p>
    <h4 class="section-title">Essay stats</h4>
    <div class="stats-grid">${items.map(([v, l]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`).join("")}</div>`;
}

// ---------- Feature #4: read aloud ----------

function speak(text, btn) {
  if (!speakable) return toast("Read-aloud isn't supported in this browser");
  const synth = window.speechSynthesis;
  const wasSpeaking = synth.speaking && speak.current === btn;
  synth.cancel();
  $$(".speaking").forEach((b) => b.classList.remove("speaking"));
  if (wasSpeaking) { speak.current = null; updateListenLabel(); return; }
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.98;
  u.onend = u.onerror = () => { btn?.classList.remove("speaking"); speak.current = null; updateListenLabel(); };
  speak.current = btn;
  btn?.classList.add("speaking");
  synth.speak(u);
  updateListenLabel();
}
function updateListenLabel() {
  $("#read-aloud span").textContent = speak.current === $("#read-aloud") ? "Stop" : "Listen";
}
if (!speakable) $("#read-aloud").hidden = true;
$("#read-aloud").addEventListener("click", (e) => {
  const fb = state.result?.feedback;
  if (!fb) return;
  const text = `Overall, ${fb.overall_score} out of ${maxScore()}. ${fb.overall_summary} ` +
    `What's working: ${fb.top_strengths.join(". ")}. Fix these first: ${fb.top_priorities.join(". ")}. ` +
    `Practice task: ${fb.next_step_exercise}`;
  speak(text, e.currentTarget);
});

// ---------- Share: copy / download ----------

$("#copy-report").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.result.markdown);
    toast("Report copied. Paste it into an email or doc.");
  } catch {
    toast("Couldn't copy. Use Download instead.");
  }
});
$("#download").addEventListener("click", () => {
  if (!state.result) return;
  const blob = new Blob([state.result.markdown], { type: "text/markdown" });
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(blob), download: `essay-feedback-${new Date().toISOString().slice(0, 10)}.md`,
  });
  a.click();
  URL.revokeObjectURL(a.href);
  toast("Report downloaded");
});
$("#new-essay").addEventListener("click", () => {
  state.result = null;
  $("#essay").value = "";
  $$("#sample-list .chip").forEach((c) => c.classList.remove("active"));
  onEssayChange();
  showError(null);
  setView("empty");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

// ---------- Feature #18: recent reports (this browser only) ----------

function saveHistory(result) {
  const first = result.essay.split("\n").find((l) => l.trim()) || "Untitled essay";
  const entry = { id: Date.now(), title: first.slice(0, 48), overall: result.feedback.overall_score, result };
  let list = [entry, ...store.get("history", []).filter((h) => h.result.essay !== result.essay)].slice(0, 6);
  while (list.length && !store.set("history", list)) list = list.slice(0, -1); // shrink if storage is full
  renderRecent();
}

function renderRecent() {
  const list = store.get("history", []);
  $("#recent-wrap").hidden = !list.length;
  $("#recent").innerHTML = `<option value="">Recent reports (${list.length})</option>` +
    list.map((h) => `<option value="${h.id}">${escapeHtml(h.title)} · ${h.overall}/5</option>`).join("");
}

$("#recent").addEventListener("change", (e) => {
  const h = store.get("history", []).find((x) => String(x.id) === e.target.value);
  e.target.value = "";
  if (!h) return;
  $("#essay").value = h.result.essay;
  $("#grade-level").value = h.result.options.grade_level;
  $("#essay-type").value = h.result.options.essay_type;
  onEssayChange();
  showResult(h.result);
  toast("Opened a saved report");
});

$("#open-how").addEventListener("click", () => document.body.classList.add("show-hero"));

// ---------- Rubric dialog ----------

$("#open-rubric").addEventListener("click", (e) => {
  e.preventDefault();
  const r = state.rubric;
  if (!r) return;
  const crit = Object.values(r.criteria).map((c) => `<div class="rubric-crit">
      <h3>${escapeHtml(c.label)}</h3><p>${escapeHtml(c.question)} Looks for: ${escapeHtml(c.look_for.join("; "))}.</p>
      <div class="levels">${Object.entries(c.levels).sort((a, b) => b[0] - a[0]).map(([s, d]) => `<div><b>${s}</b><span>${escapeHtml(d)}</span></div>`).join("")}</div>
    </div>`).join("");
  const args = Object.values(r.argument_elements || {}).map((a) => `<div><b>&middot;</b><span><b>${escapeHtml(a.label)}:</b> ${escapeHtml(a.description)}</span></div>`).join("");
  $("#rubric-body").innerHTML = crit +
    `<div class="rubric-crit"><h3>Argument structure checklist</h3><p>For argumentative essays we also check for these parts of a strong argument:</p><div class="levels">${args}</div></div>`;
  $("#rubric-dialog").showModal();
});
$("#rubric-dialog").addEventListener("click", (e) => {
  if (e.target.matches("[data-close]") || e.target === e.currentTarget) e.currentTarget.close();
});

// ---------- Onboarding: guided tour ----------

const TOURS = {
  input: [
    { target: "#tour-samples", title: "Start with a sample", text: "New here? Pick a sample essay to see a full report. Each one shows a different kind of feedback (hover a sample for a hint)." },
    { target: "#tour-essay", title: "Or paste your own essay", text: "Paste text or upload a .txt file. The bar turns green at 50 words. Your draft is saved in this browser automatically." },
    { target: "#tour-options", title: "Match the student", text: "Choose the student's level and essay type. The feedback adjusts its expectations and language to fit." },
    { target: "#submit", title: "Get feedback", text: "Press here or use Ctrl+Enter. The free AI takes about 15-40 seconds." },
  ],
  results: [
    { target: "#tour-overview", title: "Scores at a glance", text: "An overall score plus four criteria, each out of 5. Hover an (i) icon to see what that score means." },
    { target: "#tabs", title: "Dig into the details", text: "Highlights puts comments right on the essay: click any colored phrase. The other tabs explain each criterion, list corrections and show the reading level." },
    { target: ".results-toolbar", title: "Make it a learning moment", text: "\"Try it yourself\" hides corrections until the student has a go. Listen reads the feedback aloud. Copy and Download share the report." },
  ],
};
const tour = { steps: [], i: 0, name: "", then: null };

function startTour(name, then = null) {
  const steps = TOURS[name].filter((s) => $(s.target) && $(s.target).offsetParent !== null);
  if (!steps.length) return;
  Object.assign(tour, { steps, i: 0, name, then });
  $("#tour-spot").hidden = false;
  $("#tour-card").hidden = false;
  showTourStep();
}

function showTourStep() {
  const step = tour.steps[tour.i];
  const el = $(step.target);
  $("#tour-count").textContent = `Step ${tour.i + 1} of ${tour.steps.length}`;
  $("#tour-title").textContent = step.title;
  $("#tour-text").textContent = step.text;
  $("#tour-back").hidden = tour.i === 0;
  $("#tour-next").textContent = tour.i === tour.steps.length - 1 ? (tour.then ? "Next" : "Got it") : "Next";
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  setTimeout(positionTour, 350);
  $("#tour-next").focus({ preventScroll: true });
}

function positionTour() {
  if ($("#tour-card").hidden) return;
  const el = $(tour.steps[tour.i].target);
  const r = el.getBoundingClientRect();
  const pad = 6;
  Object.assign($("#tour-spot").style, {
    top: `${r.top - pad}px`, left: `${r.left - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`,
  });
  const card = $("#tour-card");
  const cw = card.offsetWidth;
  const ch = card.offsetHeight;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let top, left;
  if (vw < 640) {
    left = (vw - cw) / 2;
    top = r.bottom + ch + 24 < vh ? r.bottom + 14 : Math.max(12, r.top - ch - 14);
  } else if (r.right + cw + 24 < vw) {
    left = r.right + 16; top = Math.min(Math.max(12, r.top), vh - ch - 12);
  } else if (r.bottom + ch + 24 < vh) {
    left = Math.min(Math.max(12, r.left), vw - cw - 12); top = r.bottom + 14;
  } else {
    left = Math.min(Math.max(12, r.left), vw - cw - 12); top = Math.max(12, r.top - ch - 14);
  }
  Object.assign(card.style, { top: `${top}px`, left: `${left}px` });
}

function endTour(completed = true) {
  $("#tour-spot").hidden = true;
  $("#tour-card").hidden = true;
  store.set(`tour.${tour.name}`, true);
  const next = tour.then;
  tour.then = null;
  if (completed && next) startTour(next);
}

$("#tour-next").addEventListener("click", () => (tour.i < tour.steps.length - 1 ? (tour.i++, showTourStep()) : endTour(true)));
$("#tour-back").addEventListener("click", () => { if (tour.i > 0) { tour.i--; showTourStep(); } });
$("#tour-skip").addEventListener("click", () => { store.set("tour.results", true); endTour(false); });
$("#start-tour").addEventListener("click", () => {
  window.scrollTo({ top: 0 });
  startTour("input", state.result ? "results" : null);
});
window.addEventListener("resize", positionTour);
window.addEventListener("scroll", positionTour, { passive: true });
document.addEventListener("keydown", (e) => {
  if ($("#tour-card").hidden) return;
  if (e.key === "Escape") endTour(false);
  if (e.key === "ArrowRight") $("#tour-next").click();
  if (e.key === "ArrowLeft") $("#tour-back").click();
});

init();
