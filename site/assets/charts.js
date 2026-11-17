// Minimal SVG charts: single-series line chart with crosshair tooltip, and sparkline.
import { el, fmtValue, fmtMonthShort, fmtMonth } from "./common.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

// ---- Anomaly rules (documented on the page) ----
// gap:    value missing while earlier and later months have values
// jump:   month-on-month change above threshold (relative for counts, points for %/weeks)
// robust: with >= 6 earlier monthly changes, this month's change is more than 3.5 scaled
//         MADs from the median change of the previous 12 months
// Measures that are themselves month-on-month differences (requires_previous_month) cross
// zero, so a percentage "jump" is meaningless for them: only the unusual-change rule applies.
export function detectAnomalies(values, unit, threshold, { isChange = false } = {}) {
  const flags = values.map(() => []);
  const firstIdx = values.findIndex((v) => v !== null);
  let lastIdx = -1;
  values.forEach((v, i) => { if (v !== null) lastIdx = i; });
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v === null) {
      if (i > firstIdx && i < lastIdx && firstIdx >= 0) flags[i].push("Missing month");
      else if (i === values.length - 1 && firstIdx >= 0) flags[i].push("No data this month");
      continue;
    }
    const prev = i > 0 ? values[i - 1] : null;
    if (prev !== null && prev !== undefined && !isChange) {
      if (unit === "percent" || unit === "weeks") {
        if (Math.abs(v - prev) >= threshold.abs) flags[i].push(`Change of ${(v - prev).toFixed(1)} ${unit === "percent" ? "pts" : "wks"}`);
      } else if (Math.abs(prev) >= 20) {
        const rel = (v - prev) / Math.abs(prev);
        if (Math.abs(rel) >= threshold.rel / 100) flags[i].push(`Change of ${(rel * 100).toFixed(0)}% on previous month`);
      }
    }
    // Robust outlier on month-on-month changes, so a genuine step change flags once rather
    // than every month after it.
    if (prev !== null && prev !== undefined) {
      const diffs = [];
      for (let j = Math.max(1, i - 12); j < i; j++) {
        if (values[j] !== null && values[j - 1] !== null) diffs.push(values[j] - values[j - 1]);
      }
      if (diffs.length >= 6) {
        const med = median(diffs);
        const mad = median(diffs.map((x) => Math.abs(x - med))) * 1.4826;
        if (mad > 0 && Math.abs(v - prev - med) / mad > 3.5) flags[i].push("Unusual change against the previous 12 months");
      }
    }
  }
  return flags;
}
function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function niceTicks(min, max, count = 4) {
  if (min === max) { const pad = Math.abs(min) * 0.05 || 1; min -= pad; max += pad; }
  const step0 = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(+t.toPrecision(12));
  return { lo, hi, ticks, step };
}
// Tick labels with just enough decimals to tell adjacent ticks apart.
function tickFormatter(step, maxAbs, unit) {
  const decimalsFor = (s) => {
    let d = 0;
    while (d < 4 && Math.abs(Math.round(s * 10 ** d) - s * 10 ** d) > 1e-6) d++;
    return d;
  };
  if (unit === "percent" || unit === "weeks") {
    const d = decimalsFor(step);
    return (v) => `${v.toFixed(d)}${unit === "percent" ? "%" : ""}`;
  }
  const [div, suffix] = maxAbs >= 1e6 ? [1e6, "m"] : maxAbs >= 1e4 ? [1e3, "k"] : [1, ""];
  const d = decimalsFor(step / div);
  return (v) => `${(v / div).toFixed(d)}${suffix}`;
}

export function lineChart({ periods, values, unit, flags, label, height = 150 }) {
  const wrap = el("div", { class: "chart" });
  const tooltip = el("div", { class: "tooltip", hidden: true });
  const width = 320, m = { t: 8, r: 10, b: 22, l: 44 };
  const pts = values.map((v, i) => ({ v, i })).filter((p) => p.v !== null);
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", tabindex: "0",
    "aria-label": `${label}: line chart over ${periods.length} months. Use arrow keys to read values.` });
  wrap.append(root, tooltip);
  if (!pts.length) {
    const t = svg("text", { x: width / 2, y: height / 2, "text-anchor": "middle", class: "axis" });
    t.textContent = "No data";
    root.append(t);
    return wrap;
  }
  const vs = pts.map((p) => p.v);
  const { lo, hi, ticks, step } = niceTicks(Math.min(...vs), Math.max(...vs));
  const fmtTick = tickFormatter(step, Math.max(Math.abs(lo), Math.abs(hi)), unit);
  const iw = width - m.l - m.r, ih = height - m.t - m.b;
  const x = (i) => m.l + (periods.length === 1 ? iw / 2 : (i / (periods.length - 1)) * iw);
  const y = (v) => m.t + ih - ((v - lo) / (hi - lo || 1)) * ih;

  const axis = svg("g", { class: "axis" });
  for (const t of ticks) {
    axis.append(svg("line", { class: t === ticks[0] ? "baseline" : "gridline", x1: m.l, x2: width - m.r, y1: y(t), y2: y(t) }));
    const lab = svg("text", { x: m.l - 6, y: y(t) + 4, "text-anchor": "end" });
    lab.textContent = fmtTick(t);
    axis.append(lab);
  }
  const xLabels = periods.length <= 2 ? periods.map((_, i) => i)
    : [0, Math.round((periods.length - 1) / 2), periods.length - 1];
  for (const i of new Set(xLabels)) {
    const lab = svg("text", { x: x(i), y: height - 6, "text-anchor": periods.length === 1 ? "middle" : i === 0 ? "start" : i === periods.length - 1 ? "end" : "middle" });
    lab.textContent = fmtMonthShort(periods[i]);
    axis.append(lab);
  }
  root.append(axis);

  // Line, broken at gaps
  let d = "";
  values.forEach((v, i) => {
    if (v === null) return;
    d += `${i > 0 && values[i - 1] !== null && d ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  root.append(svg("path", { class: "series", d }));

  // Markers: all points when few, otherwise latest + flagged
  const showAll = pts.length <= 24;
  pts.forEach(({ v, i }) => {
    const flagged = flags && flags[i].length;
    if (showAll || flagged || i === pts[pts.length - 1].i) {
      root.append(svg("circle", { class: `marker${flagged ? " flag" : ""}`, cx: x(i), cy: y(v), r: flagged ? 5 : 4 }));
    }
  });
  // Flag markers for missing months sit on the baseline
  if (flags) values.forEach((v, i) => {
    if (v === null && flags[i].length) root.append(svg("circle", { class: "marker flag", cx: x(i), cy: m.t + ih, r: 5 }));
  });

  const cross = svg("line", { class: "crosshair", y1: m.t, y2: m.t + ih, visibility: "hidden" });
  root.append(cross);
  const hit = svg("rect", { x: m.l - 10, y: 0, width: iw + 20, height, fill: "transparent" });
  root.append(hit);

  let current = null;
  const show = (i) => {
    current = i;
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    tooltip.replaceChildren(
      el("strong", { text: fmtValue(values[i], unit) }),
      el("span", { class: "muted", text: fmtMonth(periods[i]) }),
      ...(flags ? flags[i].map((f) => el("div", { class: "flag-text", text: `⚠ ${f}` })) : []));
    tooltip.hidden = false;
    const box = root.getBoundingClientRect();
    const px = (x(i) / width) * box.width;
    tooltip.style.left = `${Math.min(Math.max(px - 60, 0), box.width - 130)}px`;
    tooltip.style.top = `${-8}px`;
    tooltip.style.transform = "translateY(-100%)";
  };
  const hide = () => { cross.setAttribute("visibility", "hidden"); tooltip.hidden = true; current = null; };
  const nearest = (evt) => {
    const box = root.getBoundingClientRect();
    const sx = ((evt.clientX - box.left) / box.width) * width;
    if (periods.length === 1) return 0;
    return Math.max(0, Math.min(periods.length - 1, Math.round(((sx - m.l) / iw) * (periods.length - 1))));
  };
  hit.addEventListener("pointermove", (e) => show(nearest(e)));
  hit.addEventListener("pointerleave", hide);
  root.addEventListener("blur", hide);
  root.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    let i = current ?? periods.length - 1;
    if (e.key === "ArrowLeft") i = Math.max(0, i - 1);
    if (e.key === "ArrowRight") i = Math.min(periods.length - 1, i + 1);
    if (e.key === "Home") i = 0;
    if (e.key === "End") i = periods.length - 1;
    show(i);
  });
  return wrap;
}

export function tableView(periods, values, unit, flags) {
  return el("details", { class: "table-view" }, el("summary", { text: "Table" }),
    el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "Month" }), el("th", { class: "num", text: "Value" }), el("th", { text: "Flags" }))),
      el("tbody", {}, periods.map((p, i) => el("tr", {},
        el("td", { text: fmtMonth(p) }), el("td", { class: "num", text: fmtValue(values[i], unit) }),
        el("td", { text: flags ? flags[i].join("; ") : "" }))))));
}

export function sparkline(values, flags, { width = 140, height = 30 } = {}) {
  const root = svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" });
  const pts = values.map((v, i) => ({ v, i })).filter((p) => p.v !== null);
  if (!pts.length) return root;
  const vs = pts.map((p) => p.v);
  const lo = Math.min(...vs), hi = Math.max(...vs);
  const pad = 5;
  const x = (i) => pad + (values.length === 1 ? (width - 2 * pad) / 2 : (i / (values.length - 1)) * (width - 2 * pad));
  const y = (v) => height - pad - ((v - lo) / (hi - lo || 1)) * (height - 2 * pad);
  let d = "";
  values.forEach((v, i) => { if (v !== null) d += `${i > 0 && values[i - 1] !== null && d ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; });
  root.append(svg("path", { class: "series", d }));
  pts.forEach(({ v, i }) => {
    const flagged = flags && flags[i].length;
    if (flagged || i === pts[pts.length - 1].i || pts.length <= 2) {
      root.append(svg("circle", { class: `marker${flagged ? " flag" : ""}`, cx: x(i), cy: y(v), r: flagged ? 4 : 3 }));
    }
  });
  return root;
}
