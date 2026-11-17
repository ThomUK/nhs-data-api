// Shared helpers. All data-derived text goes in via textContent (never innerHTML).

export async function getJSON(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function parseDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
export const fmtMonth = (iso) => { const d = parseDate(iso); return `${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const fmtMonthShort = (iso) => { const d = parseDate(iso); return `${MONTHS[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}`; };
export const fmtDay = (iso) => { const d = parseDate(iso); return `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const daysBetween = (a, b) => Math.round((parseDate(b) - parseDate(a)) / 86400000);

const nf = new Intl.NumberFormat("en-GB");
export function fmtValue(v, unit) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (unit === "percent") return `${v.toFixed(1)}%`;
  if (unit === "weeks") return `${v.toFixed(1)} wks`;
  return nf.format(v);
}
export function fmtSigned(v, unit) {
  if (v === null || v === undefined) return "–";
  const s = v > 0 ? "+" : v < 0 ? "−" : "±";
  const a = Math.abs(v);
  if (unit === "percent") return `${s}${a.toFixed(1)} pts`;
  if (unit === "weeks") return `${s}${a.toFixed(1)} wks`;
  return `${s}${nf.format(a)}`;
}

export function status(kind, icon, label) {
  return el("span", { class: `status ${kind}` }, el("span", { class: "dot", "aria-hidden": "true", text: icon }), label);
}

export function renderChrome(active) {
  const pages = [["index.html", "Calendar"], ["timeseries.html", "Time series"], ["validation.html", "Validation"]];
  const bar = el("header", { class: "topbar" },
    el("div", { class: "brand" }, "NHS Data API", el("small", { text: "admin" })),
    el("nav", { "aria-label": "Admin pages" },
      pages.map(([href, label]) => el("a", { href, "aria-current": href === active ? "page" : null, text: label }))),
    el("div", { class: "build", id: "build-info" }));
  document.body.prepend(bar);
  getJSON("data/build.json").then((b) => {
    document.getElementById("build-info").textContent =
      `Data built ${b.built_at.replace("T", " ").slice(0, 16)} UTC · v${b.version}`;
  }).catch(() => {});
}

export function showError(container, err) {
  container.replaceChildren(el("div", { class: "notice" },
    status("critical", "!", "Could not load data"), el("span", { text: String(err.message || err) })));
}
