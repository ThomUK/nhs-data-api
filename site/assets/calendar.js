import { getJSON, el, fmtDay, fmtMonth, daysBetween, status, renderChrome, showError } from "./common.js";

renderChrome("index.html");
const content = document.getElementById("content");
const fDataset = document.getElementById("f-dataset");
const fPast = document.getElementById("f-past");
const fAhead = document.getElementById("f-ahead");
const fPending = document.getElementById("f-pending");
let data;

const ROLE = { ingest: "Ingest", validate: "Validate", reference: "Reference" };

function fileStatus(file, pub, today) {
  if (file.received.length) return status("good", "✓", "Received");
  if (pub.publication_date > today) return status("neutral", "·", "Not yet published");
  return file.required ? status("serious", "!", "Outstanding") : status("warning", "–", "Not collected");
}

function pubStatus(pub, today) {
  const required = pub.files.filter((f) => f.required);
  if (!pub.files.length) return status("neutral", "·", "Not yet onboarded");
  if (pub.publication_date > today) return status("neutral", "·", "Upcoming");
  const missing = required.filter((f) => !f.received.length).length;
  return missing ? status("serious", "!", `${missing} required file${missing > 1 ? "s" : ""} outstanding`)
    : status("good", "✓", "All required files received");
}

function datasetBlock(pub, today) {
  const head = el("div", { style: "display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline" },
    el("div", {},
      el("h3", { text: pub.title }),
      el("div", { class: "muted small" }, `Data for ${fmtMonth(pub.data_period)} · `,
        el("a", { href: pub.source_page, target: "_blank", rel: "noopener", text: "source page" }))),
    pubStatus(pub, today));
  if (!pub.files.length) return el("div", { class: "pending-row" }, head);
  const rows = pub.files.map((f) => el("tr", {},
    el("td", {}, el("div", { text: f.label }), el("div", { class: "small muted", text: f.purpose })),
    el("td", {}, el("span", { class: "chip", text: ROLE[f.role] }), f.required ? null : el("div", { class: "small muted", text: "optional" })),
    el("td", {}, fileStatus(f, pub, today),
      f.received.map((name) => el("div", { class: "filename", text: name })))));
  const extra = pub.unmatched_files.length
    ? el("p", { class: "small", style: "margin:8px 0 0" }, status("neutral", "i", "Other files in this release (e.g. revised earlier months): "),
      pub.unmatched_files.map((n) => el("span", { class: "filename", text: ` ${n}` })))
    : null;
  return el("div", {}, head,
    el("div", { class: "table-wrap", style: "margin-top:8px" },
      el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "File" }), el("th", { text: "Use" }), el("th", { text: "Status" }))),
        el("tbody", {}, rows))), extra);
}

function dateCard(date, pubs, today) {
  const days = daysBetween(today, date);
  const when = days === 0 ? "today" : days > 0 ? `in ${days} days` : `${-days} days ago`;
  const confirmed = pubs.some((p) => p.date_status === "confirmed");
  const unconfirmedRule = pubs.filter((p) => p.rule_status === "unconfirmed").map((p) => p.title);
  const notes = pubs.map((p) => p.date_note).filter(Boolean);
  const onboarded = pubs.filter((p) => p.files.length);
  const pending = pubs.filter((p) => !p.files.length);
  return el("article", { class: "card", style: "margin-bottom:12px" },
    el("div", { style: "display:flex;gap:12px;flex-wrap:wrap;align-items:baseline;margin-bottom:8px" },
      el("strong", { text: fmtDay(date) }), el("span", { class: "muted small", text: when }),
      confirmed ? status("good", "✓", "Date confirmed") : status("neutral", "·", "Expected (from rule)")),
    notes.length ? el("p", { class: "small muted", style: "margin:-4px 0 8px", text: notes.join(" ") }) : null,
    ...onboarded.map((p) => datasetBlock(p, today)),
    pending.length ? el("div", { class: "pending", style: "margin-top:12px;padding-top:10px;border-top:1px solid var(--grid)" },
      el("div", { class: "small muted", text: "Also expected (not yet onboarded):" }),
      el("ul", { class: "small", style: "margin:4px 0 0;padding-left:18px" },
        pending.map((p) => el("li", {}, `${p.title}, data for ${fmtMonth(p.data_period)}`,
          unconfirmedRule.includes(p.title) ? el("span", { class: "muted", text: " (schedule unconfirmed)" }) : null)))) : null);
}

function addMonthsIso(iso, n) {
  const [y, m] = iso.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return d.toISOString().slice(0, 10);
}

function render() {
  const today = data.today;
  const until = addMonthsIso(today, Number(fAhead.value) + 1);
  const pubs = data.publications.filter((p) =>
    (!fDataset.value || p.dataset === fDataset.value)
    && (fPending.checked || p.files.length || fDataset.value === p.dataset)
    && (fPast.checked || p.publication_date >= today)
    && p.publication_date < until);
  const next = data.publications.filter((p) => p.publication_date >= today && p.files.length)
    .filter((p) => !fDataset.value || p.dataset === fDataset.value);
  const out = [];
  if (next.length) {
    const date = next[0].publication_date;
    const same = next.filter((p) => p.publication_date === date);
    const files = same.flatMap((p) => p.files.filter((f) => f.required).map((f) => f.label));
    out.push(el("section", { class: "card hero", style: "margin-bottom:24px", "aria-label": "Next publication" },
      el("div", { class: "muted small", text: "Next publication with files to collect" }),
      el("div", { class: "big", text: fmtDay(date) }),
      el("div", { text: `${same.map((p) => `${p.title}, ${fmtMonth(p.data_period)} data`).join("; ")} · in ${daysBetween(today, date)} days` }),
      el("div", { class: "small muted", text: `Required: ${files.join("; ")}` })));
  }
  const byDate = new Map();
  for (const p of pubs) byDate.set(p.publication_date, [...(byDate.get(p.publication_date) || []), p]);
  let month = "";
  for (const [date, group] of byDate) {
    const m = date.slice(0, 7);
    if (m !== month) { month = m; out.push(el("h2", { text: fmtMonth(`${m}-01`) })); }
    out.push(dateCard(date, group, today));
  }
  if (!pubs.length) out.push(el("p", { class: "muted", text: "No publications match these filters." }));
  if (data.unscheduled.length) {
    out.push(el("h2", { text: "Datasets without a schedule yet" }));
    for (const u of data.unscheduled) {
      out.push(el("article", { class: "card", style: "margin-bottom:12px" }, el("h3", { text: u.title }),
        el("p", { class: "small muted", style: "margin:4px 0 0" }, u.rule_note, " ",
          el("a", { href: u.source_page, target: "_blank", rel: "noopener", text: "Source page" }))));
    }
  }
  content.replaceChildren(...out);
}

function downloadIcs() {
  const today = data.today;
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//nhs-data-api//admin//EN", "CALSCALE:GREGORIAN"];
  const esc = (s) => s.replace(/[\\,;]/g, (c) => `\\${c}`).replace(/\n/g, "\\n");
  for (const p of data.publications.filter((p) => p.publication_date >= today)) {
    const d = p.publication_date.replaceAll("-", "");
    const files = p.files.map((f) => `${f.required ? "[required] " : ""}${f.label}`).join("\n");
    lines.push("BEGIN:VEVENT", `UID:${p.dataset}-${d}@nhs-data-api`, `DTSTAMP:${today.replaceAll("-", "")}T000000Z`,
      `DTSTART;VALUE=DATE:${d}`, `SUMMARY:${esc(`${p.title}: ${fmtMonth(p.data_period)} data`)}`,
      `DESCRIPTION:${esc(`${p.date_status === "confirmed" ? "Confirmed" : "Expected"} publication.\n${files}\n${p.source_page}`)}`,
      "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  const a = el("a", { href: URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/calendar" })),
    download: "nhs-publications.ics" });
  a.click();
  URL.revokeObjectURL(a.href);
}

getJSON("data/calendar.json").then((d) => {
  data = d;
  const seen = new Map(d.publications.map((p) => [p.dataset, p.title]));
  for (const [id, title] of seen) fDataset.append(el("option", { value: id, text: title }));
  fDataset.addEventListener("change", render);
  fPast.addEventListener("change", render);
  fAhead.addEventListener("change", render);
  fPending.addEventListener("change", render);
  document.getElementById("ics").addEventListener("click", downloadIcs);
  render();
}).catch((e) => showError(content, e));
