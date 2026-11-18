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

const REASON = {
  merged_or_recoded: ["good", "→", "Merged or recoded"],
  closed: ["neutral", "·", "Closed (ODS)"],
  not_submitting: ["serious", "!", "Not submitted"],
};

function orgLine(code, name, extra) {
  return el("div", { style: "margin:2px 0" }, el("span", { class: "filename", text: `${code} ` }), name || "", extra || null);
}

function submissions(subs) {
  const rows = [...subs].reverse().map((s) => {
    const nn = s.new_non_submitters;
    const newCell = nn === null ? el("span", { class: "muted small", text: "Previous month not loaded" })
      : nn.length === 0 ? status("good", "✓", "None")
      : el("div", { class: "small" }, nn.map((p) => {
        const [kind, icon, label] = REASON[p.reason] || REASON.not_submitting;
        return orgLine(p.code, p.name, el("span", { style: "margin-left:8px" }, status(kind, icon,
          p.reason === "merged_or_recoded" ? `${label} → ${p.successor}` : p.reason === "closed" ? `${label} ${p.closed_on}` : label)));
      }));
    const pers = s.persistent_non_submitters || [];
    const persCell = pers.length === 0 ? el("span", { class: "muted small", text: "–" })
      : el("div", { class: "small" }, pers.map((p) => orgLine(p.code, p.name,
        el("span", { class: "muted", text: ` · last reported ${fmtMonth(p.last_reported)}` }))));
    return el("tr", {}, el("td", { text: fmtMonth(s.period) }),
      el("td", { class: "num", text: nf.format(s.providers_submitting) }), el("td", {}, newCell), el("td", {}, persCell));
  });
  return el("div", { class: "table-wrap card", style: "padding:0" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", { text: "Month" }), el("th", { class: "num", text: "Providers" }),
      el("th", { text: "Submitted last month but not this month" }), el("th", { text: "NHS trusts still not submitting" }))),
    el("tbody", {}, rows)));
}

function lineage(l) {
  if (!l || !l.snapshot) return [el("p", { class: "muted", text: "No ODS snapshot yet (st fetch-ods)." })];
  const out = [el("p", { class: "small muted", text: `ODS snapshot ${l.snapshot}. Applied links make a merged or recoded provider count as the same provider in like-for-like measures and submission checks. Published figures stay under the publisher's codes.` })];
  out.push(el("div", { class: "table-wrap card", style: "padding:0" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", { text: "From" }), el("th", { text: "To" }), el("th", { text: "Effective" }), el("th", { text: "Source" }))),
    el("tbody", {}, l.links.map((k) => el("tr", {},
      el("td", {}, orgLine(k.from, k.from_name)), el("td", {}, orgLine(k.to, k.to_name)),
      el("td", { text: k.effective ? fmtMonth(k.effective) : "–" }),
      el("td", {}, el("span", { class: "chip", text: k.source === "ods" ? "ODS successor" : "Curated" }),
        k.source === "curated" ? el("div", { class: "small muted", style: "max-width:46ch", text: k.evidence }) : null)))))));
  const pending = [...l.proposed.map((p) => ({ ...p, kind: "proposed" })),
    ...l.candidates.filter((c) => !c.applied && !l.proposed.some((p) => p.from === c.from && p.to === c.to))
      .map((c) => ({ from: c.from, from_name: c.from_name, to: c.to, to_name: c.to_name, kind: "candidate",
        evidence: `Same address (${c.address}); last reported ${fmtMonth(c.last_reported)}, new code from ${fmtMonth(c.first_reported)}${c.operator_change ? `; operator ${c.operator_change}` : ""}.` }))];
  out.push(el("h3", { style: "margin:20px 0 8px", text: "Awaiting review" }));
  if (!pending.length) out.push(status("good", "✓", "Nothing awaiting review"));
  else out.push(el("p", { class: "small muted", text: "Set status: confirmed in catalogue/organisation_lineage.yaml to apply a link." }),
    el("div", { class: "table-wrap card", style: "padding:0" }, el("table", {}, el("tbody", {}, pending.map((p) => el("tr", {},
      el("td", {}, status("warning", "?", p.kind === "proposed" ? "Proposed" : "Detected")),
      el("td", {}, orgLine(p.from, p.from_name), el("div", { class: "muted small", text: "→" }), orgLine(p.to, p.to_name)),
      el("td", { class: "small", style: "max-width:60ch", text: p.evidence })))))));
  return out;
}

function revisions(r) {
  const periods = (r && r.periods) || [];
  if (!periods.length) return [el("p", { class: "muted", text: "No processed data." })];
  const compared = periods.filter((p) => p.comparisons.length);
  const out = [];
  out.push(el("p", { class: "small muted", text: "Every archived version of a month is kept. Where a month has two or more versions, the changes between them are listed. A month whose earliest archived version is later than its expected first release only has a revision: the original release was never archived, so its changes cannot be measured." }));
  if (!compared.length) out.push(el("div", { class: "notice info" }, status("neutral", "i", "No comparisons yet"),
    el("span", { text: " No month has more than one archived version. Comparisons appear when a revised file is archived for a month whose earlier version is held." })));
  for (const p of compared) {
    for (const c of p.comparisons) {
      out.push(el("article", { class: "card", style: "margin-bottom:12px" },
        el("h3", { text: `${fmtMonth(p.period)}: ${c.old} → ${c.new}` }),
        el("p", { class: "small muted", style: "margin:4px 0 8px",
          text: `${nf.format(c.rows_changed)} rows changed, ${nf.format(c.rows_added)} added, ${nf.format(c.rows_removed)} removed of ${nf.format(c.rows_compared)}; ${c.providers_changed} providers with changed measures.` }),
        c.national_changes.length ? el("div", { class: "table-wrap" }, el("table", {},
          el("thead", {}, el("tr", {}, el("th", { text: "England measure" }), el("th", { class: "num", text: "Before" }), el("th", { class: "num", text: "After" }), el("th", { class: "num", text: "Change" }))),
          el("tbody", {}, c.national_changes.map((m) => el("tr", {}, el("td", { text: m.measure.replaceAll("_", " ") }),
            el("td", { class: "num", text: nf.format(m.old) }), el("td", { class: "num", text: nf.format(m.new) }),
            el("td", { class: "num", text: `${m.change > 0 ? "+" : ""}${nf.format(m.change)}` }))))))
          : status("good", "✓", "No change to England measures"),
        c.top_provider_changes.length ? el("details", { style: "margin-top:8px" }, el("summary", { class: "small", text: "Largest provider waiting-list changes" }),
          el("div", { class: "table-wrap" }, el("table", {}, el("tbody", {}, c.top_provider_changes.map((t) => el("tr", {},
            el("td", {}, orgLine(t.org_code, t.org_name)), el("td", { class: "num", text: nf.format(t.old ?? 0) }),
            el("td", { class: "num", text: nf.format(t.new ?? 0) }), el("td", { class: "num", text: `${t.change > 0 ? "+" : ""}${nf.format(t.change ?? 0)}` }))))))) : null));
    }
  }
  out.push(el("div", { class: "table-wrap card", style: "padding:0;margin-top:12px" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", { text: "Month" }), el("th", { text: "Archived versions" }), el("th", { text: "Expected first release" }), el("th", { text: "Status" }))),
    el("tbody", {}, [...periods].reverse().map((p) => el("tr", {},
      el("td", { text: fmtMonth(p.period) }), el("td", { class: "small", text: p.vintages.join(", ") }),
      el("td", { class: "small", text: p.expected_first_release }),
      el("td", {}, p.original_archived ? (p.comparisons.length ? status("good", "✓", `${p.comparisons.length} revision${p.comparisons.length > 1 ? "s" : ""} compared`) : status("good", "✓", "Original release archived"))
        : status("warning", "!", "Revision only: original not archived"))))))));
  return out;
}

getJSON("data/validation.json").then((v) => {
  const out = [el("h2", { style: "margin-top:8px", text: "Reconciliation runs" })];
  if (v.runs.length) out.push(...[...v.runs].reverse().map(runCard));
  else out.push(el("p", { class: "muted", text: "No reconciliation runs recorded yet." }));
  out.push(el("h2", { text: "Submissions" }),
    el("p", { class: "small muted", text: "Reasons use ODS successor records and curated lineage links. NHS trusts still not submitting: trusts (ODS role RO197) that reported in an earlier loaded month, are missing for at least two months, are not closed and are not carried by a submitting successor." }),
    submissions(v.submissions),
    el("h2", { text: "Organisation lineage" }), ...lineage(v.lineage),
    el("h2", { text: "Revisions" }), ...revisions(v.revisions));
  content.replaceChildren(...out);
}).catch((e) => showError(content, e));
