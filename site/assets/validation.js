import { getJSON, el, fmtMonth, status, renderChrome, showError } from "./common.js";

renderChrome("validation.html");
const content = document.getElementById("content");
const nf = new Intl.NumberFormat("en-GB");

function runCard(run) {
  const checks = run.checks.map((c) => el("tr", {},
    el("td", { text: c.measure.replaceAll("_", " ") }),
    el("td", { class: "num", text: nf.format(run.rows_compared) }),
    el("td", { class: "num", text: nf.format(c.mismatches) }),
    el("td", { text: c.tolerance ? `±${c.tolerance.toFixed(2)} (1 dp rounding)` : "exact" }),
    el("td", {}, c.mismatches ? status("critical", "✕", "Mismatch") : status("good", "✓", "Match"))));
  const samples = run.checks.filter((c) => c.mismatches).map((c) => el("details", {},
    el("summary", { text: `${c.measure}: first ${c.sample.length} mismatches` }),
    el("pre", { class: "filename", text: c.sample.map((r) => JSON.stringify(r)).join("\n") })));
  return el("article", { class: "card", style: "margin-bottom:16px" },
    el("div", { style: "display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline" },
      el("h3", { text: `RTT ${fmtMonth(run.period)}: provider workbook` }),
      run.ok ? status("good", "✓", "All checks match") : status("critical", "✕", "Mismatches found")),
    el("p", { class: "small muted", style: "margin:4px 0 10px" },
      `${run.workbook} · run ${run.run_at.replace("T", " ").slice(0, 16)} UTC · ${nf.format(run.rows_published)} published rows, `,
      `${run.missing_from_ours} missing from ours, ${run.missing_from_published} not in published`),
    el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "Measure" }), el("th", { class: "num", text: "Rows" }),
        el("th", { class: "num", text: "Mismatches" }), el("th", { text: "Tolerance" }), el("th", { text: "Result" }))),
      el("tbody", {}, checks))),
    ...samples);
}

function submissions(subs) {
  return el("div", { class: "table-wrap card", style: "padding:0" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", { text: "Month" }), el("th", { class: "num", text: "Providers submitting" }),
      el("th", { text: "Submitted last month but not this month" }))),
    el("tbody", {}, subs.map((s) => el("tr", {},
      el("td", { text: fmtMonth(s.period) }),
      el("td", { class: "num", text: nf.format(s.providers_submitting) }),
      el("td", {}, s.new_non_submitters === null ? el("span", { class: "muted small", text: "Previous month not loaded" })
        : s.new_non_submitters.length === 0 ? status("good", "✓", "None")
        : el("div", {}, status("warning", "!", `${s.new_non_submitters.length} providers`),
          el("div", { class: "small", style: "margin-top:4px" },
            s.new_non_submitters.map((p) => el("div", {}, el("span", { class: "filename", text: `${p.code} ` }), p.name))))))))));
}

getJSON("data/validation.json").then((v) => {
  const out = [el("h2", { style: "margin-top:8px", text: "Reconciliation runs" })];
  if (v.runs.length) out.push(...[...v.runs].reverse().map(runCard));
  else out.push(el("p", { class: "muted", text: "No reconciliation runs recorded yet." }));
  out.push(el("h2", { text: "Submission changes" }),
    el("p", { class: "small muted", text: "Only detects providers that stopped submitting since the previous month. Long-running non-submitters need the ODS expected-provider list." }),
    submissions(v.submissions));
  content.replaceChildren(...out);
}).catch((e) => showError(content, e));
