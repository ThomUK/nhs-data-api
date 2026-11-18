"""Generate the public API documentation subsite (site/api/).

Everything is generated: endpoints from the API's OpenAPI spec, datasets and measures from
the catalogue, and example responses by calling the API against the processed data at build
time. The subsite is self-contained (no links into the admin pages) so it can be hosted
separately once the rest of the project is private.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from . import __version__
from .catalogue import Dataset, load_catalogue
from .paths import CATALOGUE_DIR, PROCESSED_DIR, REPO_ROOT

OUT = REPO_ROOT / "site" / "api"
PRODUCT = "secondthursday"
BASE = "https://<api-host>"  # not yet deployed
DESCRIPTION = ("Documentation for an API serving public NHS England statistics with "
               "definitions, sources and caveats.")
# Quick start on the overview page: (introduction, path, query). Responses are real, taken
# from the processed data at build time.
QUICKSTART = [
    ("England's waiting list, % within 18 weeks and median wait since July 2026:",
     "/v1/rtt/metrics", {"view": "national",
                         "measures": "waiting_list_total,pct_within_18_weeks,median_wait_weeks",
                         "period_from": "2026-07-01"}),
    ("One trust (Guy's and St Thomas', ODS code <code>RJ1</code>), latest month, all measures:",
     "/v1/rtt/metrics", {"view": "provider", "org": "RJ1"}),
    ("Find an NHS trust's code:",
     "/v1/organisations", {"q": "bristol", "sector": "nhs_trust"}),
]


def _url(path: str, params: dict) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{BASE}{path}" + (f"?{query}" if query else "")

EXAMPLES = [
    ("/v1/rtt/metrics", {"view": "national", "measures":
     "waiting_list_total,pct_within_18_weeks,median_wait_weeks", "period_from": "2026-07-01"}),
    ("/v1/rtt/metrics", {"view": "provider", "org": "RJ1",
                         "measures": "waiting_list_total,p92_wait_weeks,waiting_over_52_weeks"}),
    ("/v1/rtt/metrics", {"view": "population_icb", "org": "QKK",
                         "measures": "waiting_list_total,waiting_list_change_mom_like_for_like"}),
    ("/v1/rtt/submissions", {}),
    ("/v1/organisations", {"q": "bristol", "sector": "nhs_trust"}),
    ("/v1/organisations/RA7", {}),
    ("/v1/datasets", {}),
]

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--surface-2:#f3f2ee;--ink:#0b0b0b;
--ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);
--accent:#2a78d6;--code:#f3f2ee;--warn:#fab219;--good:#0ca30c}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--surface-2:#242422;--ink:#f0efec;--ink-2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--accent:#3987e5;--code:#242422}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#242422;
--ink:#f0efec;--ink-2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);
--accent:#3987e5;--code:#242422}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);
font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
header.top{display:flex;gap:24px;align-items:center;flex-wrap:wrap;padding:12px 24px;
background:var(--surface);border-bottom:1px solid var(--border)}
.brand{font-weight:650}.brand small{color:var(--muted);font-weight:400;margin-left:6px}
nav{display:flex;gap:4px;flex-wrap:wrap}nav a{color:var(--ink-2);text-decoration:none;
padding:6px 10px;border-radius:6px}nav a:hover{background:var(--surface-2)}
nav a[aria-current=page]{background:var(--surface-2);color:var(--ink);font-weight:600}
main{max-width:960px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:30px;line-height:1.2;margin:0 0 8px;letter-spacing:-.01em}
h2{font-size:21px;margin:40px 0 12px;padding-top:8px;border-top:1px solid var(--grid)}
h3{font-size:17px;margin:28px 0 8px}.lede{font-size:18px;color:var(--ink-2);max-width:65ch}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13.5px}
code{background:var(--code);padding:1px 5px;border-radius:4px}
pre{background:var(--code);padding:14px 16px;border-radius:8px;overflow-x:auto;line-height:1.5}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;font-size:14.5px;margin:8px 0 16px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--grid);vertical-align:top}
th{font-size:13px;color:var(--ink-2)}.wrap{overflow-x:auto}
.method{display:inline-block;font:600 12px ui-monospace,monospace;padding:2px 8px;
border-radius:4px;background:var(--accent);color:#fff;margin-right:8px}
.endpoint{background:var(--surface);border:1px solid var(--border);border-radius:10px;
padding:4px 20px 12px;margin:20px 0}
.chip{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;
background:var(--surface-2);color:var(--ink-2);white-space:nowrap}
.chip.draft{border:1px solid var(--warn)}.chip.experimental{border:1px dashed var(--warn)}
.note{border-left:3px solid var(--accent);background:var(--surface);padding:10px 14px;
border-radius:6px;color:var(--ink-2);margin:16px 0}
.cards{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.card h3{margin:0 0 4px}.muted{color:var(--muted)}.small{font-size:14px}
details summary{cursor:pointer;color:var(--ink-2);margin:4px 0}
main.wide{max-width:1240px}
.split{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:36px;
align-items:start;padding:28px 0;border-top:1px solid var(--grid)}
.split>.code{position:sticky;top:16px}
.split>.code pre{max-height:calc(100vh - 180px);overflow:auto;margin:0 0 12px}
.split h2{border:0;margin:0 0 8px;padding:0}
.label{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;
letter-spacing:.05em;margin:0 0 6px}
.fields{margin:8px 0 16px}.field{border-top:1px solid var(--grid);padding:10px 0}
.field:last-child{border-bottom:1px solid var(--grid)}
.fname{font:600 14px ui-monospace,SFMono-Regular,Menlo,monospace}
.ftype{color:var(--muted);font-size:13px;margin-left:8px}
.field p{margin:4px 0 0;font-size:14.5px}.field .muted{font-size:13.5px}
.returns{font-size:14.5px;background:var(--surface);border:1px solid var(--border);
border-radius:8px;padding:8px 12px;margin:12px 0}
.status-code{font:600 13px ui-monospace,monospace;padding:2px 8px;border-radius:4px;
background:var(--surface-2);margin-right:8px}
.split>div{min-width:0}
@media (max-width:960px){.split{grid-template-columns:minmax(0,1fr);gap:12px}
.split>.code{position:static}}
pre.response{max-height:26em;overflow:auto}
details.response-toggle{margin:-4px 0 20px}
details.response-toggle summary{padding:4px 0}
details.response-toggle[open] summary{margin-bottom:8px}
footer{color:var(--muted);font-size:13px;max-width:960px;margin:0 auto;padding:0 24px 40px}
@media (max-width:640px){main{padding:20px 16px 48px}header.top{padding:10px 16px}
h1{font-size:25px}}
"""


def _page(title: str, active: str, body: str, depth: int = 0, wide: bool = False) -> str:
    root = "../" * depth
    links = [("index.html", "Overview"), ("reference.html", "Endpoints"),
             ("objects.html", "Objects"), ("errors.html", "Errors"),
             ("datasets.html", "Datasets & measures"), ("llms.txt", "llms.txt")]
    nav = "".join(
        f'<a href="{root}{h}"{" aria-current=page" if h == active else ""}>{escape(t)}</a>'
        for h, t in links)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{DESCRIPTION}">
<link rel="stylesheet" href="{root}assets/docs.css"></head><body>
<header class="top"><div class="brand">{PRODUCT}<small>docs</small></div>
<nav aria-label="Documentation">{nav}</nav></header>
<main{' class=wide' if wide else ''}>{body}</main>
<footer>Generated {datetime.now(UTC):%d %B %Y} · v{__version__} · Contains public sector
information licensed under the Open Government Licence v3.0.</footer>
</body></html>"""


def _code(text: str, lang: str = "", extra: str = "") -> str:
    cls = f' class="{extra}"' if extra else ""
    return f'<pre{cls}><code class="{lang}">{escape(text)}</code></pre>'


def _json(obj) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


def _trim(obj, max_items: int = 3, key: str = ""):
    """Shorten example responses: lists to a few items, and the repetitive meta caveats and
    measure definitions to one entry each, recursively."""
    limit = 1 if key in ("caveats", "measures") else max_items
    if isinstance(obj, list):
        items = [_trim(x, max_items) for x in obj[:limit]]
        if len(obj) > limit:
            items.append(f"… {len(obj) - limit} more")
        return items
    if isinstance(obj, dict):
        entries = list(obj.items())
        if key == "measures" and len(entries) > limit:
            kept = {k: _trim(v, max_items, k) for k, v in entries[:limit]}
            kept["…"] = f"{len(entries) - limit} more measure definitions"
            return kept
        return {k: _trim(v, max_items, k) for k, v in entries}
    if isinstance(obj, str) and len(obj) > 160:
        return obj[:157] + "…"
    return obj


def _key(path: str, params: dict) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{path}?{query}" if query else path


def call_api(processed_dir: Path, requests) -> dict[str, tuple[int, object]]:
    """Make GET requests in-process; returns {key: (status, json body)}."""
    from fastapi.testclient import TestClient

    from .api import app as app_module

    original = app_module.PROCESSED_DIR
    app_module.PROCESSED_DIR = processed_dir
    try:
        client = TestClient(app_module.app)
        out = {}
        for path, params in requests:
            resp = client.get(path, params=params)
            out[_key(path, params)] = (resp.status_code, resp.json())
        return out
    finally:
        app_module.PROCESSED_DIR = original


def load_api_objects(path: Path = CATALOGUE_DIR / "api_objects.yaml") -> dict:
    import yaml
    return yaml.safe_load(path.read_text())


def _pick(obj, pointer: str):
    for part in pointer.split(".") if pointer else []:
        if obj is None:
            return None
        if isinstance(obj, list):
            idx = int(part)
            obj = obj[idx] if -len(obj) <= idx < len(obj) else None
        else:
            obj = obj.get(part)
    return obj


def measure_fields(ds: Dataset) -> list[dict]:
    """Measure columns of the measure row, from the catalogue."""
    fields = []
    for m in ds.measures:
        if not m.computed:
            continue
        nullable = m.requires_previous_month or m.unit in ("percent", "weeks")
        desc = " ".join(m.definition.split())
        if m.requires_previous_month:
            desc += " Null when the previous month is not available."
        fields.append({"name": m.id, "type": "integer" if m.unit == "count" else "number",
                       "nullable": nullable, "description": desc, "status": m.status,
                       "unit": m.unit, "label": m.label})
    return fields


def _fields_html(fields: list[dict], root: str = "") -> str:
    items = []
    for f in fields:
        ftype = escape(f.get("type", ""))
        if f.get("link"):
            ftype = f"<a href='{root}objects.html#{f['link']}'>{ftype}</a>"
        chips = ""
        if f.get("nullable"):
            chips += " · nullable"
        if f.get("status") and f["status"] != "stable":
            chips += f" <span class='chip {f['status']}'>{f['status']}</span>"
        label = f"<strong>{escape(f['label'])}.</strong> " if f.get("label") else ""
        values = ""
        if f.get("values"):
            values = ("<div class=muted>One of: " + ", ".join(
                f"<code>{escape(str(v))}</code>" for v in f["values"]) + "</div>")
        extra = ""
        if f.get("default") not in (None, ""):
            extra += f" · default <code>{escape(str(f['default']))}</code>"
        if f.get("required"):
            extra += " · <strong>required</strong>"
        items.append(f"<div class=field id='field-{escape(f['name'])}'>"
                     f"<span class=fname>{escape(f['name'])}</span>"
                     f"<span class=ftype>{ftype}{chips}{extra}</span>"
                     f"<p>{label}{escape(f.get('description') or '')}</p>{values}</div>")
    return f"<div class=fields>{''.join(items)}</div>"


def example_responses(processed_dir: Path, examples=None) -> dict[str, dict]:
    """Call the API in-process against the processed data. Missing data -> no example."""
    from fastapi.testclient import TestClient

    from .api import app as app_module

    original = app_module.PROCESSED_DIR
    app_module.PROCESSED_DIR = processed_dir
    out = {}
    try:
        client = TestClient(app_module.app)
        for path, params in (EXAMPLES if examples is None else examples):
            resp = client.get(path, params=params)
            if resp.status_code == 200:
                query = "&".join(f"{k}={v}" for k, v in params.items())
                key = f"{path}?{query}" if query else path
                body = resp.json()
                if path == "/v1/rtt/submissions":
                    body["data"] = body["data"][-1:]
                out[key] = _trim(body)
    finally:
        app_module.PROCESSED_DIR = original
    return out


def _param_fields(params: list[dict]) -> list[dict]:
    fields = []
    for p in params:
        schema = p.get("schema", {})
        options = schema.get("anyOf", [schema])
        types = [o.get("type") for o in options if o.get("type") not in (None, "null")]
        enum = next((o.get("enum") for o in options if o.get("enum")), None)
        fields.append({"name": p["name"], "type": f"{', '.join(types)} · {p['in']}",
                       "required": p.get("required"), "default": schema.get("default"),
                       "values": enum,
                       "description": p.get("description") or schema.get("description") or ""})
    return fields


def _anchor(path: str) -> str:
    return path.strip("/").replace("/", "-").replace("{", "").replace("}", "")


def _returns(path: str, objects: list[dict]) -> str:
    hits = [o for o in objects if path in o.get("returned_by", [])]
    if not hits:
        return ""
    single = "{" in path

    def name(o: dict) -> str:
        noun = o["title"].removeprefix("The ").lower()
        article = "an" if noun[0] in "aeiou" else "a"
        text = f"{article} {noun} object" if single else f"{noun} objects"
        return f"<a href='objects.html#{o['id']}'>{escape(text)}</a>"

    what = " or ".join(name(o) for o in hits)
    shape = f"<code>data</code>: {what}" if single else f"a <code>data</code> list of {what}"
    return (f"<div class=returns><strong>Returns</strong> {shape}, and a "
            f"<a href='objects.html#meta'>meta object</a>.</div>")


def reference_page(spec: dict, examples: dict[str, dict], objects: list[dict]) -> str:
    anchor_for = _anchor
    ops = [(p, o["get"]) for p, o in spec["paths"].items() if "get" in o and p != "/health"]
    toc = "".join(f"<li><a href='#{anchor_for(p)}'><code>{escape(p)}</code></a>: "
                  f"{escape((op.get('description') or '').split(chr(10))[0])}</li>"
                  for p, op in ops)
    body = [f"<h1>Endpoints</h1><p class=lede>All endpoints are read-only <code>GET</code> "
            f"requests returning JSON: a <code>data</code> list or object and a "
            f"<a href=objects.html#meta><code>meta</code> object</a>. Errors are described on "
            f"the <a href=errors.html>Errors</a> page. The machine-readable spec is "
            f"<a href=openapi.json>openapi.json</a>.</p><ul class=small>{toc}</ul>"]
    for path, op in ops:
        desc = escape(" ".join((op.get("description") or "").split()))
        left = [f"<h2><span class=method>GET</span><code>{escape(path)}</code></h2>",
                f"<p>{desc}</p>", _returns(path, objects)]
        if op.get("parameters"):
            left.append("<div class=label>Parameters</div>"
                        + _fields_html(_param_fields(op["parameters"])))
        right = []
        for key, response in examples.items():
            base = key.split("?")[0]
            if base == path or ("{" in path and base.startswith(path.split("{")[0])
                                and base.count("/") == path.count("/")):
                query = key.split("?", 1)[1] if "?" in key else ""
                url = f"{BASE}{base}" + (f"?{query}" if query else "")
                right.append("<div class=label>Request</div>" + _code(f'curl "{url}"', "shell")
                             + "<div class=label>Response</div>" + _code(_json(response), "json"))
        if not right:
            right.append("<div class=label>Request</div>"
                         + _code(f'curl "{BASE}{path}"', "shell"))
        body.append(f"<section class=split id='{anchor_for(path)}'><div>{''.join(left)}</div>"
                    f"<div class=code>{''.join(right)}</div></section>")
    return _page(f"Endpoints · {PRODUCT}", "reference.html", "".join(body), wide=True)


def objects_page(spec: dict, cat: dict[str, Dataset], responses: dict) -> str:
    objs = spec["objects"]
    toc = "".join(f"<li><a href='#{o['id']}'>{escape(o['title'])}</a></li>" for o in objs)
    body = ["<h1>Objects</h1><p class=lede>The shapes the API returns. Each field lists its "
            "type and whether it can be null. Examples are real responses (long text shortened)."
            f"</p><ul class=small>{toc}</ul>"]
    for o in objs:
        fields = list(o.get("fields", []))
        if o.get("measures_from"):
            fields += measure_fields(cat[o["measures_from"]])
        returned = ", ".join(
            f"<a href='reference.html#{_anchor(r)}'><code>{escape(r)}</code></a>"
            if r.startswith("/") else f"<code>{escape(r)}</code>" for r in o["returned_by"])
        left = (f"<h2>{escape(o['title'])}</h2><p>{escape(' '.join(o['summary'].split()))}</p>"
                f"<p class=small>Returned by: {returned}</p>"
                f"<div class=label>Fields</div>{_fields_html(fields)}")
        ex = o.get("example") or {}
        status, raw = responses.get(_key(ex.get("path", ""), ex.get("params") or {}), (0, None))
        sample = _pick(raw, ex.get("pick", "")) if status == 200 else None
        right = ("<div class=label>Example</div>" + _code(_json(_trim(sample)), "json")
                 if sample is not None
                 else "<p class='small muted'>No example in the current data.</p>")
        body.append(f"<section class=split id='{o['id']}'><div>{left}</div>"
                    f"<div class=code>{right}</div></section>")
    return _page(f"Objects · {PRODUCT}", "objects.html", "".join(body), wide=True)


def errors_page(spec: dict, responses: dict) -> str:
    rows = "".join(f"<tr><td><span class=status-code>{e['status']}</span></td>"
                   f"<td><a href='#e{e['status']}'>{escape(e['title'])}</a></td></tr>"
                   for e in spec["errors"])
    body = ["<h1>Errors</h1><p class=lede>Errors use standard HTTP status codes and a JSON body "
            "with a <code>detail</code> field: a message, or for invalid parameters a list of "
            "problems. Error responses are never cached (<code>Cache-Control: no-store</code>). "
            "A missing row is not an error: a provider that did not submit has no row, never a "
            "zero.</p>",
            "<div class=split style='border:0;padding-top:8px'><div>"
            "<div class=label>Status codes</div><div class=wrap><table><tbody>"
            "<tr><td><span class=status-code>200</span></td><td>Success</td></tr>"
            f"{rows}</tbody></table></div></div><div class=code>"
            "<div class=label>Error body</div>"
            + _code('{\n  "detail": "RJX is not an organisation in the statistics"\n}', "json")
            + "</div></div>"]
    for e in spec["errors"]:
        left = (f"<h2><span class=status-code>{e['status']}</span>{escape(e['title'])}</h2>"
                f"<p>{escape(' '.join(e['when'].split()))}</p>"
                f"<p><strong>What to do:</strong> {escape(e['action'])}</p>")
        right = []
        for ex in e.get("examples", []):
            key = _key(ex["path"], ex.get("params") or {})
            status, payload = responses.get(key, (0, None))
            if status == e["status"]:
                right.append("<div class=label>Request</div>"
                             + _code(f'curl "{_url(ex["path"], ex.get("params") or {})}"', "shell")
                             + f"<div class=label>Response · {status}</div>"
                             + _code(_json(payload), "json"))
        if not right:
            right.append("<p class='small muted'>No live example.</p>")
        body.append(f"<section class=split id='e{e['status']}'><div>{left}</div>"
                    f"<div class=code>{''.join(right)}</div></section>")
    return _page(f"Errors · {PRODUCT}", "errors.html", "".join(body), wide=True)


def _measures_table(ds: Dataset) -> str:
    rows = []
    for m in ds.measures:
        status = "" if m.status == "stable" else f" <span class='chip {m.status}'>{m.status}</span>"
        extra = []
        if m.standard:
            extra.append(f"<br><span class=muted>Standard: {escape(m.standard)}</span>")
        if m.caveat:
            extra.append(f"<br><span class=muted>Caveat: {escape(m.caveat.strip())}</span>")
        if m.requires_previous_month:
            extra.append("<br><span class=muted>Needs the previous month.</span>")
        rows.append(f"<tr><td id='{m.id}'><code>{m.id}</code>{status}</td>"
                    f"<td><strong>{escape(m.label)}</strong><br>{escape(m.definition.strip())}"
                    f"{''.join(extra)}</td><td>{escape(m.unit)}</td></tr>")
    return ("<div class=wrap><table><thead><tr><th>Measure id</th><th>Definition</th>"
            "<th>Unit</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def available_periods(processed_dir: Path) -> dict[str, tuple]:
    """First and last month served per dataset, from the processed data."""
    import polars as pl

    path = processed_dir / "rtt_metrics" / "metrics.parquet"
    if not path.exists():
        return {}
    periods = pl.read_parquet(path, columns=["period"])["period"]
    return {"rtt": (periods.min(), periods.max())}


def dataset_page(ds: Dataset, available: tuple | None = None) -> str:
    b = [f"<h1>{escape(ds.title)}</h1>",
         f"<p class=lede>{escape(ds.summary.strip())}</p>",
         "<div class=wrap><table><tbody>",
         f"<tr><th>Dataset id</th><td><code>{ds.id}</code> "
         f"<span class='chip {ds.status}'>{ds.status}</span></td></tr>",
         f"<tr><th>Publisher</th><td>{escape(ds.publisher)} · "
         f"<a href='{ds.source_page}'>source page</a></td></tr>",
         f"<tr><th>Frequency</th><td>{ds.frequency}</td></tr>",
         f"<tr><th>Published coverage</th><td>{escape(ds.geography)}"
         f"{f', from {ds.coverage_start:%B %Y}' if ds.coverage_start else ''}</td></tr>",
         (f"<tr><th>Available in this API</th><td>{available[0]:%B %Y} to "
          f"{available[1]:%B %Y}</td></tr>" if available else ""),
         f"<tr><th>Licence</th><td><a href='{ds.licence.url}'>{escape(ds.licence.name)}</a>"
         f"<br><span class=muted>{escape(ds.attribution)}</span></td></tr>",
         "</tbody></table></div>"]
    if ds.views:
        b.append("<h2>Views</h2><p>The same rows can be grouped several ways. Choose with the "
                 "<code>view</code> parameter.</p><div class=wrap><table><tbody>")
        b += [f"<tr><td><code>{v.id}</code></td><td><strong>{escape(v.label)}</strong><br>"
              f"{escape(v.description.strip())}</td></tr>" for v in ds.views]
        b.append("</tbody></table></div>")
    if ds.measures:
        b.append("<h2>Measures</h2>" + _measures_table(ds))
    if ds.dimensions:
        b.append("<h2>Dimensions</h2>")
        for d in ds.dimensions:
            b.append(f"<h3><code>{d.id}</code> · {escape(d.label)}</h3>"
                     f"<p>{escape(d.description.strip())}</p>")
            if d.codes:
                b.append("<div class=wrap><table><tbody>" + "".join(
                    f"<tr><td><code>{escape(k)}</code></td><td>{escape(v)}</td></tr>"
                    for k, v in d.codes.items()) + "</tbody></table></div>")
    if ds.caveats:
        b.append("<h2>Caveats</h2><p>Caveats are also returned in every response's "
                 "<code>meta.caveats</code>.</p>")
        b += [f"<div class=note><strong>{escape(c.id)}</strong><br>{escape(c.text.strip())}</div>"
              for c in ds.caveats]
    return _page(f"{ds.title} · {PRODUCT}", "datasets.html", "".join(b), depth=1)


def datasets_page(cat: dict[str, Dataset]) -> str:
    cards = "".join(
        f"<div class=card><h3><a href='datasets/{d.id}.html'>{escape(d.title)}</a></h3>"
        f"<div class='small muted'><code>{d.id}</code> · {d.frequency} · "
        f"<span class='chip {d.status}'>{d.status}</span> · {len(d.measures)} measures</div>"
        f"<p class=small>{escape(d.summary.strip())}</p></div>" for d in cat.values())
    return _page(f"Datasets · {PRODUCT}", "datasets.html",
                 "<h1>Datasets &amp; measures</h1><p class=lede>Every dataset and measure is "
                 "defined in a public catalogue. The definitions below are the same ones the "
                 "API returns in <code>meta.measures</code>.</p>"
                 "<p><span class='chip draft'>draft</span> definitions or coverage may still "
                 "change. <span class='chip experimental'>experimental</span> measures are "
                 "excluded unless requested with <code>include_experimental=true</code>.</p>"
                 f"<div class=cards>{cards}</div>")


def _quickstart_html(responses: dict[str, dict]) -> str:
    parts = []
    for intro, path, params in QUICKSTART:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        response = responses.get(f"{path}?{query}" if query else path)
        parts.append(f"<p>{intro}</p>" + _code(f'curl "{_url(path, params)}"', "shell"))
        if response is not None:
            parts.append("<details class=response-toggle><summary class=small>"
                         "<strong>Response</strong> <span class=muted>(real data; long lists "
                         "and meta shortened)</span></summary>"
                         + _code(_json(response), "json", "response") + "</details>")
    return "\n".join(parts)


def overview_page(cat: dict[str, Dataset], validation: dict | None,
                  quick_responses: dict[str, dict] | None = None) -> str:
    rtt = cat.get("rtt")
    valid = ""
    if validation and validation.get("runs"):
        run = validation["runs"][-1]
        month = datetime.strptime(run["period"], "%Y-%m-%d").strftime("%B %Y")
        valid = (f"<div class=note><strong>Reconciled with NHS England.</strong> For "
                 f"{month}, all {run['rows_compared']:,} provider × specialty rows "
                 f"{'match' if run['ok'] else 'were checked against'} NHS England's published "
                 f"provider figures (waiting list, waits over 18/52/65/78 weeks, median and "
                 f"92nd percentile). Reconciliation runs every month before release.</div>")
    views = "".join(f"<li><code>{v.id}</code>: {escape(v.label)}</li>"
                    for v in (rtt.views if rtt else []))
    body = f"""
<h1>{PRODUCT}</h1>
<p class=lede>Public NHS England performance statistics through a modern JSON API, designed
for human programmers and AI agents alike. Every number comes back with its definition, the
publication it came from, its licence, and the caveats that apply.</p>
{valid}
<h2>Principles</h2>
<ul>
<li><strong>Citable.</strong> Each response's <code>meta</code> block names the dataset,
source page, licence and attribution, and defines every measure returned.</li>
<li><strong>Honest about the data.</strong> Known problems (missed submissions, mergers,
recodes, revisions) are returned as caveats rather than hidden. Missing data is never a
zero.</li>
<li><strong>Matches the publisher.</strong> Measures reproduce NHS England's published
figures exactly, on NHS England's basis.</li>
<li><strong>Open data only.</strong> Every dataset is published under the Open Government
Licence; reuse is permitted with attribution.</li>
</ul>
<h2>Quick start</h2>
<div class=note>The API is not yet publicly deployed. Examples use <code>{escape(BASE)}</code> as
a placeholder for the host.</div>
{_quickstart_html(quick_responses or {})}
<h2>Concepts</h2>
<h3>Views</h3>
<p>Waiting-list data can be grouped by who treats patients or by where they live:</p>
<ul>{views}</ul>
<p>Population views answer "how long are this area's residents waiting, wherever they are
treated?".</p>
<h3>Responses</h3>
{_code('''{
  "data": [ { "period": "2026-09-01", "org_code": "RJ1", "waiting_list_total": 107635, ... } ],
  "meta": {
    "dataset": "rtt",
    "source_page": "https://www.england.nhs.uk/statistics/...",
    "licence": "Open Government Licence v3.0",
    "attribution": "Source: NHS England, ...",
    "caveats": [ { "id": "rtt-no-estimates", "text": "..." } ],
    "measures": { "waiting_list_total": { "label": "...", "unit": "count", "definition": "..." } }
  }
}''', 'json')}
<p>Periods are ISO dates for the first day of the month. Organisations use ODS codes.
Measure ids are stable; see <a href=datasets.html>Datasets &amp; measures</a>.</p>
<h3>Revisions and missing data</h3>
<p>NHS England revises earlier months. The API serves the latest version of each month and
keeps every version. A provider that did not submit has no row for that month (never a
zero); <code>/v1/rtt/submissions</code> lists who did not submit and why (merged or recoded,
closed, or missing).</p>
<h3>Like-for-like changes</h3>
<p>Month-on-month changes come in two forms: the simple difference of published totals, and
a like-for-like version that only compares providers present in both months, following
mergers and recodes. In September 2026 the published waiting list fell by 83,840, but the
like-for-like change was a rise of about 5,500: Nottingham University Hospitals did not
submit.</p>
<h2>For AI agents</h2>
<p>A plain-text summary for language models is at <a href=llms.txt>llms.txt</a>. The full
spec is <a href=openapi.json>openapi.json</a>. Agents should quote <code>meta.attribution</code>
when citing figures and pass on any <code>meta.caveats</code>. An MCP server exposing the
same endpoints as task-shaped tools is planned.</p>
<h2>Licence</h2>
<p>Data: NHS England, Open Government Licence v3.0. Attribution is required; use the
<code>meta.attribution</code> text. This service is independent and is not provided by the
NHS.</p>"""
    return _page(PRODUCT, "index.html", body)


def llms_txt(cat: dict[str, Dataset], spec: dict) -> str:
    lines = [f"# {PRODUCT}", "",
             "> Public NHS England statistics as JSON, with every figure's definition, source,",
             "> licence (Open Government Licence v3.0) and caveats in the response `meta`.", "",
             "Not yet publicly deployed; examples use https://<api-host>.", "",
             "## Rules for using this data", "",
             "- Quote `meta.attribution` when citing figures.",
             "- Pass on `meta.caveats`; a missing row means no submission, never zero.",
             "- Recompute ratios and percentiles from components; never average them.",
             "- Use like-for-like measures for month-on-month change; simple changes are "
             "distorted by missed submissions and mergers.",
             "- Periods are first-of-month ISO dates; organisations are ODS codes "
             "(find them with /v1/organisations?q=).", "",
             "## Endpoints", ""]
    for path, ops in spec["paths"].items():
        op = ops.get("get")
        if op and path != "/health":
            params = ", ".join(p["name"] for p in op.get("parameters", []))
            summary = (op.get("description") or op.get("summary") or "").split("\n")[0]
            lines.append(f"- GET {path}" + (f" ({params})" if params else "") + f": {summary}")
    for ds in cat.values():
        lines += ["", f"## Dataset `{ds.id}`: {ds.title} ({ds.status})", "",
                  ds.summary.strip()]
        if ds.views:
            lines += ["", "Views: " + "; ".join(f"`{v.id}` {v.label}" for v in ds.views)]
        if ds.measures:
            lines += ["", "Measures:"]
            lines += [f"- `{m.id}` ({m.unit}{', ' + m.status if m.status != 'stable' else ''}): "
                      f"{' '.join(m.definition.split())}" for m in ds.measures]
        if ds.caveats:
            lines += ["", "Caveats:"]
            lines += [f"- {' '.join(c.text.split())}" for c in ds.caveats]
    lines += ["", "## Errors", "",
              "- JSON body with `detail` (a message, or a list of problems for invalid "
              "parameters). 404: unknown code or no matching rows (the message says when an "
              "organisation exists but has no data that month). 422: invalid parameter. "
              "503: data not loaded. 429 (planned): rate limited, honour Retry-After."]
    lines += ["", "## Docs", "", "- Endpoints: reference.html", "- Objects: objects.html",
              "- Errors: errors.html", "- OpenAPI: openapi.json",
              "- Datasets & measures: datasets.html", ""]
    return "\n".join(lines)


def build_docs(out_dir: Path | None = None, processed_dir: Path = PROCESSED_DIR,
               validation: dict | None = None) -> list[Path]:
    from .api.app import app

    out_dir = out_dir or OUT
    (out_dir / "datasets").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    cat = load_catalogue()
    spec = app.openapi()
    examples = example_responses(processed_dir)
    available = available_periods(processed_dir)
    api_objects = load_api_objects()
    object_requests = [(o["example"]["path"], o["example"].get("params") or {})
                       for o in api_objects["objects"] if o.get("example")]
    error_requests = [(ex["path"], ex.get("params") or {})
                      for e in api_objects["errors"] for ex in e.get("examples", [])]
    object_responses = call_api(processed_dir, object_requests)
    error_responses = call_api(processed_dir, error_requests)
    files = {
        "assets/docs.css": CSS.strip() + "\n",
        "index.html": overview_page(cat, validation, example_responses(
            processed_dir, [(path, params) for _, path, params in QUICKSTART])),
        "reference.html": reference_page(spec, examples, api_objects["objects"]),
        "objects.html": objects_page(api_objects, cat, object_responses),
        "errors.html": errors_page(api_objects, error_responses),
        "datasets.html": datasets_page(cat),
        "openapi.json": json.dumps(spec, indent=2),
        "llms.txt": llms_txt(cat, spec),
        **{f"datasets/{ds.id}.html": dataset_page(ds, available.get(ds.id))
           for ds in cat.values()},
    }
    written = []
    for rel, text in files.items():
        path = out_dir / rel
        path.write_text(text)
        written.append(path)
    return written
