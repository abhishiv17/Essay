// Essay Feedback Generator frontend (no build step). Talks to the FastAPI routes in app.py.
// Flow: landing -> submission (essay + optional context) -> analysis pipeline -> feedback report.
// The report is one document: overall score, the four required criteria (expandable), strengths,
// prioritized improvements (evidence -> why -> next step), practice, and measured evaluation,
// with the annotated essay beside it. Every quoted comment links to the exact sentence.

"use strict";

/* ============================== utils ============================== */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const MIN_WORDS = 50;
const MAX_WORDS = 3000;

const escapeHtml = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// Browser storage: per-viewer conveniences only (draft, preferences, recent reports). Never required.
const store = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(`efg.${key}`); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`efg.${key}`, JSON.stringify(value)); return true; } catch { return false; }
  },
};

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.hidden = true), 2800);
}

function relTime(ts) {
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  const d = Math.round(s / 86400);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

/* ============================== motion ============================== */
// Fast 0.2s, standard 0.4s, reveal 0.7s; power easing, no bounce. Instant without GSAP or with reduced motion.

const DUR = { fast: 0.2, std: 0.4, reveal: 0.7 };
const EASE = "power3.out";
const reducedMQ = window.matchMedia("(prefers-reduced-motion: reduce)");
const motionOK = () => typeof window.gsap !== "undefined" && !reducedMQ.matches;

/* ============================== API ============================== */

class ApiError extends Error {
  constructor(status, detail) { super(detail); this.status = status; this.detail = detail; }
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const code = $("#access-code").value.trim();
  if (code) headers["X-Access-Code"] = code;
  let res;
  try { res = await fetch(path, { ...options, headers }); } catch { throw new ApiError(0, "network"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return body;
}

function friendlyError(err) {
  const d = String(err.detail || "").toLowerCase();
  if (err.status === 0) return { title: "The feedback service can't be reached.", text: "Check your connection, or that the server is running." };
  if (d.includes("limit reached") || d.includes("rate-limited") || d.includes("rate limit") || d.includes("429")) {
    const resets = [...d.matchAll(/resets in about ([^)|]+)/g)].map((m) => m[1].trim());
    const when = resets.length ? ` The free quota resets in about ${resets.sort((a, b) => a.length - b.length)[0]}.` : " Wait about a minute, then try again.";
    return { title: "The free AI models are busy right now.", text: `They have reached their free usage limit.${when} Sample essays still open instantly.`, raw: err.detail };
  }
  if (d.includes("api key")) return { title: "The AI service isn't set up yet.", text: "The server is missing GROQ_API_KEY / GEMINI_API_KEY (see the README).", raw: err.detail };
  if (d.includes("invalid json") || d.includes("incomplete") || d.includes("cut off")) return { title: "The report came back incomplete.", text: "This happens occasionally with free AI models. Trying again usually works.", raw: err.detail };
  return { title: "The feedback service is temporarily unavailable.", text: "Something went wrong while analyzing the essay. Please try again in a moment.", raw: err.detail };
}

/* ============================== data helpers ============================== */

const CRITERIA = ["grammar", "coherence", "argument", "originality"];
const CRIT_NAME = { grammar: "Grammar & Mechanics", coherence: "Coherence & Organization", argument: "Argument Strength", originality: "Originality & Voice" };
const CAT_OF = { grammar: "grammar", coherence: "structure", argument: "argument", originality: "voice" };
const ERROR_LABELS = {
  grammar: "Grammar", spelling: "Spelling", punctuation: "Punctuation",
  capitalization: "Capitalization", word_choice: "Word choice", sentence_structure: "Sentence structure",
};
const isArgumentative = (type) => !/narrative|descriptive/i.test(type || "");
const levelWord = (s) => (s <= 2 ? "Needs work" : s === 3 ? "Developing" : "Strong");
function critQuestion(crit, type) {
  if (crit === "argument" && !isArgumentative(type)) return "For narrative writing: how clearly does it make its point?";
  return {
    grammar: "How correct and readable are the sentences?",
    coherence: "How logically does the essay flow?",
    argument: "How convincingly are claims supported?",
    originality: "How specific and distinctive is the writing?",
  }[crit];
}

const SAMPLE_META = {
  "1_strong_argumentative": { title: "Strong argument", type: "Argumentative", level: "High school (Grades 9-12)", tag: "Argumentative · strong", desc: "A well-argued essay on school start times, with evidence and a rebuttal.", expect: "Expect high scores and specific praise, plus a few precise refinements." },
  "2_esl_grammar_errors": { title: "English learner, many errors", type: "Argumentative", level: "English language learner", tag: "Argumentative · ESL", desc: "Clear ideas with frequent grammar and mechanics errors.", expect: "Expect a low grammar score, recurring error patterns, and each rule explained." },
  "3_generic_cliche": { title: "Clean but generic", type: "Argumentative", level: "High school (Grades 9-12)", tag: "Argumentative · cliched", desc: "Correct grammar, but vague claims and stock phrases.", expect: "Expect weaker argument and originality scores despite clean grammar." },
  "4_narrative": { title: "Personal narrative", type: "Narrative", level: "High school (Grades 9-12)", tag: "Narrative", desc: "A short story about a power cut, with no thesis or counterargument.", expect: "Expect narrative-appropriate feedback, with no penalty for missing a thesis." },
};

// Find a quote in the essay: case-insensitive, whitespace-tolerant, supports "..." elisions (mirrors core/verify.py).
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

// Every quoted comment becomes an "item" that can be linked between the report and the essay.
function buildItems(r) {
  const fb = r.feedback;
  const items = [];
  let n = 0;
  for (const e of fb.grammar_errors)
    items.push({ id: `i${n++}`, kind: "error", cat: "grammar", crit: "grammar", quote: e.quote, type: e.error_type, title: ERROR_LABELS[e.error_type] || "Correction", why: e.explanation, fix: e.correction, verified: e.verified !== false });
  for (const c of fb.criteria)
    for (const i of c.improvements)
      items.push({ id: `i${n++}`, kind: "issue", cat: CAT_OF[c.criterion], crit: c.criterion, quote: i.quote, why: i.issue, tip: i.suggestion, rewrite: i.example_rewrite, verified: i.verified !== false });
  for (const c of fb.criteria)
    for (const s of c.strengths)
      items.push({ id: `i${n++}`, kind: "strength", cat: "strength", crit: c.criterion, quote: s.quote, why: s.comment, verified: s.verified !== false });

  // Highlight spans: errors win over issues, issues over strengths, when they overlap. Only verified quotes.
  const owners = [];
  for (const it of items) {
    const sp = it.quote && it.verified ? findSpan(it.quote, r.essay) : null;
    if (!sp) continue;
    const clash = owners.find((o) => sp[0] < o.span[1] && o.span[0] < sp[1]);
    if (clash) it.markOf = clash.id;
    else { it.span = sp; it.markOf = it.id; owners.push(it); }
  }
  return items;
}

const STOP = new Set("the a an and or but of to in on for with your you is are was be this that it its as at by from more most very their they them our we us has have had can will would should could not no into about than then so such also just each one".split(" "));
const words = (s) => ((s || "").toLowerCase().match(/[a-z']{3,}/g) || []).filter((w) => !STOP.has(w));
function bestMatch(text, candidates, getText) {
  const target = new Set(words(text));
  let best = null;
  let bestScore = 0;
  for (const c of candidates) {
    const score = new Set(words(getText(c)).filter((w) => target.has(w))).size;
    if (score > bestScore) { best = c; bestScore = score; }
  }
  return bestScore >= 2 ? best : null;
}
const scoresOf = (r) => Object.fromEntries([["overall", r.feedback.overall_score], ...r.feedback.criteria.map((c) => [c.criterion, c.score])]);

/* ============================== Nib, the guide ============================== */
// Nib (frontend/mascot.js) walks first-time users through the steps. Tips appear once per browser;
// the header "Guide" button replays the tip for the current screen at any time.

const hasNib = () => typeof window.Nib !== "undefined";

function nibTip(step) {
  const scrollTo = (sel) => $(sel)?.scrollIntoView({ behavior: motionOK() ? "smooth" : "auto", block: "start" });
  const tips = {
    landing: { mood: "hello", text: "Hi, I'm Nib! New here? Start with a sample essay to see a full report in seconds, or paste your own essay.",
      actions: [{ label: "Show me the samples", onClick: () => scrollTo("#home-samples") }, { label: "Paste my own", onClick: () => openSubmit() }] },
    "submit-empty": { mood: "point", text: "Step 1: paste the essay into the big box (at least 50 words), or use Upload .txt. Not sure? Use a sample." },
    "submit-ready": { mood: "point", text: "Step 2 (optional): set the essay type, academic level and assignment prompt below for more specific feedback. Then press Generate Feedback.",
      actions: [{ label: "Generate Feedback", onClick: () => generate() }] },
    analysis: { mood: "writing", text: "I'm reading the essay against the rubric and checking every quote. This usually takes 10 to 40 seconds." },
    report: { mood: "cheer", text: "Step 3: here's the report! Start with the four criteria, then Areas for improvement. Click any underlined sentence to see it in the essay.",
      actions: [{ label: "Show the four criteria", onClick: () => scrollTo("#crit-title") }, { label: "Got it" }] },
    error: { mood: "oops", text: "Something went wrong, but the essay is saved. Try again in a moment, or open a sample: those load instantly.",
      actions: [{ label: "Open samples", onClick: () => $("#dlg-samples").showModal() }] },
  };
  return tips[step];
}

// Show a step's tip the first time only (unless forced by the Guide button).
function guide(step, { force = false } = {}) {
  if (!hasNib()) return;
  const tip = nibTip(step);
  if (!tip) return;
  if (force) Nib.mute(false);
  Nib.say(tip.text, { mood: tip.mood, actions: tip.actions || [], duration: 11000, once: force ? "" : `tip-${step}` });
}

function currentStep() {
  if (currentView === "submit") return wordCount() >= MIN_WORDS ? "submit-ready" : "submit-empty";
  return currentView;
}

function onViewChange(view) {
  if (!hasNib()) return;
  Nib.hide();
  if (view === "analysis") Nib.mount("#nib-analysis", "writing");
  if (view === "error") Nib.mount("#nib-error", "oops");
  const step = view === "submit" ? currentStep() : view;
  if (view !== "analysis") setTimeout(() => currentView === view && guide(step), view === "report" ? 1600 : 600);
}

/* ============================== views ============================== */

const state = { rubric: null, samples: [], evaluation: null, result: null, items: [], previous: null, loading: false, health: null };
let currentView = "landing";

function settleViews() { $$(".view").forEach((v) => (v.hidden = v.id !== `view-${currentView}`)); }

function show(view, { flipFrom = null } = {}) {
  const next = $(`#view-${view}`);
  const prev = $$(".view").find((v) => !v.hidden && v !== next);
  currentView = view;
  document.body.dataset.view = view;
  $("#back-chip").hidden = true;
  onViewChange(view);
  if (!motionOK()) { settleViews(); window.scrollTo(0, 0); return; }
  gsap.killTweensOf(".view");
  gsap.set(".view", { clearProps: "opacity,transform" });
  if (!prev) { settleViews(); return; }

  const target = flipFrom && window.Flip ? next.querySelector("[data-flip-id]") : null;
  if (target) {
    // The "Analyze an Essay" button grows into the essay editor.
    const flipState = Flip.getState(flipFrom);
    settleViews();
    window.scrollTo(0, 0);
    Flip.from(flipState, { targets: target, duration: 0.55, ease: "power3.inOut", absolute: true, scale: true, fade: true });
    gsap.from($$(":scope > * > *:not(.editor)", next), { opacity: 0, y: 10, duration: DUR.std, delay: 0.25, stagger: 0.04, ease: EASE, clearProps: "all" });
    return;
  }
  gsap.to(prev, {
    opacity: 0, y: -6, duration: DUR.fast, ease: "power2.in",
    onComplete() {
      gsap.set(prev, { clearProps: "opacity,transform" });
      settleViews();
      window.scrollTo(0, 0);
      gsap.fromTo(`#view-${currentView}`, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: DUR.std, ease: EASE, clearProps: "opacity,transform" });
    },
  });
}

function introLanding() {
  if (!motionOK()) return;
  const tl = gsap.timeline({ defaults: { ease: EASE } });
  setTimeout(() => tl.progress(1), 2500); // safety net: never leave the hero half-faded
  tl.from(".nib-intro", { opacity: 0, y: 10, duration: 0.4 })
    .from(".kicker, #landing-title", { opacity: 0, y: 14, duration: 0.5, stagger: 0.08 })
    .from(".lede", { opacity: 0, y: 8, duration: 0.35 }, "-=0.3")
    .from(".criteria-strip li", { opacity: 0, y: 8, duration: 0.35, stagger: 0.05 }, "-=0.2")
    .from(".cta-row, .meta-line", { opacity: 0, y: 8, duration: 0.35 }, "-=0.2")
    .from(".preview-sheet", { opacity: 0, y: 20, duration: 0.6 }, "-=0.4")
    .from(".pipeline-strip li", { opacity: 0, y: 8, duration: 0.35, stagger: 0.05 }, "-=0.3");
}

/* ============================== samples + recent ============================== */

function renderSamples() {
  $("#sample-list").innerHTML = state.samples.map((s) => {
    const m = SAMPLE_META[s.id] || { title: s.title, tag: "", desc: "", expect: "" };
    return `<button class="sample-card" type="button" data-sample="${escapeHtml(s.id)}">
      <span class="top"><b>${escapeHtml(m.title)}</b><span class="tags">${escapeHtml(m.tag)}</span></span>
      <span class="desc">${escapeHtml(m.desc)}</span><span class="expect">${escapeHtml(m.expect)}</span></button>`;
  }).join("");
  $("#home-samples").innerHTML = state.samples.map((s) => {
    const m = SAMPLE_META[s.id] || { title: s.title, tag: "", desc: "", expect: "" };
    return `<button class="sample-card" type="button" data-sample="${escapeHtml(s.id)}">
      <span class="top"><span class="tags">${escapeHtml(m.tag)}</span><b>${escapeHtml(m.title)}</b></span>
      <span class="desc">${escapeHtml(m.desc)}</span><span class="expect">${escapeHtml(m.expect)}</span>
      <span class="go">Use this essay &rarr;</span></button>`;
  }).join("");
  const list = store.get("history", []);
  $("#recent-section").innerHTML = list.length
    ? `<p class="eyebrow" style="margin-top:12px">Recent reports in this browser</p><div class="sample-list">${list.map((h) =>
        `<button class="sample-card" type="button" data-history="${h.id}"><span class="top"><b>${escapeHtml(h.title)}</b>
         <span class="tags">${h.overall} / 5</span></span><span class="expect">${escapeHtml(h.type || "")} &middot; ${relTime(h.when)}</span></button>`).join("")}</div>`
    : "";
}

function loadSample(s) {
  const m = SAMPLE_META[s.id] || {};
  $("#essay").value = s.text;
  $("#essay-type").value = m.type || "Argumentative";
  $("#grade-level").value = m.level || "High school (Grades 9-12)";
  $("#assignment").value = "";
  state.previous = null;
  onEssayInput();
}

function saveHistory(result) {
  const first = result.essay.split("\n").find((l) => l.trim()) || "Untitled essay";
  const entry = { id: Date.now(), title: first.slice(0, 60), type: result.options.essay_type, overall: result.feedback.overall_score, when: Date.now(), result };
  let list = [entry, ...store.get("history", []).filter((h) => h.result.essay !== result.essay)].slice(0, 6);
  while (list.length && !store.set("history", list)) list = list.slice(0, -1);
}

document.addEventListener("click", (e) => {
  const sampleBtn = e.target.closest("[data-sample]");
  if (sampleBtn) {
    const s = state.samples.find((x) => x.id === sampleBtn.dataset.sample);
    if (!s) return;
    if ($("#dlg-samples").open) $("#dlg-samples").close();
    loadSample(s);
    openSubmit();
    toast(`Sample loaded: "${(SAMPLE_META[s.id] || s).title}". Press Generate Feedback.`);
    return;
  }
  const hist = e.target.closest("[data-history]");
  if (hist) {
    const h = store.get("history", []).find((x) => String(x.id) === hist.dataset.history);
    if (!h) return;
    $("#dlg-samples").close();
    $("#essay").value = h.result.essay;
    $("#essay-type").value = h.result.options.essay_type;
    $("#grade-level").value = h.result.options.grade_level;
    $("#assignment").value = h.result.options.assignment_prompt || "";
    saveDraft();
    openReport(h.result);
  }
});

/* ============================== submission ============================== */

function openSubmit(opts = {}) {
  $("#revision-banner").hidden = !state.previous;
  if (state.previous) $("#revision-text").textContent = `The previous version scored ${state.previous.feedback.overall_score}/5. Edit the essay, then generate feedback again to compare on the same rubric.`;
  updateWordCount(false);
  show("submit", opts);
  setTimeout(() => { if (!$("#essay").value.trim()) $("#essay").focus({ preventScroll: true }); }, opts.flipFrom ? 600 : 250);
}

const wordCount = () => ($("#essay").value.match(/\S+/g) || []).length;
let shownCount = 0;
let wasValid = false;

function updateWordCount(animate = true) {
  const n = wordCount();
  const label = $("#word-count");
  const render = (v) => (label.textContent = `${Math.round(v).toLocaleString()} word${Math.round(v) === 1 ? "" : "s"}`);
  if (animate && motionOK() && Math.abs(n - shownCount) > 3) {
    const o = { v: shownCount };
    gsap.to(o, { v: n, duration: DUR.fast, ease: "power1.out", onUpdate: () => render(o.v) });
  } else render(n);
  shownCount = n;
  const valid = n >= MIN_WORDS && n <= MAX_WORDS;
  const unlock = $("#unlock");
  unlock.classList.toggle("ready", valid);
  if (n === 0) unlock.textContent = `Add at least ${MIN_WORDS} words to generate feedback.`;
  else if (n < MIN_WORDS) unlock.textContent = `${MIN_WORDS - n} more word${MIN_WORDS - n === 1 ? "" : "s"} needed to generate feedback.`;
  else if (n > MAX_WORDS) unlock.textContent = `Over ${MAX_WORDS.toLocaleString()} words. Shorten the essay to continue.`;
  else unlock.textContent = "Ready to analyze.";
  $("#generate").disabled = !valid || state.loading;
  if (valid && !wasValid && currentView === "submit") guide("submit-ready");
  if (valid && !wasValid && animate && motionOK()) gsap.fromTo("#generate", { scale: 0.96 }, { scale: 1, duration: 0.35, ease: "power2.out", clearProps: "transform" });
  wasValid = valid;
}

let saveTimer;
function onEssayInput() {
  updateWordCount();
  $("#save-state").textContent = "Saving…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraft, 500);
}
function saveDraft() {
  const ok = store.set("draft", { essay: $("#essay").value, grade: $("#grade-level").value, type: $("#essay-type").value, assignment: $("#assignment").value });
  $("#save-state").textContent = ok ? "Saved in this browser" : "Couldn't save in this browser";
}
function restoreDraft() {
  const d = store.get("draft");
  if (!d) return;
  $("#essay").value = d.essay || "";
  if (d.grade) $("#grade-level").value = d.grade;
  if (d.type) $("#essay-type").value = d.type;
  if (d.assignment) $("#assignment").value = d.assignment;
  if (d.essay) $("#save-state").textContent = "Saved in this browser";
  updateWordCount(false);
}

$("#essay").addEventListener("input", onEssayInput);
["#grade-level", "#essay-type", "#assignment"].forEach((s) => $(s).addEventListener("change", saveDraft));
$("#file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $("#essay").value = await file.text();
  onEssayInput();
  toast(`Loaded ${file.name}`);
  e.target.value = "";
});
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && currentView === "submit" && !$("#generate").disabled) generate();
});

/* ============================== analysis ============================== */

const STAGES = [
  "Reading the essay",
  "Analyzing grammar & mechanics",
  "Evaluating coherence & organization",
  "Assessing argument strength",
  "Examining originality & voice",
  "Generating constructive feedback",
  "Verifying feedback against the essay",
];

function startStages() {
  const ol = $("#stages");
  ol.innerHTML = STAGES.map((s) => `<li><span class="tick" aria-hidden="true">&#10003;</span>${s}</li>`).join("");
  const lis = $$("li", ol);
  let i = 0;
  lis[0].classList.add("active");
  if (motionOK()) gsap.from(lis, { opacity: 0, y: 6, duration: DUR.std, stagger: 0.04, ease: EASE });
  // Paced through the analysis stages; "Generating" stays active until the response arrives.
  const timer = setInterval(() => {
    if (i >= STAGES.length - 2) return;
    lis[i].classList.replace("active", "done");
    lis[++i].classList.add("active");
  }, 1600);
  return async () => {
    clearInterval(timer);
    for (let k = 0; k < lis.length; k++) { lis[k].classList.remove("active"); lis[k].classList.add("done"); }
    await new Promise((r) => setTimeout(r, motionOK() ? 350 : 0));
  };
}

async function generate() {
  if (state.loading) return;
  $("#inline-error").hidden = true;
  saveDraft();
  state.loading = true;
  show("analysis");
  const finish = startStages();
  const shownAt = Date.now();
  try {
    const result = await api("/api/feedback", {
      method: "POST",
      body: JSON.stringify({ essay: $("#essay").value.trim(), grade_level: $("#grade-level").value, essay_type: $("#essay-type").value, assignment_prompt: $("#assignment").value }),
    });
    // Saved results return instantly; keep the pipeline readable instead of flashing it.
    await new Promise((r) => setTimeout(r, Math.max(0, 1500 - (Date.now() - shownAt))));
    await finish();
    if (state.previous && state.previous.essay !== result.essay) result.compare = { before: scoresOf(state.previous), after: scoresOf(result) };
    state.previous = null;
    saveHistory(result);
    openReport(result);
  } catch (err) {
    await finish();
    handleError(err);
  } finally {
    state.loading = false;
    updateWordCount(false);
  }
}

function handleError(err) {
  if (err.status === 422 || err.status === 401) {
    openSubmit();
    const box = $("#inline-error");
    if (err.status === 401) {
      $("#access-wrap").hidden = false;
      box.textContent = "This deployment needs an access code. Enter the code your team shared, then generate again.";
      setTimeout(() => $("#access-code").focus(), 300);
    } else box.textContent = err.detail;
    box.hidden = false;
    return;
  }
  const f = friendlyError(err);
  $("#error-title").textContent = f.title;
  $("#error-text").textContent = f.text;
  $("#error-tech").hidden = !f.raw;
  $("#error-raw").textContent = f.raw || "";
  show("error");
}

$("#generate").addEventListener("click", generate);
$("#error-retry").addEventListener("click", generate);
$("#error-edit").addEventListener("click", () => openSubmit());

/* ============================== report ============================== */

function modelLine(r) {
  if (!r.model || r.model === "mock") return { cls: "demo", text: "Demo data: example feedback (MOCK_LLM), not a live analysis of this essay." };
  const [provider, model] = r.model.split(":");
  const nice = { groq: "Groq", gemini: "Google Gemini", ollama: "Ollama", anthropic: "Claude" }[provider] || provider;
  return { cls: "", text: `${r.from_cache ? "Saved analysis" : "Live analysis"} by ${nice} (${(model || "").split(" ")[0]}) · generated ${new Date(r.generated_at).toLocaleString()}` };
}

const quoteBtn = (it) => `<button type="button" class="quote-btn" data-item="${it.id}" title="Show this sentence in the essay">&ldquo;${escapeHtml(it.quote)}&rdquo;</button>`;
const verifiedTag = (it) => (it.markOf ? `<span class="verified">&#10003; quote found in essay</span>` : `<span class="whole">applies to the whole essay</span>`);

function improvementCard(it, type, priority = 0) {
  return `<div class="fb cat-${it.cat}" data-item="${it.id}">
    <div class="fb-head"><span class="cat-label">${CRIT_NAME[it.crit]}${priority ? `<span class="priority-tag">Priority ${priority}</span>` : ""}</span>${verifiedTag(it)}</div>
    <dl>
      ${it.quote && it.markOf ? `<div><dt class="lbl">Evidence: your sentence</dt><dd>${quoteBtn(it)}</dd></div>` : ""}
      <div><dt class="lbl">Why this matters</dt><dd>${escapeHtml(it.why)}</dd></div>
      <div><dt class="lbl">What to do next</dt><dd>${escapeHtml(it.tip)}</dd></div>
      ${it.rewrite ? `<div><dt class="lbl">Suggested revision</dt><dd><span class="rewrite">${escapeHtml(it.rewrite)}</span></dd></div>` : ""}
    </dl></div>`;
}

function renderReport(r) {
  const fb = r.feedback;
  const type = r.options.essay_type;
  const first = r.essay.split("\n").find((l) => l.trim()) || "Untitled essay";
  const src = modelLine(r);
  const v = r.verification;
  const issues = state.items.filter((i) => i.kind === "issue");

  // Areas for improvement: the model's top priorities first, each matched to its grounded comment.
  const used = new Set();
  const prioritized = fb.top_priorities.map((p, i) => {
    const m = bestMatch(p, issues.filter((x) => !used.has(x.id)), (x) => `${x.why} ${x.tip}`);
    if (m) used.add(m.id);
    return { text: p, item: m, n: i + 1 };
  });
  const scoreOf = Object.fromEntries(fb.criteria.map((c) => [c.criterion, c.score]));
  const rest = issues.filter((x) => !used.has(x.id)).sort((a, b) => scoreOf[a.crit] - scoreOf[b.crit]);
  const improvementHtml = [
    ...prioritized.map((p) => p.item ? improvementCard(p.item, type, p.n)
      : `<div class="fb" data-priority="${p.n}"><div class="fb-head"><span class="cat-label">Overall<span class="priority-tag">Priority ${p.n}</span></span></div><p>${escapeHtml(p.text)}</p></div>`),
    ...rest.map((it) => improvementCard(it, type)),
  ];
  const VISIBLE = 4;

  // Strengths: top 3, each with the grounded quote that best supports it.
  const strengthPool = state.items.filter((i) => i.kind === "strength" && i.markOf);
  const strengths = fb.top_strengths.map((t, i) => {
    const m = bestMatch(t, strengthPool, (x) => `${x.why} ${x.quote}`);
    if (m) strengthPool.splice(strengthPool.indexOf(m), 1);
    return `<li><span class="num">0${i + 1}</span><div><h3>${escapeHtml(t)}</h3>
      ${m ? `<div class="evidence-line"><span class="lbl">Evidence</span>${quoteBtn(m)}<span class="lbl">Why it works</span><span>${escapeHtml(m.why)}</span></div>` : ""}</div></li>`;
  }).join("");

  return `
    <header class="report-head">
      <p class="eyebrow">Feedback report</p>
      <h1 class="report-title" id="report-title">${escapeHtml(first.slice(0, 90))}</h1>
      <div class="calibration" aria-label="Personalization">
        <span>Calibrated for</span>
        <span class="chip">${escapeHtml(type)}</span>
        <span class="chip">${escapeHtml(r.options.grade_level.replace(/\s*\(.*\)/, ""))}</span>
        <span class="chip">${r.options.assignment_prompt ? "Assignment prompt considered" : "No assignment prompt"}</span>
        <span class="chip">${r.stats.words} words</span>
      </div>
      <p class="source ${src.cls}">${escapeHtml(src.text)}</p>
      <div class="report-actions">
        <button class="btn btn-quiet btn-sm" type="button" id="print-report">Print report</button>
        <button class="btn btn-quiet btn-sm" type="button" id="copy-report">Copy feedback</button>
        <button class="btn btn-quiet btn-sm" type="button" id="download-report">Download (.md)</button>
      </div>
    </header>

    <section class="overall" aria-label="Overall score">
      <div><div class="overall-score"><span id="overall-num">${fb.overall_score}</span><small> / 5</small></div><span class="overall-word">${levelWord(fb.overall_score)}</span></div>
      <p class="overall-summary">${escapeHtml(fb.overall_summary)}</p>
    </section>
    ${r.compare ? compareBox(r) : ""}

    <section class="r-section" aria-labelledby="crit-title">
      <header><h2 class="h-section" id="crit-title">The four criteria</h2><span class="meta">Each scored 1&ndash;5. Open one for evidence and recommendations.</span></header>
      <div class="criteria">${fb.criteria.map((c) => criterionBlock(c, r)).join("")}</div>
    </section>

    <section class="r-section" data-reveal="late" aria-labelledby="str-title">
      <header><h2 class="h-section" id="str-title">What you're doing well</h2></header>
      <ol class="numbered">${strengths}</ol>
    </section>

    <section class="r-section" data-reveal="late" aria-labelledby="imp-title">
      <header><h2 class="h-section" id="imp-title">Areas for improvement</h2><span class="meta">Evidence &rarr; why it matters &rarr; what to do next, most important first</span></header>
      <div id="improvements">${improvementHtml.slice(0, VISIBLE).join("")}
        <div id="more-improvements" hidden>${improvementHtml.slice(VISIBLE).join("")}</div></div>
      ${improvementHtml.length > VISIBLE ? `<button class="btn btn-quiet btn-sm more-btn" type="button" id="show-more" aria-expanded="false">Show all ${improvementHtml.length} improvements</button>` : ""}
    </section>

    ${practiceSection(r, prioritized)}

    <section class="r-section" data-reveal="late" aria-labelledby="eval-title">
      <header><h2 class="h-section" id="eval-title">How accurate is this feedback?</h2><span class="meta">Measured results only</span></header>
      ${metricsHtml(true)}
    </section>

    <footer class="report-foot">
      <span>&#10003; ${v.items_checked - v.items_unverified} of ${v.items_checked} quoted comments were matched to the essay's exact words${v.dropped && v.items_unverified ? `; ${v.items_unverified} that couldn't be matched were removed` : ""}.</span>
      <span>Structured first-pass feedback generated in seconds, ready for an educator to review, adjust and share.</span>
      <span>Scores are guidance on the published rubric, not an official grade. Originality is not plagiarism or AI detection.</span>
    </footer>`;
}

function criterionBlock(c, r) {
  const type = r.options.essay_type;
  const its = state.items.filter((i) => i.crit === c.criterion && i.kind !== "error");
  const issues = its.filter((i) => i.kind === "issue");
  const strengths = its.filter((i) => i.kind === "strength");
  const extra = { grammar: grammarExtra, coherence: coherenceExtra, argument: argumentExtra, originality: originalityExtra }[c.criterion](r);
  return `<div class="crit" data-crit="${c.criterion}">
    <button class="crit-row" type="button" aria-expanded="false" aria-controls="crit-${c.criterion}">
      <span class="crit-name">${CRIT_NAME[c.criterion]}<small>${critQuestion(c.criterion, type)}</small></span>
      <span class="crit-track" aria-hidden="true"><span class="crit-fill" style="width:${(c.score / 5) * 100}%"></span></span>
      <span class="crit-score"><b>${c.score}</b> / 5 &middot; ${levelWord(c.score)}</span>
      <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
    </button>
    <div class="crit-body" id="crit-${c.criterion}" hidden><div class="crit-inner">
      <p class="crit-summary">${escapeHtml(c.summary)}</p>
      ${extra}
      ${issues.length ? `<p class="sub-title">Weaknesses &amp; recommendations</p>${issues.map((i) => improvementCard(i, type)).join("")}` : ""}
      ${strengths.length ? `<p class="sub-title">Strengths</p>${strengths.map((s) => `<div class="fb cat-strength" data-item="${s.id}"><div class="fb-head"><span class="cat-label">Working well</span>${verifiedTag(s)}</div>
        ${s.quote && s.markOf ? `<p>${quoteBtn(s)}</p>` : ""}<p style="margin-top:6px">${escapeHtml(s.why)}</p></div>`).join("")}` : ""}
    </div></div></div>`;
}

function grammarExtra(r) {
  const errors = state.items.filter((i) => i.kind === "error");
  if (!errors.length) return `<p class="note">No grammar or mechanics errors were found.</p>`;
  const by = {};
  errors.forEach((e) => (by[e.type] = by[e.type] || []).push(e));
  const sorted = Object.entries(by).sort((a, b) => b[1].length - a[1].length);
  const [topType, topList] = sorted[0];
  const hide = store.get("tryMode", false);
  return `<div class="pattern"><span class="lbl">Most common pattern</span><b>${escapeHtml(ERROR_LABELS[topType] || topType)}: ${topList.length} of ${errors.length} corrections</b>
      <p>${escapeHtml(topList[0].why)}</p></div>
    <div class="try-line"><span class="sub-title" style="margin:0">Corrections (${errors.length})</span>
      <label class="switch"><input type="checkbox" class="try-toggle" ${hide ? "checked" : ""}><span class="switch-track"></span>Try it yourself</label></div>
    <div class="corrections ${hide ? "hide-answers" : ""}">
      ${sorted.flatMap(([, list]) => list).map((e) => `<div class="corr" data-item="${e.id}">
        <div><span class="lbl">Your sentence</span><p class="val yours">${e.markOf ? quoteBtn(e) : escapeHtml(e.quote)}</p></div>
        <div><span class="lbl">Better</span><p class="val answer">${escapeHtml(e.fix)}</p></div>
        <p class="why answer"><b>${escapeHtml(e.title)}:</b> ${escapeHtml(e.why)}</p>
        <div class="attempt"><input type="text" placeholder="What would you change here?" aria-label="Your correction for: ${escapeHtml(e.quote)}" data-answer="${escapeHtml(e.fix)}">
          <button class="btn btn-quiet btn-sm reveal" type="button">Reveal answer</button></div>
      </div>`).join("")}
    </div>`;
}

const GRADE_TARGETS = { "Middle school (Grades 6-8)": [6, 8], "High school (Grades 9-12)": [9, 12], "English language learner": [6, 10], "Undergraduate": [12, 16] };

function coherenceExtra(r) {
  const s = r.stats;
  const [lo, hi] = GRADE_TARGETS[r.options.grade_level] || [9, 12];
  const pct = (x) => `${(Math.max(0, Math.min(18, x)) / 18) * 100}%`;
  return `<p class="sub-title">Structure &amp; readability (measured)</p>
    <p class="meta">Reading level about grade ${s.grade_level} (Flesch-Kincaid); target for this level: grades ${lo}&ndash;${hi}.</p>
    <div aria-hidden="true"><div class="gauge-track"><div class="gauge-band" style="left:${pct(lo)};width:${pct(hi - lo)}"></div>
      <div class="gauge-marker" style="left:${pct(s.grade_level)}">Grade ${s.grade_level}</div></div>
      <div class="gauge-scale"><span>0</span><span>6</span><span>12</span><span>18</span></div></div>
    <div class="stat-row">
      <div class="stat"><b>${s.paragraphs}</b><span>paragraphs</span></div>
      <div class="stat"><b>${s.sentences}</b><span>sentences</span></div>
      <div class="stat"><b>${s.avg_sentence_length}</b><span>words / sentence</span></div>
      <div class="stat"><b>${s.long_sentences}</b><span>sentences over 35 words</span></div>
    </div>`;
}

const MAP_ORDER = ["lead", "position", "claim", "evidence", "counterclaim", "rebuttal", "concluding_statement"];
const ELEMENT_TIPS = {
  lead: { why: "A strong opening makes the reader want to keep going and points toward the thesis.", todo: "Open with a surprising fact, a short story or a question that leads into your position.", better: "Make sure the opening connects directly to your thesis." },
  position: { why: "The thesis tells the reader exactly what you are arguing.", todo: "Write one sentence that states your opinion and the main reason for it.", better: "Make the thesis specific: what you believe and the main reason, in one sentence." },
  claim: { why: "Claims are the reasons that hold up your position.", todo: "Give each body paragraph one clear reason, stated in its first sentence.", better: "Check that each claim is a reason for your position, not just a related fact." },
  evidence: { why: "Evidence shows claims are true instead of just asserting them.", todo: "After each claim, add a specific example, fact or experience, then explain how it proves the claim.", better: "After each example, add one sentence explaining how it proves the claim." },
  counterclaim: { why: "Addressing the other side shows the argument has been thought through and makes it more convincing.", todo: 'Add a sentence such as "Some people argue that..." with the strongest opposing reason.', better: "State the opposing view at its strongest, then make sure you answer it." },
  rebuttal: { why: "A rebuttal answers the opposing view, so it strengthens the position instead of weakening it.", todo: 'Right after the counterclaim, explain why your position still holds: "However, ..."', better: "Back up the rebuttal with a reason or example, not just disagreement." },
  concluding_statement: { why: "The conclusion reminds the reader of the position and why it matters.", todo: "Restate the thesis in new words and end with why it matters.", better: "Avoid repeating the introduction; end with why the argument matters." },
};

function argumentExtra(r) {
  if (!isArgumentative(r.options.essay_type)) {
    return `<p class="note">Assessed as a <b>${escapeHtml(r.options.essay_type.toLowerCase())}</b> essay: purpose, insight and how well details serve them. It is not penalized for lacking a thesis, counterclaim or rebuttal.</p>`;
  }
  const els = Object.fromEntries((r.feedback.argument_structure || []).map((e) => [e.element, e]));
  const defs = state.rubric?.argument_elements || {};
  const have = MAP_ORDER.filter((k) => els[k]?.present).length;
  return `<p class="sub-title">Argument structure: ${have} of 7 parts found <span class="meta">(PERSUADE 2.0 definitions)</span></p>
    <div class="arg-layout"><ol class="arg-map" aria-label="Argument map">${MAP_ORDER.map((k) => {
      const ok = !!els[k]?.present;
      return `<li class="${ok ? "has" : "missing"}"><button class="node" type="button" data-node="${k}" aria-pressed="false">
        <span class="mark" aria-hidden="true">${ok ? "&#10003;" : "&#10007;"}</span>${escapeHtml(defs[k]?.label || k)}<span class="state">${ok ? "Found" : "Missing"}</span></button></li>`;
    }).join("")}</ol><div class="node-detail" aria-live="polite"><p class="meta">Select a part of the argument to see what it is, where it appears, and what to do next.</p></div></div>`;
}

function selectNode(btn) {
  const key = btn.dataset.node;
  const r = state.result;
  const el = (r.feedback.argument_structure || []).find((e) => e.element === key) || { present: false, quote: "" };
  const def = state.rubric?.argument_elements?.[key] || { label: key, description: "" };
  const tip = ELEMENT_TIPS[key];
  const box = btn.closest(".arg-layout").querySelector(".node-detail");
  $$(".node", btn.closest(".arg-map")).forEach((n) => n.setAttribute("aria-pressed", String(n === btn)));
  box.innerHTML = `<span class="lbl">${el.present ? "Found in the essay" : "Missing from the essay"}</span><h4>${escapeHtml(def.label)}</h4>
    <p class="meta">${escapeHtml(def.description)}</p><dl>
    ${el.present && el.quote ? `<div><dt class="lbl">Where</dt><dd class="quote">&ldquo;${escapeHtml(el.quote)}&rdquo;</dd></div>` : ""}
    <div><dt class="lbl">Why it matters</dt><dd>${escapeHtml(tip.why)}</dd></div>
    <div><dt class="lbl">${el.present ? "Make it stronger" : "What to add"}</dt><dd>${escapeHtml(el.present ? tip.better : tip.todo)}</dd></div></dl>`;
  if (motionOK()) gsap.from(box.children, { opacity: 0, y: 6, duration: DUR.fast, stagger: 0.03 });
}

function originalityExtra(r) {
  return `<p class="note">Originality here means specific examples, distinctive ideas and an authentic voice, not plagiarism or AI detection.
    Vocabulary variety: <b>${r.stats.lexical_diversity}</b> (unique words / total).</p>`;
}

function practiceSection(r, prioritized) {
  const fb = r.feedback;
  const src = prioritized.find((p) => p.item && p.item.quote && p.item.markOf)?.item || null;
  state.practiceSrc = src;
  return `<section class="r-section" data-reveal="late" aria-labelledby="practice-title">
    <header><h2 class="h-section" id="practice-title">Practice the top recommendation</h2><span class="meta">Optional</span></header>
    <div class="practice">
      <p class="lbl">Task</p><p style="font-family:var(--font-text);font-size:1.06rem;margin-top:4px">${escapeHtml(fb.next_step_exercise)}</p>
      ${src ? `<p class="meta" style="margin-top:10px">Start from this sentence: <span class="quote">&ldquo;${escapeHtml(src.quote)}&rdquo;</span></p>` : ""}
      <label class="sr-only" for="practice-input">Your revision</label>
      <textarea id="practice-input" placeholder="Write the improved version here...">${src ? escapeHtml(src.quote) : ""}</textarea>
      <div class="practice-actions"><button class="btn btn-primary btn-sm" type="button" id="check-practice">Check my revision</button>
        <button class="text-btn" type="button" id="revise-essay">Or revise the whole essay and re-analyze &rarr;</button></div>
      <div id="practice-result" aria-live="polite"></div>
    </div></section>`;
}

function compareBox(r) {
  const { before, after } = r.compare;
  const keys = ["overall", ...CRITERIA];
  const rows = keys.map((k) => {
    const d = after[k] - before[k];
    const cls = d > 0 ? "delta-up" : d < 0 ? "delta-down" : "delta-same";
    return `<div class="delta-row"><span>${k === "overall" ? "Overall" : CRIT_NAME[k]}</span><span>${before[k]}/5</span><span aria-hidden="true">&rarr;</span><span><b>${after[k]}/5</b></span>
      <span class="${cls}">${d > 0 ? `&uarr; +${d}` : d < 0 ? `&darr; ${d}` : "no change"}</span></div>`;
  }).join("");
  const gains = CRITERIA.map((k) => [k, after[k] - before[k]]).filter(([, d]) => d > 0).sort((a, b) => b[1] - a[1]);
  return `<section class="compare"><p class="h-section" style="margin-bottom:8px">Compared with the previous version</p>${rows}
    <p class="meta" style="margin-top:8px">${gains.length ? `The revised essay scored higher on this rubric in ${CRIT_NAME[gains[0][0]]}.` : "Scores on this rubric didn't change; check the comments for what's different."}</p></section>`;
}

function metricsHtml(compact) {
  const ev = state.evaluation;
  if (!ev || !ev.metrics || !ev.metrics.length) {
    return `<div class="empty-note"><b>No measured results published yet.</b>Accuracy is measured with <code>eval/run_eval.py</code> (planted errors, PERSUADE 2.0 argument annotations, ELLIPSE human scores). Results appear here only after a run; nothing is estimated.</div>`;
  }
  const rows = ev.metrics.map((m) => `<div class="metric"><b>${escapeHtml(m.label)}</b><span class="value">${Math.round(m.value * 100)}%</span>
    <span>${escapeHtml(m.detail)}</span></div>`).join("");
  return `<div class="metrics">${rows}</div>
    <p class="meta" style="margin-top:8px">${compact ? "Small evaluation samples, measured with this system's own pipeline. " : ""}Last run ${escapeHtml(new Date(ev.generated_at).toLocaleDateString())}. Method: docs/AI_APPROACH.md.</p>`;
}

function renderEssayPanel(r) {
  const marks = state.items.filter((i) => i.span).sort((a, b) => a.span[0] - b.span[0]);
  let html = "";
  let cursor = 0;
  for (const it of marks) {
    html += escapeHtml(r.essay.slice(cursor, it.span[0]));
    const label = it.kind === "strength" ? "Strength" : CRIT_NAME[it.crit];
    html += `<mark class="hl cat-${it.cat} kind-${it.kind}" data-item="${it.id}" tabindex="0" role="button" aria-label="${escapeHtml(label)}: show feedback">${escapeHtml(r.essay.slice(it.span[0], it.span[1]))}</mark>`;
    cursor = it.span[1];
  }
  html += escapeHtml(r.essay.slice(cursor));
  const linked = state.items.filter((i) => i.markOf).length;
  return `<div class="essay-head"><h2 id="essay-panel-title">The student's essay</h2>
      <p class="meta">${linked} comments linked to exact sentences. Select a highlight to see its feedback.</p>
      <div class="legend"><span class="cat-grammar"><i></i>Grammar</span><span class="cat-structure"><i></i>Coherence</span>
        <span class="cat-argument"><i></i>Argument</span><span class="cat-voice"><i></i>Originality</span><span class="cat-strength"><i></i>Strength</span></div></div>
    <div class="essay-scroll" id="essay-scroll"><div class="essay-text">${html}</div></div>`;
}

function openReport(result) {
  state.result = result;
  state.items = buildItems(result);
  $("#report").innerHTML = renderReport(result);
  $("#essay-panel").innerHTML = renderEssayPanel(result);
  show("report");
  revealReport();
}

function revealReport() {
  if (!motionOK()) return;
  const num = $("#overall-num");
  const target = Number(num.textContent);
  const o = { v: 0 };
  gsap.timeline({ defaults: { ease: EASE } })
    .from(".report-head > *", { opacity: 0, y: 10, duration: 0.4, stagger: 0.05 })
    .from(".overall", { opacity: 0, y: 12, duration: 0.45 }, "-=0.2")
    .to(o, { v: target, duration: 0.6, ease: "power2.out", onUpdate: () => (num.textContent = Math.round(o.v)) }, "<")
    .from(".crit", { opacity: 0, y: 8, duration: 0.35, stagger: 0.08 }, "-=0.25")
    .from(".crit-fill", { width: 0, duration: DUR.reveal, stagger: 0.08 }, "<0.1")
    .from("[data-reveal=late], .report-foot", { opacity: 0, y: 14, duration: 0.45, stagger: 0.08 }, "-=0.4")
    .from(".essay-panel", { opacity: 0, x: 14, duration: 0.5 }, 0.3);
}

/* ---------- interactions ---------- */

const isStacked = () => !window.matchMedia("(min-width: 1101px)").matches;

function toggleCrit(block, open = null) {
  const btn = $(".crit-row", block);
  const body = $(".crit-body", block);
  const willOpen = open ?? btn.getAttribute("aria-expanded") !== "true";
  if (willOpen === (btn.getAttribute("aria-expanded") === "true")) return Promise.resolve();
  btn.setAttribute("aria-expanded", String(willOpen));
  if (!motionOK()) { body.hidden = !willOpen; return Promise.resolve(); }
  return new Promise((resolve) => {
    if (willOpen) {
      body.hidden = false;
      gsap.fromTo(body, { height: 0, opacity: 0 }, { height: "auto", opacity: 1, duration: 0.4, ease: "power2.out", clearProps: "height,opacity", onComplete: resolve });
    } else {
      gsap.to(body, { height: 0, opacity: 0, duration: 0.3, ease: "power2.in", onComplete: () => { body.hidden = true; gsap.set(body, { clearProps: "height,opacity" }); resolve(); } });
    }
  });
}

function pulse(el) {
  if (!motionOK() || !el) return;
  gsap.fromTo(el, { opacity: 0.35 }, { opacity: 1, duration: 0.55, ease: "power2.out" });
}

// Feedback -> essay: highlight and scroll to the exact sentence.
function showInEssay(id, fromEl) {
  const it = state.items.find((x) => x.id === id);
  if (!it || !it.markOf) { toast("This comment is about the essay as a whole."); return; }
  const mark = $(`.hl[data-item="${it.markOf}"]`);
  $$(".hl.active, .fb.active, .corr.active").forEach((x) => x.classList.remove("active"));
  mark.classList.add("active");
  fromEl?.closest(".fb, .corr")?.classList.add("active");
  const smooth = motionOK() ? "smooth" : "auto";
  if (isStacked()) {
    state.returnTo = fromEl;
    mark.scrollIntoView({ block: "center", behavior: smooth });
    $("#back-chip").hidden = false;
  } else {
    const box = $("#essay-scroll");
    box.scrollTo({ top: Math.max(0, mark.offsetTop - box.clientHeight / 2), behavior: smooth });
  }
  setTimeout(() => pulse(mark), 150);
}

// Essay -> feedback: find the comment for a highlight, opening its section if needed.
async function showFeedback(id) {
  const ids = state.items.filter((x) => x.markOf === id).map((x) => x.id);
  const visible = (el) => el && el.offsetParent !== null;
  let target = null;
  for (const i of ids) {
    target = $$(`.report [data-item="${i}"]`).filter((el) => !el.matches(".quote-btn")).find(visible);
    if (target) break;
  }
  if (!target) {
    const first = ids.map((i) => $$(`.report [data-item="${i}"]`).find((el) => !el.matches(".quote-btn"))).find(Boolean);
    if (!first) return;
    if (first.closest("#more-improvements")) { $("#more-improvements").hidden = false; $("#show-more")?.remove(); }
    const crit = first.closest(".crit");
    if (crit) await toggleCrit(crit, true);
    target = first;
  }
  $$(".hl.active, .fb.active, .corr.active").forEach((x) => x.classList.remove("active"));
  $(`.hl[data-item="${id}"]`)?.classList.add("active");
  target.classList.add("active");
  target.scrollIntoView({ block: "center", behavior: motionOK() ? "smooth" : "auto" });
  if (motionOK()) gsap.fromTo(target, { x: -6 }, { x: 0, duration: 0.4, ease: "power2.out", delay: 0.2 });
}

$("#view-report").addEventListener("click", async (e) => {
  const q = e.target.closest(".quote-btn");
  if (q) return showInEssay(q.dataset.item, q);
  const mark = e.target.closest(".hl[data-item]");
  if (mark) return showFeedback(mark.dataset.item);
  const row = e.target.closest(".crit-row");
  if (row) return toggleCrit(row.closest(".crit"));
  const node = e.target.closest(".node");
  if (node) return selectNode(node);
  const reveal = e.target.closest(".reveal");
  if (reveal) {
    const corr = reveal.closest(".corr");
    const input = corr.querySelector("input");
    const norm = (s) => s.toLowerCase().replace(/[^a-z0-9' ]/g, "").replace(/\s+/g, " ").trim();
    corr.classList.add("revealed");
    if (input.value.trim()) toast(norm(input.value) === norm(input.dataset.answer) ? "Exactly right." : "Compare your version with the answer.");
    return;
  }
  if (e.target.id === "show-more") {
    $("#more-improvements").hidden = false;
    if (motionOK()) gsap.from("#more-improvements .fb", { opacity: 0, y: 8, duration: DUR.std, stagger: 0.04 });
    e.target.remove();
    return;
  }
  if (e.target.id === "print-report") return printReport();
  if (e.target.id === "copy-report") return copyReport();
  if (e.target.id === "download-report") return downloadReport();
  if (e.target.id === "revise-essay") {
    state.previous = state.result;
    $("#essay").value = state.result.essay;
    onEssayInput();
    openSubmit();
    return;
  }
  if (e.target.id === "check-practice") return checkPractice(e.target);
});
$("#view-report").addEventListener("keydown", (e) => {
  const mark = e.target.closest(".hl[data-item]");
  if (mark && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); showFeedback(mark.dataset.item); }
});
$("#view-report").addEventListener("change", (e) => {
  if (!e.target.matches(".try-toggle")) return;
  store.set("tryMode", e.target.checked);
  const box = e.target.closest(".crit-inner").querySelector(".corrections");
  box.classList.toggle("hide-answers", e.target.checked);
  $$(".corr.revealed", box).forEach((c) => c.classList.remove("revealed"));
});
$("#back-chip").addEventListener("click", () => {
  $("#back-chip").hidden = true;
  (state.returnTo || $("#report")).scrollIntoView({ block: "center", behavior: motionOK() ? "smooth" : "auto" });
});

const VERDICT = { improved: "Improved", getting_there: "Getting there", not_yet: "Not yet" };
async function checkPractice(btn) {
  const out = $("#practice-result");
  const attempt = $("#practice-input").value.trim();
  const src = state.practiceSrc;
  if (attempt.length < 3) { out.innerHTML = `<p class="meta" style="margin-top:10px">Write a revision first.</p>`; return; }
  if (src && attempt === src.quote.trim()) { out.innerHTML = `<p class="meta" style="margin-top:10px">Change the sentence first, then check it.</p>`; return; }
  btn.disabled = true;
  btn.textContent = "Checking…";
  try {
    const fb = state.result.feedback;
    const res = await api("/api/practice", {
      method: "POST",
      body: JSON.stringify({ task: `${fb.next_step_exercise} (Focus: ${fb.top_priorities[0] || ""})`.slice(0, 1500), original: src ? src.quote : "", attempt, grade_level: state.result.options.grade_level }),
    });
    out.innerHTML = `<div class="verdict"><span class="verdict-tag ${res.verdict}">${VERDICT[res.verdict]}</span><p>${escapeHtml(res.feedback)}</p>
      <p><b>Next:</b> ${escapeHtml(res.next_tip)}</p>${src?.rewrite ? `<p class="meta" style="margin-top:6px">One possible revision: <span class="quote">${escapeHtml(src.rewrite)}</span></p>` : ""}</div>`;
    if (motionOK()) gsap.from(".verdict", { opacity: 0, y: 10, duration: DUR.std, ease: EASE });
  } catch (err) {
    const f = err.status === 422 ? { title: "Please check the revision.", text: err.detail } : friendlyError(err);
    out.innerHTML = `<p class="inline-error">${escapeHtml(f.title)} ${escapeHtml(f.text)}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Check my revision";
  }
}

async function printReport() {
  const closed = $$(".crit").filter((c) => $(".crit-row", c).getAttribute("aria-expanded") !== "true");
  closed.forEach((c) => { $(".crit-body", c).hidden = false; });
  $("#more-improvements") && ($("#more-improvements").hidden = false);
  window.print();
  closed.forEach((c) => { $(".crit-body", c).hidden = true; });
}
async function copyReport() {
  try { await navigator.clipboard.writeText(state.result.markdown); toast("Feedback copied. Paste it into an email, LMS or document."); }
  catch { toast("Couldn't copy here. Use Download instead."); }
}
function downloadReport() {
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(new Blob([state.result.markdown], { type: "text/markdown" })),
    download: `essay-feedback-${new Date().toISOString().slice(0, 10)}.md`,
  });
  a.click();
  URL.revokeObjectURL(a.href);
  toast("Report downloaded");
}

/* ============================== dialogs + header ============================== */

function renderRubric() {
  const r = state.rubric;
  if (!r) return;
  const dims = CRITERIA.map((k) => {
    const c = r.criteria[k];
    return `<div class="dim-guide"><h3>${CRIT_NAME[k]}</h3><p>${critQuestion(k, "Argumentative")}</p>
      <p class="meta">Looks for ${escapeHtml(c.look_for.join("; "))}.</p>
      <details><summary class="text-btn small">Scoring guide (1&ndash;5)</summary>
        <div class="levels">${Object.entries(c.levels).sort((a, b) => b[0] - a[0]).map(([s, d]) => `<div><b>${s}</b><span>${escapeHtml(d)}</span></div>`).join("")}</div></details></div>`;
  }).join("");
  const args = MAP_ORDER.map((k) => r.argument_elements?.[k]).filter(Boolean)
    .map((a) => `<div><b>&middot;</b><span><b>${escapeHtml(a.label)}:</b> ${escapeHtml(a.description)}</span></div>`).join("");
  $("#rubric-body").innerHTML = `<p class="meta">These four criteria come straight from the problem statement. Each is scored 1&ndash;5 against written level descriptions (1&ndash;2 needs work, 3 developing, 4&ndash;5 strong).</p>${dims}
    <div class="dim-guide"><h3>Argument structure</h3><p>For argumentative essays the report also checks seven argument parts, using the PERSUADE 2.0 annotation definitions.</p>
      <details><summary class="text-btn small">The seven parts</summary><div class="levels">${args}</div></details></div>
    <p class="meta">Narrative and descriptive essays are judged on purpose and insight, not on thesis or counterargument.</p>`;
}

function renderEval() {
  $("#eval-body").innerHTML = `<p class="meta">How closely the system's feedback matches known answers and human experts. Only measured numbers are shown.</p>${metricsHtml(false)}
    <div class="prose"><p><b>Methods.</b> Grammar error detection and structural flaw detection use essays with deliberately planted problems. Argument accuracy compares the argument checklist with PERSUADE 2.0 expert annotations. Score agreement compares scores with ELLIPSE human raters (within 1 point). Quote grounding is the share of quoted comments found word-for-word in the essay.</p></div>`;
}

document.addEventListener("click", (e) => {
  const opener = e.target.closest("[data-open]");
  if (opener) {
    if (opener.dataset.open === "samples") renderSamples();
    if (opener.dataset.open === "eval") renderEval();
    $(`#dlg-${opener.dataset.open}`)?.showModal();
    return;
  }
  if (e.target.closest("[data-close]")) e.target.closest("dialog").close();
});
$$("dialog").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));

$("#brand").addEventListener("click", () => show("landing"));
$("#cta-analyze").addEventListener("click", (e) => openSubmit({ flipFrom: e.currentTarget }));
$("#new-essay").addEventListener("click", () => {
  const text = $("#essay").value.trim();
  const reviewed = state.result && state.result.essay.trim() === text;
  if (text && !reviewed && !window.confirm("Start a new essay? The current draft will be cleared.")) return;
  $("#essay").value = "";
  $("#assignment").value = "";
  state.previous = null;
  onEssayInput();
  openSubmit();
});

/* ============================== init ============================== */

async function init() {
  if (window.gsap && window.Flip) gsap.registerPlugin(Flip);
  const [health, rubric, samples, evaluation] = await Promise.allSettled([api("/api/health"), api("/api/rubric"), api("/api/samples"), api("/api/evaluation")]);
  if (health.status === "fulfilled") {
    state.health = health.value;
    $("#demo-pill").hidden = !health.value.mock;
    $("#access-wrap").hidden = !health.value.access_code_required;
    $("#about-model").textContent = health.value.mock ? "This deployment is in demo mode (MOCK_LLM=1)." : `Configured: ${health.value.model}.`;
  }
  if (rubric.status === "fulfilled") { state.rubric = rubric.value; renderRubric(); }
  if (samples.status === "fulfilled") { state.samples = samples.value; renderSamples(); }
  if (evaluation.status === "fulfilled") state.evaluation = evaluation.value;
  restoreDraft();

  // ?sample=<file name> loads a sample and analyzes it straight away (handy for demo recordings).
  const sample = state.samples.find((s) => s.id === new URLSearchParams(location.search).get("sample"));
  if (sample) {
    loadSample(sample);
    currentView = "submit";
    settleViews();
    generate();
    return;
  }
  if (hasNib()) Nib.mount("#nib-hero", "hello");
  introLanding();
  setTimeout(() => currentView === "landing" && guide("landing"), 1400);
}

$("#guide-btn").addEventListener("click", () => {
  if (!hasNib()) return toast("The guide couldn't load.");
  guide(currentStep(), { force: true });
});

init();
