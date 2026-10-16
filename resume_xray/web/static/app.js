// resume-xray page logic. The resume stays in this tab's memory and is sent only to the local
// server on this computer; every change (job text, keywords) sends it again and nothing is stored.
"use strict";

const $ = (id) => document.getElementById(id);
const state = { file: null, add: [], remove: [], titleTouched: false, data: null, seq: 0, lang: "en", view: null };

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function t() {
  return window.I18N[state.lang];
}

// Language ---------------------------------------------------------------------------------------

function loadLanguage() {
  let saved = null;
  try {
    saved = localStorage.getItem("rx-lang");
  } catch (_) {}
  state.lang = saved === "tr" || saved === "en" ? saved : (navigator.language || "").toLowerCase().startsWith("tr") ? "tr" : "en";
}

function setLanguage(lang) {
  state.lang = lang;
  try {
    localStorage.setItem("rx-lang", lang);
  } catch (_) {}
  applyLanguage();
}

function applyLanguage() {
  const strings = t();
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const value = strings[node.dataset.i18n];
    if (typeof value === "string") node.textContent = value;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = strings[node.dataset.i18nPlaceholder];
  });
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang)));
  renderMine();
  renderGo();
  renderFaq();
  if (state.data) render(state.data);
}

// Questions are native <details>, so they open with the keyboard and work without this script's
// state; open ones stay open when the language changes.
function renderFaq() {
  const list = $("faq-list");
  const open = new Set([...list.querySelectorAll("details[open]")].map((d) => d.dataset.i));
  list.replaceChildren();
  t().faq.forEach(([question, answer], i) => {
    const item = el("details");
    item.dataset.i = String(i);
    item.open = open.has(String(i));
    item.append(el("summary", "", question), el("p", "", answer));
    list.append(item);
  });
}

// Input ------------------------------------------------------------------------------------------

// Choosing a file only selects it; the Analyze button starts the reading. Once results are on the
// page, keyword and job edits update them right away.
function setFile(file) {
  if (!file) return;
  state.file = file;  // keywords stay: the same search can be tried on another resume
  state.data = null;
  state.view = null;
  state.seq++;
  $("results").hidden = true;
  showError("");
  renderGo();
}

function renderGo() {
  const s = t();
  $("go").hidden = !state.file;
  if (state.file && !state.data) {
    $("drop-title").textContent = state.file.name;
    $("drop-sub").textContent = s.file_ready;
  }
}

let timer = null;
function analyzeSoon() {
  clearTimeout(timer);
  if (state.data) timer = setTimeout(analyze, 650);
}

function refresh() {
  if (state.data) analyze();
}

function showError(message) {
  const box = $("file-error");
  box.textContent = message || "";
  box.hidden = !message;
}

async function analyze() {
  if (!state.file) return;
  const seq = ++state.seq;
  $("results").hidden = false;
  $("busy").hidden = false;
  showError("");

  const form = new FormData();
  form.append("file", state.file);
  form.append("job", $("job").value);
  form.append("title", $("title").value);
  form.append("add", JSON.stringify(state.add));
  form.append("remove", JSON.stringify(state.remove));

  let response;
  try {
    response = await fetch("/api/analyze", { method: "POST", body: form });
  } catch (_) {
    if (seq === state.seq) {
      $("busy").hidden = true;
      showError(t().err_network);
    }
    return;
  }
  if (seq !== state.seq) return;
  $("busy").hidden = true;
  if (!response.ok) {
    let code = "unreadable_file";
    try {
      code = (await response.json()).detail || code;
    } catch (_) {}
    showError(t()["err_" + code] || t().err_unreadable_file);
    $("results").hidden = true;
    return;
  }
  const data = await response.json();
  if (!state.titleTouched && !$("title").value && data.job_match && data.job_match.job_title) {
    $("title").value = data.job_match.job_title;
  }
  state.data = data;
  render(data);
}

// Rendering --------------------------------------------------------------------------------------

function render(data) {
  const s = t();
  $("drop-title").textContent = data.document;
  $("drop-sub").textContent = data.kind === "pdf" ? s.file_sub_pdf(data.pages) : s.file_sub_docx;

  const problems = data.findings.filter((f) => f.severity !== "info");
  $("fix-count").textContent = String(problems.length);
  $("fix-count").hidden = !problems.length;
  const verdict = s.verdict[data.verdict];
  const [readTitle, readText] = typeof verdict === "function" ? verdict(problems.length) : verdict;
  $("sum-read").textContent = readTitle;
  $("sum-read-text").textContent = readText;

  renderFindings(data);
  renderKeywords(data.job_match);
  renderSeen(data);
  renderTechnical(data);
}

function phrase(finding) {
  const make = t().findings[finding.code];
  return make ? make(finding.params || {}, finding, state.lang) : [finding.title, finding.detail];
}

// Fixes and tips are two lists; each item is tinted in its list's status color.
function renderFindings(data) {
  const shown = data.findings.filter((f) => f.code !== "columns_ok");
  const fixes = shown.filter((f) => f.severity !== "info");
  const tips = shown.filter((f) => f.severity === "info");
  fill($("findings"), fixes, t().fix);
  fill($("tips"), tips, t().tip);
  $("tips-title").hidden = !tips.length;
  $("all-good").hidden = fixes.length > 0;
  renderGood(data);
}

// What passed. An item is listed only when no finding touches it in any reader, so "good" is never
// said about something that breaks in some ATSs.
function renderGood(data) {
  const s = t().good;
  const codes = new Set(data.findings.map((f) => f.code));
  const none = (...list) => list.every((c) => !codes.has(c));
  const items = [];
  if (none("no_text_layer", "reader_failed")) {
    if (none("garbled", "words_broken")) items.push(s.text);
    if (codes.has("columns_ok")) items.push(s.columns);
    else if (none("columns_scramble", "order_differs")) items.push(s.order);
    if (data.kind === "docx" && none("contact_in_header", "text_boxes")) items.push(s.parts);
    const headings = Object.values(data.sections);
    if (headings.length && none("section_missing", "heading_unknown", "heading_merged")) items.push(s.headings(list(headings, state.lang)));
    const found = ["email", "phone", "linkedin"].filter((k) => data.fields[k]).map((k) => s.contact_items[k]);
    const and = state.lang === "tr" ? " ve " : " and ";
    if (found.length) items.push(s.contact(found.length < 2 ? found[0] : found.slice(0, -1).join(", ") + and + found[found.length - 1]));
  }
  const box = $("good");
  box.replaceChildren(...items.map((text) => el("li", "", text)));
  $("good-title").hidden = !items.length;
}

function fill(list, findings, label) {
  list.replaceChildren();
  findings.forEach((finding, i) => {
    const [title, text] = phrase(finding);
    const item = el("li");
    const body = el("span", "body");
    body.append(el("span", "visually-hidden", `${label} ${i + 1}: `), el("strong", "", title), el("span", "sub", text));
    item.append(body);
    list.append(item);
  });
}

function status(term) {
  if (term.level === "missing") return "no";
  if (term.level === "exact" && !term.lost_in.length) return "ok";
  return "part";
}

function renderKeywords(match) {
  const s = t();
  const box = $("keywords");
  if (!match) {
    [$("sum-match").textContent, $("sum-match-text").textContent] = s.match_none;
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const required = match.terms.filter((x) => x.kind === "required");
  const basis = required.length ? required : match.terms;
  const coverage = required.length ? match.required_coverage : match.preferred_coverage;
  if (!basis.length) {
    [$("sum-match").textContent, $("sum-match-text").textContent] = s.match_empty;
  } else {
    const count = (st) => basis.filter((x) => status(x) === st).length;
    [$("sum-match").textContent, $("sum-match-text").textContent] = s.match_summary(
      Math.round((coverage || 0) * 100), count("ok"), basis.length, count("part"));
  }

  const bar = $("bar");
  bar.replaceChildren();
  const order = ["no", "part", "ok"];
  const counts = { no: 0, part: 0, ok: 0 };
  for (const st of order) {
    for (const term of basis.filter((x) => status(x) === st)) {
      const seg = el("span", st);
      seg.style.flex = String(term.weight);
      bar.append(seg);
      counts[st]++;
    }
  }
  bar.setAttribute("aria-label", s.bar_label(counts.no, counts.part, counts.ok));

  const groups = $("groups");
  groups.replaceChildren();
  for (const st of order) {
    const terms = match.terms.filter((x) => status(x) === st);
    if (!terms.length) continue;
    const group = el("div", "group");
    const head = el("p", "", s.groups[st][0] + " ");
    head.append(el("span", "", "· " + s.groups[st][1]));
    group.append(head);
    for (const term of terms) group.append(chip(term, st));
    groups.append(group);
  }

  const checks = $("checks");
  checks.replaceChildren();
  const line = (label, text, good) => {
    const li = el("li");
    li.append(el("span", "k", label), el("span", good === undefined ? "" : good ? "good" : "bad", text));
    checks.append(li);
  };
  if (match.job_title) {
    line(s.check_title, match.title_match ? s.title_found(match.title_match) : s.title_missing(match.job_title), Boolean(match.title_match));
  } else if (basis.some((x) => x.source === "job")) {
    line(s.check_title, s.title_unknown);
  }
  if (match.years_required) {
    const have = match.years_in_resume;
    line(s.check_years, s.years(match.years_required, have), have !== null && have >= match.years_required);
  }
  if (match.degree_required) {
    const rank = ["Bachelor", "Master", "PhD"];
    const ok = match.degree_in_resume && rank.indexOf(match.degree_in_resume) >= rank.indexOf(match.degree_required);
    line(s.check_degree, s.degree(s.degrees[match.degree_required], match.degree_in_resume && s.degrees[match.degree_in_resume]), Boolean(ok));
  }
}

function chip(term, st) {
  const s = t();
  const button = el("button", `chip ${st}${term.source === "user" ? " user" : ""}`);
  button.type = "button";
  button.setAttribute("aria-label", s.remove_kw(term.job_wording));
  button.append(el("span", "", term.job_wording));
  let note = "";
  if (term.level === "word_form" || term.level === "synonym") note = s.you_wrote(term.resume_wording);
  else if (st === "part") note = s.split_in_some;
  if (term.kind === "preferred") note = note ? `${note}, ${s.nice_to_have}` : s.nice_to_have;
  if (note) button.append(el("span", "said", note));
  button.append(el("span", "x", "×"));
  button.addEventListener("click", () => removeTerm(term));
  return button;
}

function removeTerm(term) {
  const key = term.job_wording.toLocaleLowerCase();
  if (term.source === "user") {
    state.add = state.add.filter((w) => w.toLocaleLowerCase() !== key && w.toLocaleLowerCase() !== term.name.toLocaleLowerCase());
  }
  state.remove.push(term.job_wording);
  renderMine();
  refresh();
}

// The user's own keywords, listed under their input so they can be typed before a resume is chosen.
function renderMine() {
  const box = $("mine");
  box.replaceChildren();
  for (const word of state.add) {
    const button = el("button", "chip mine-chip user");
    button.type = "button";
    button.setAttribute("aria-label", t().mine_remove(word));
    button.append(el("span", "", word), el("span", "x", "×"));
    button.addEventListener("click", () => {
      state.add = state.add.filter((w) => w !== word);
      renderMine();
      refresh();
    });
    box.append(button);
  }
}

function addWords(text) {
  const known = new Set(state.add.map((w) => w.toLocaleLowerCase()));
  for (const word of text.split(/[,;\n]/).map((w) => w.trim()).filter(Boolean)) {
    const key = word.toLocaleLowerCase();
    state.remove = state.remove.filter((w) => w.toLocaleLowerCase() !== key);
    if (!known.has(key)) state.add.push(word);
    known.add(key);
  }
  renderMine();
  refresh();
}

function renderTechnical(data) {
  const s = t();
  const list = $("tech-findings");
  list.replaceChildren();
  for (const finding of data.findings) {
    const li = el("li", "", phrase(finding)[0]);
    const readers = (finding.strategies || []).map((x) => s.readers[x]).join(", ");
    li.append(el("div", "meta", s.tech_meta(finding.check, readers)));
    if (finding.examples && finding.examples.length) li.append(el("div", "meta", `${s.examples}: ${finding.examples.join(", ")}`));
    list.append(li);
  }
}

// The text each reader gets, one tab per reader. A reader that some problem affects is marked.
function renderSeen(data) {
  const s = t();
  const strategies = Object.keys(data.readings);
  const broken = new Set(data.findings.filter((f) => f.severity !== "info").flatMap((f) => f.strategies || []));
  // Open on a reading that has a problem, so the user sees what goes wrong first.
  if (!strategies.includes(state.view)) state.view = strategies.find((x) => broken.has(x)) || strategies[strategies.length - 1];
  const tabs = $("seen-tabs");
  tabs.replaceChildren();
  for (const strategy of strategies) {
    const name = s.readers[strategy];
    const tab = el("button", "tab" + (broken.has(strategy) ? " warn" : ""), name[0].toLocaleUpperCase(state.lang) + name.slice(1));
    tab.type = "button";
    tab.id = "tab-" + strategy;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(strategy === state.view));
    tab.tabIndex = strategy === state.view ? 0 : -1;
    if (broken.has(strategy)) tab.setAttribute("aria-description", s.seen_warn);
    tab.addEventListener("click", () => {
      state.view = strategy;
      renderSeen(data);
      $("tab-" + strategy).focus();
    });
    tab.addEventListener("keydown", (e) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      state.view = strategies[(strategies.indexOf(strategy) + step + strategies.length) % strategies.length];
      renderSeen(data);
      $("tab-" + state.view).focus();
    });
    tabs.append(tab);
  }
  const text = data.readings[state.view];
  $("seen-caption").textContent = s.reading_titles[state.view] + (broken.has(state.view) ? ". " + s.seen_warn[0].toUpperCase() + s.seen_warn.slice(1) + "." : "");
  $("seen-text").setAttribute("aria-labelledby", "tab-" + state.view);
  $("seen-text").textContent = text === null ? s.reader_failed_text : text || s.no_text;
}

// Wiring -----------------------------------------------------------------------------------------

function wire() {
  const input = $("file");
  input.addEventListener("change", () => setFile(input.files[0]));
  $("hero-choose").addEventListener("click", () => input.click());
  $("analyze").addEventListener("click", () => {
    analyze();
    $("results").scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });

  const drop = $("drop");
  ["dragenter", "dragover"].forEach((type) => drop.addEventListener(type, () => drop.classList.add("over")));
  ["dragleave", "drop"].forEach((type) => drop.addEventListener(type, () => drop.classList.remove("over")));
  // A file dropped anywhere else must not make the browser open it instead of the page.
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });

  $("job").addEventListener("input", () => {
    if (!state.titleTouched) $("title").value = "";
    analyzeSoon();
  });
  $("title").addEventListener("input", () => {
    state.titleTouched = $("title").value.trim() !== "";
    analyzeSoon();
  });

  const addInput = $("add-input");
  $("add-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const word = addInput.value.trim();
    if (!word) {
      showAddError(true);
      return;
    }
    addInput.value = "";
    addWords(word);
  });
  addInput.addEventListener("input", () => showAddError(false));
  $("add-more").addEventListener("click", () => {
    addInput.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    addInput.focus({ preventScroll: true });
  });

  document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => setLanguage(b.dataset.lang)));
}

function showAddError(show) {
  let note = $("add-error");
  if (!note) {
    note = el("p", "error add-error");
    note.id = "add-error";
    note.setAttribute("role", "alert");
    $("add-form").after(note);
  }
  note.textContent = show ? t().err_empty : "";
  note.hidden = !show;
}

loadLanguage();
wire();
applyLanguage();
