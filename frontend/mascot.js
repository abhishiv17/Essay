// Nib: the coach's mascot. A fountain-pen nib drawn in the page's own ink, shown only at moments that need
// a guide (first visit, while an essay is analyzed, when the report opens, when something goes wrong).
// Self-contained: load mascot.css + mascot.js; colours come from the tokens in styles.css.
//
//   Nib.say(text, { mood, actions, duration, once })   floating helper in a corner; returns false if skipped
//   Nib.hide()                                          dismiss the floating helper
//   Nib.mount(elOrSelector, mood, { size })             draw Nib inside a view (hero, analysis, error)
//   Nib.svg(mood)                                       raw SVG string
//   Nib.mute(bool) / Nib.muted                          "don't show tips" (remembered in this browser)
//
// Moods: idle | hello | writing | thinking | cheer | point | oops
// `once: "key"` shows a tip only the first time per browser. `actions: [{ label, onClick }]` adds buttons.

(function () {
  const MOODS = ["idle", "hello", "writing", "thinking", "cheer", "point", "oops"];
  const KEY_MUTED = "nib.muted";
  const KEY_SEEN = "nib.seen";

  const store = {
    get(k, fallback) { try { const v = localStorage.getItem(k); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: tips just repeat */ } },
  };

  // viewBox 0 0 80 100; the nib tip sits at (40, 92). Every part is drawn once; CSS shows the parts a mood needs.
  function svg(mood = "idle") {
    if (!MOODS.includes(mood)) mood = "idle";
    return `<svg class="nib-svg" data-mood="${mood}" viewBox="0 0 80 100" aria-hidden="true" focusable="false">
  <g class="nib-figure-g">
    <path class="nib-ink x-ink" d="M8 97 q8 -4 16 0 t16 0 t16 0 t16 0"/>
    <path class="nib-fill x-blot" d="M27 95 q2 -4 8 -3 q5 -2 10 0 q7 -1 9 3 q1 4 -6 4 q-4 2 -9 0 q-6 2 -10 0 q-4 -1 -2 -4z"/>
    <g class="nib-sway">
      <rect class="nib-collar" x="23" y="4" width="34" height="10" rx="3"/>
      <path class="nib-collar-line" d="M28 9 H52"/>
      <path class="nib-shell" d="M19 20 Q19 14 25 14 H55 Q61 14 61 20 V34 C61 52 50 70 40 92 C30 70 19 52 19 34 Z"/>
      <path class="nib-line nib-slit" d="M40 63 V89"/>
      <circle class="nib-hole" cx="40" cy="59" r="3"/>
      <path class="nib-shine" d="M24.5 22 V33"/>

      <circle class="nib-cheek x-cheeks" cx="26.5" cy="41" r="2.8"/>
      <circle class="nib-cheek x-cheeks" cx="53.5" cy="41" r="2.8"/>

      <g class="e-open nib-blink"><circle class="nib-fill" cx="32" cy="33" r="3"/><circle class="nib-fill" cx="48" cy="33" r="3"/></g>
      <g class="e-happy"><path class="nib-line" d="M28.5 34.5 q3.5 -4.5 7 0"/><path class="nib-line" d="M44.5 34.5 q3.5 -4.5 7 0"/></g>
      <g class="e-up"><circle class="nib-fill" cx="33.5" cy="31" r="3"/><circle class="nib-fill" cx="49.5" cy="31" r="3"/></g>
      <g class="e-worried">
        <circle class="nib-fill" cx="32" cy="34" r="2.6"/><circle class="nib-fill" cx="48" cy="34" r="2.6"/>
        <path class="nib-line" d="M27 28.5 L35 26"/><path class="nib-line" d="M53 28.5 L45 26"/>
      </g>

      <path class="nib-line m-smile" d="M35 42 q5 5 10 0"/>
      <path class="nib-fill m-grin" d="M34 41 q6 8 12 0 z"/>
      <ellipse class="nib-fill m-open" cx="40" cy="43.5" rx="2.6" ry="3.2"/>
      <path class="nib-line m-flat" d="M37.5 43.5 h5"/>
      <path class="nib-line m-wobble" d="M34 44 q2 -2 4 0 t4 0 t4 0"/>

      <path class="nib-line x-chin" d="M60.5 40 q10 -6 6 -19"/>
    </g>

    <path class="nib-line a-left-down" d="M19.5 40 q-7 5 -8 14"/>
    <path class="nib-line a-right-down" d="M60.5 40 q7 5 8 14"/>
    <path class="nib-line a-right-wave" d="M60.5 38 q9 -4 11 -15"/>
    <path class="nib-line a-left-up" d="M19.5 38 q-9 -4 -11 -15"/>
    <path class="nib-line a-right-up" d="M60.5 38 q9 -4 11 -15"/>
    <path class="nib-line a-right-point" d="M60.5 40 q8 0 16 -3"/>

    <g class="x-ticks"><path class="nib-line" d="M6 14 l-3 -3"/><path class="nib-line" d="M9 9 l-1 -4"/><path class="nib-line" d="M74 14 l3 -3"/><path class="nib-line" d="M71 9 l1 -4"/></g>
    <g class="x-dots"><circle class="nib-fill" cx="66" cy="10" r="1.6"/><circle class="nib-fill" cx="71" cy="6" r="2"/><circle class="nib-fill" cx="77" cy="2.5" r="2.3"/></g>
    <path class="nib-drop x-sweat" d="M64 17 q3.5 5 0 7.5 q-3.5 -2.5 0 -7.5z"/>
  </g>
</svg>`;
  }

  function mount(target, mood = "idle", { size } = {}) {
    const el = typeof target === "string" ? document.querySelector(target) : target;
    if (!el) return null;
    el.classList.add("nib-mount");
    if (size) el.style.setProperty("--nib-size", typeof size === "number" ? `${size}px` : size);
    el.innerHTML = svg(mood);
    return el;
  }

  /* ---------- floating helper ---------- */
  let helper = null;
  let timer = 0;

  function ensureHelper() {
    if (helper) return helper;
    helper = document.createElement("div");
    helper.className = "nib-helper";
    helper.hidden = true;
    helper.innerHTML = `
      <div class="nib-bubble" role="status" aria-live="polite">
        <button class="nib-close" type="button" aria-label="Dismiss tip">&times;</button>
        <p class="nib-text"></p>
        <div class="nib-actions"></div>
        <button class="nib-mute" type="button">Don't show tips</button>
      </div>
      <div class="nib-avatar"></div>`;
    document.body.appendChild(helper);
    helper.querySelector(".nib-close").addEventListener("click", hide);
    helper.querySelector(".nib-mute").addEventListener("click", () => { mute(true); hide(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !helper.hidden) hide(); });
    return helper;
  }

  function say(text, { mood = "idle", actions = [], duration = 8000, once = "", corner = "br" } = {}) {
    if (store.get(KEY_MUTED, false)) return false;
    if (once) {
      const seen = store.get(KEY_SEEN, []);
      if (seen.includes(once)) return false;
      store.set(KEY_SEEN, [...seen, once]);
    }
    const h = ensureHelper();
    clearTimeout(timer);
    h.dataset.corner = corner;
    h.querySelector(".nib-text").textContent = text;
    h.querySelector(".nib-avatar").innerHTML = svg(mood);
    const row = h.querySelector(".nib-actions");
    row.innerHTML = "";
    row.hidden = !actions.length;
    for (const a of actions) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "nib-action";
      b.textContent = a.label;
      b.addEventListener("click", () => { hide(); a.onClick && a.onClick(); });
      row.appendChild(b);
    }
    h.hidden = false;
    h.classList.remove("is-leaving");
    void h.offsetWidth; // restart the entrance animation
    h.classList.add("is-in");
    // Tips with buttons wait for the user; plain tips leave on their own.
    if (duration && !actions.length) timer = setTimeout(hide, duration);
    return true;
  }

  function hide() {
    if (!helper || helper.hidden) return;
    clearTimeout(timer);
    helper.classList.remove("is-in");
    helper.classList.add("is-leaving");
    const done = () => { helper.hidden = true; helper.classList.remove("is-leaving"); };
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) done();
    else setTimeout(done, 220);
  }

  function mute(on = true) {
    store.set(KEY_MUTED, !!on);
    if (on) hide();
  }

  window.Nib = {
    say, hide, mount, svg, mute, moods: MOODS,
    get muted() { return store.get(KEY_MUTED, false); },
  };
})();
