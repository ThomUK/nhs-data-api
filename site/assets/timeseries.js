import { getJSON, el, fmtValue, fmtSigned, renderChrome, showError, status, fmtMonth } from "./common.js";
import { lineChart, sparkline, tableView, detectAnomalies } from "./charts.js";

renderChrome("timeseries.html");
const $ = (id) => document.getElementById(id);
const content = $("content"), notices = $("notices");
const f = { view: $("f-view"), org: $("f-org"), tf: $("f-tf"), measure: $("f-measure"),
  rel: $("f-rel"), abs: $("f-abs"), exp: $("f-exp"), flagged: $("f-flagged") };

const GROUPS = [
  ["Waiting list", ["waiting_list_total", "waiting_list_dta", "pct_waiting_list_dta"]],
  ["Waiting times", ["pct_within_18_weeks", "median_wait_weeks", "p92_wait_weeks", "waiting_over_18_weeks",
    "waiting_over_52_weeks", "waiting_over_65_weeks", "waiting_over_78_weeks", "waiting_over_104_weeks", "approaching_52_weeks"]],
  ["Activity", ["clock_starts", "clock_stops_admitted", "clock_stops_non_admitted", "clock_stops_total",
    "pct_completed_within_18_weeks_admitted", "pct_completed_within_18_weeks_non_admitted",
    "median_wait_completed_admitted_weeks", "median_wait_completed_non_admitted_weeks"]],
  ["Month-on-month change", ["waiting_list_change_mom", "waiting_list_change_mom_like_for_like",
    "waiting_over_52_weeks_change_mom", "waiting_over_52_weeks_change_mom_like_for_like",
    "unreported_removals", "unreported_removals_like_for_like"]],
  ["Data quality", ["providers_submitting"]],
];

let meta, mode = "org";
const cache = new Map();
const state = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));

async function series(view) {
  if (!cache.has(view)) cache.set(view, await getJSON(`data/timeseries/${view}.json`));
  return cache.get(view);
}
const measureById = () => Object.fromEntries(meta.measures.map((m) => [m.id, m]));
const visibleMeasures = () => meta.measures.filter((m) => f.exp.checked || m.status !== "experimental");
const thresholds = () => ({ rel: Number(f.rel.value) || 20, abs: Number(f.abs.value) || 3 });

function saveHash() {
  const p = new URLSearchParams({ mode, view: f.view.value, tf: f.tf.value, measure: f.measure.value,
    rel: f.rel.value, abs: f.abs.value });
  if (f.org.value) p.set("org", f.org.value);
  if (f.exp.checked) p.set("exp", "1");
  history.replaceState(null, "", `#${p}`);
}

function orgFromInput(data) {
  const v = f.org.value.trim().toUpperCase();
  if (!v) return data.orgs[0];
  return data.orgs.find((o) => o.code.toUpperCase() === v)
    || data.orgs.find((o) => `${o.code} · ${o.name}`.toUpperCase() === v)
    || data.orgs.find((o) => (o.name || "").toUpperCase().includes(v));
}

function setNotices(data) {
  const out = [];
  if (data.periods.length < 6) {
    out.push(el("div", { class: "notice info" }, status("neutral", "i", "Short history"),
      el("span", { text: ` Only ${data.periods.length} month${data.periods.length === 1 ? "" : "s"} loaded (${data.periods.map(fmtMonth).join(", ")}). The unusual-change rule needs 8+ months; month-on-month measures start from the second month.` })));
  }
  if (f.view.value !== "national") {
    out.push(el("p", { class: "small muted", style: "margin:0 0 12px",
      text: "Non-national views show all specialties combined (C_999). Specialty series are available for England." }));
  }
  notices.replaceChildren(...out);
}

async function renderOrg() {
  const data = await series(f.view.value);
  setNotices(data);
  const org = orgFromInput(data);
  if (!org) { content.replaceChildren(el("p", { class: "muted", text: "No organisation matches. Try an ODS code such as RJ1." })); return; }
  const tf = f.view.value === "national" ? f.tf.value : "C_999";
  const s = org.series[tf];
  if (!s) { content.replaceChildren(el("p", { class: "muted", text: `No data for ${org.name} in this specialty.` })); return; }
  const byId = measureById();
  const visible = new Set(visibleMeasures().map((m) => m.id));
  const blocks = [el("h2", { style: "margin-top:8px" }, `${org.name} `, el("span", { class: "muted small", text: `${org.code} · ${meta.treatment_functions[tf] || tf}` }))];
  let flaggedCount = 0;
  for (const [group, ids] of GROUPS) {
    const cards = [];
    for (const id of ids.filter((i) => visible.has(i) && s[i])) {
      const m = byId[id], values = s[id];
      const flags = detectAnomalies(values, m.unit, thresholds(), { isChange: !!m.requires_previous_month });
      flaggedCount += flags.filter((x) => x.length).length;
      const last = values.length - 1;
      const prev = last > 0 ? values[last - 1] : null;
      const delta = values[last] !== null && prev !== null ? values[last] - prev : null;
      cards.push(el("article", { class: "card chart-card" },
        el("header", {}, el("h3", { text: m.label }), m.status === "experimental" ? el("span", { class: "chip", text: "experimental" }) : null),
        el("div", {}, el("span", { class: "value", text: fmtValue(values[last], m.unit) }), " ",
          el("span", { class: "delta", text: delta === null ? "" : `${fmtSigned(delta, m.unit)} on previous month` })),
        lineChart({ periods: data.periods, values, unit: m.unit, flags, label: m.label }),
        tableView(data.periods, values, m.unit, flags)));
    }
    if (cards.length) blocks.push(el("h2", { text: group }), el("div", { class: "grid-cards" }, cards));
  }
  blocks.splice(1, 0, el("p", { class: "small" }, flaggedCount
    ? status("warning", "⚠", `${flaggedCount} point${flaggedCount > 1 ? "s" : ""} flagged for review`)
    : status("good", "✓", "No points flagged")));
  content.replaceChildren(...blocks);
}

async function renderScan() {
  const data = await series(f.view.value);
  setNotices(data);
  const tf = f.view.value === "national" ? f.tf.value : "C_999";
  const m = measureById()[f.measure.value];
  const last = data.periods.length - 1;
  const rows = data.orgs.map((o) => {
    const values = o.series[tf]?.[m.id];
    if (!values) return null;
    const flags = detectAnomalies(values, m.unit, thresholds(), { isChange: !!m.requires_previous_month });
    const cur = values[last], prev = last > 0 ? values[last - 1] : null;
    let change = null, sortKey = -1;
    if (cur !== null && prev !== null) {
      change = cur - prev;
      sortKey = m.unit === "percent" || m.unit === "weeks" ? Math.abs(change)
        : Math.abs(prev) >= 20 ? Math.abs(change / prev) * 100 : 0;
    } else if (cur === null && prev !== null) sortKey = 1e12 + Math.abs(prev); // dropped out: biggest first
    const nFlags = flags.filter((x) => x.length).length;
    return { o, values, flags, cur, change, prev, sortKey, nFlags };
  }).filter(Boolean)
    .filter((r) => !f.flagged.checked || r.nFlags)
    .sort((a, b) => (b.nFlags > 0) - (a.nFlags > 0) || b.sortKey - a.sortKey);
  const pctChange = (r) => r.change === null || m.unit === "percent" || m.unit === "weeks" || !r.prev ? ""
    : ` (${r.change / Math.abs(r.prev) >= 0 ? "+" : "−"}${Math.abs((r.change / Math.abs(r.prev)) * 100).toFixed(1)}%)`;
  const limit = 200;
  const body = rows.slice(0, limit).map((r) => el("tr", { class: "scan-row" },
    el("td", {}, el("a", { href: "#", text: r.o.name || r.o.code, onclick: (e) => {
      e.preventDefault(); f.org.value = r.o.code; setMode("org"); } }),
      el("div", { class: "small muted", text: r.o.code })),
    el("td", { class: "spark" }, sparkline(r.values, r.flags)),
    el("td", { class: "num", text: fmtValue(r.cur, m.unit) }),
    el("td", { class: "num", text: r.cur === null && r.prev !== null ? `missing (was ${fmtValue(r.prev, m.unit)})` : `${fmtSigned(r.change, m.unit)}${pctChange(r)}` }),
    el("td", {}, r.nFlags ? status("warning", "⚠", [...new Set(r.flags.flat())].join("; ")) : el("span", { class: "muted small", text: "–" }))));
  content.replaceChildren(
    el("p", { class: "small muted", text: `${rows.length} organisations · sorted by flagged first, then size of latest month-on-month change${rows.length > limit ? ` · showing first ${limit}` : ""}` }),
    el("div", { class: "table-wrap card", style: "padding:0" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "Organisation" }), el("th", { text: "Trend" }),
        el("th", { class: "num", text: `Latest (${fmtMonth(data.periods[last])})` }), el("th", { class: "num", text: "Change" }), el("th", { text: "Flags" }))),
      el("tbody", {}, body))));
}

async function render() {
  saveHash();
  content.style.opacity = "0.5";
  try {
    if (mode === "org") await renderOrg(); else await renderScan();
  } catch (e) { showError(content, e); }
  content.style.opacity = "";
}

async function onViewChange() {
  const data = await series(f.view.value);
  $("org-list").replaceChildren(...data.orgs.map((o) => el("option", { value: o.code, text: `${o.code} · ${o.name}` })));
  f.tf.disabled = f.view.value !== "national";
  if (f.tf.disabled) f.tf.value = "C_999";
  if (!data.orgs.some((o) => o.code === f.org.value)) f.org.value = data.orgs[0]?.code || "";
  render();
}

function fillMeasures() {
  const keep = f.measure.value;
  f.measure.replaceChildren(...visibleMeasures().map((m) => el("option", { value: m.id, text: m.label })));
  if ([...f.measure.options].some((o) => o.value === keep)) f.measure.value = keep;
}

function setMode(next) {
  mode = next;
  for (const b of document.querySelectorAll("#f-mode button")) b.setAttribute("aria-pressed", b.dataset.mode === mode);
  $("l-org").hidden = mode !== "org";
  $("l-measure").hidden = mode !== "scan";
  $("l-flagged").hidden = mode !== "scan";
  render();
}

getJSON("data/measures.json").then(async (m) => {
  meta = m;
  f.view.replaceChildren(...meta.views.map((v) => el("option", { value: v.id, text: v.label })));
  f.tf.replaceChildren(...Object.entries(meta.treatment_functions).map(([c, n]) => el("option", { value: c, text: n })));
  f.exp.checked = state.exp === "1";
  fillMeasures();
  if (state.view) f.view.value = state.view;
  if (state.tf) f.tf.value = state.tf;
  if (state.measure) f.measure.value = state.measure;
  if (state.rel) f.rel.value = state.rel;
  if (state.abs) f.abs.value = state.abs;
  f.org.value = state.org || (f.view.value === "national" ? "ENG" : "");
  if (!state.measure) f.measure.value = "waiting_list_total";
  mode = state.mode === "scan" ? "scan" : "org";
  for (const b of document.querySelectorAll("#f-mode button")) b.addEventListener("click", () => setMode(b.dataset.mode));
  f.view.addEventListener("change", onViewChange);
  f.org.addEventListener("change", render);
  for (const k of ["tf", "measure", "rel", "abs", "flagged"]) f[k].addEventListener("change", render);
  f.exp.addEventListener("change", () => { fillMeasures(); render(); });
  const data = await series(f.view.value);
  $("org-list").replaceChildren(...data.orgs.map((o) => el("option", { value: o.code, text: `${o.code} · ${o.name}` })));
  f.tf.disabled = f.view.value !== "national";
  setMode(mode);
}).catch((e) => showError(content, e));
