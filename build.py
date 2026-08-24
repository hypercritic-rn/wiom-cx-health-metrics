#!/usr/bin/env python3
"""Reads dashboard_data.json and generates a static index.html dashboard,
tabbed by journey (B2I / R2E / Closure)."""
import json
import os
import html
from datetime import datetime

JOURNEYS = ["B2I", "R2E", "Closure", "Chat"]
JOURNEY_LABELS = {"B2I": "B2I (Booking to Install)", "R2E": "R2E (Recharge to Exit)", "Closure": "Closure", "Chat": "Chat"}
WINDOW_LABELS = ["D-1", "D-2", "D-3", "W-1", "W-2", "W-3", "M-1", "M-2", "M-3"]

# status palette (fixed, from the dataviz skill reference palette)
STATUS = {
    "good": "#0ca30c",
    "mild_good": "#7cb342",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
    # conversion metrics are business rates with no agreed target yet, so they are
    # rendered neutral rather than being judged against the L0 100% scale. Once a
    # target is set per metric we can colour against it.
    "neutral": "#898781",
}

TIERS = ["L0", "L1"]
TIER_LABELS = {
    "L0": "System health &mdash; should sit at or near 100%",
    "L1": "Conversion &amp; efficiency",
}
# a conversion metric is only final once every booking-day in the window has had its
# full horizon, so recent columns are still accruing and must be marked as such
TIER_NOTES = {
    "L1": (
        "Cohort = bookings that paid the fee in that window; cancelled, refunded and still-open "
        "bookings stay in the denominator. <strong>Only matured cohorts are shown</strong>, so D-1 is "
        "the newest booking day past that metric's horizon, not yesterday. Hover a value for the "
        "dates it covers."
    ),
}


def status_for(value, inverted=False):
    if value is None:
        return None
    v = value
    if inverted:
        # high value = bad (e.g. % stuck) -- mirrored version of the 5-tier scale below
        if v <= 0:
            return "good"
        if v <= 0.5:
            return "mild_good"
        if v <= 5:
            return "warning"
        if v <= 10:
            return "serious"
        return "critical"
    else:
        if v >= 100:
            return "good"
        if v >= 99.5:
            return "mild_good"
        if v >= 95:
            return "warning"
        if v >= 90:
            return "serious"
        return "critical"


def status_for_count(value):
    # positive/count metric: 0 is the target, any backlog is a problem
    if value is None:
        return None
    if value <= 0:
        return "good"
    if value <= 10:
        return "warning"
    if value <= 25:
        return "serious"
    return "critical"


def to_float(v):
    if v is None:
        return None
    if isinstance(v, str):
        if v in ("-", "TBD", ""):
            return None
        try:
            return float(v)
        except ValueError:
            return None
    return float(v)


def mask_mobile(v):
    s = str(v)
    return s if len(s) <= 4 else "•" * (len(s) - 4) + s[-4:]


def fmt_ts(v, null_label="—"):
    if v is None:
        return null_label
    try:
        return datetime.fromisoformat(str(v)).strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except ValueError:
        return html.escape(str(v))


def fmt_int(v, null_label="—"):
    if v is None:
        return null_label
    try:
        return str(int(round(float(v))))
    except (TypeError, ValueError):
        return html.escape(str(v))


def fmt_text(v, null_label="—"):
    return null_label if v is None else html.escape(str(v))


def format_cell(col_type, v, null_label, unmask=False):
    if col_type == "mobile":
        if v is None:
            return null_label
        return html.escape(str(v)) if unmask else mask_mobile(v)
    if col_type == "ts":
        return fmt_ts(v, null_label)
    if col_type == "int":
        return fmt_int(v, null_label)
    return fmt_text(v, null_label)


def build_drilldown_panel(m):
    dd = m.get("drilldown")
    if not dd:
        return ""
    panel_id = f"drill-{m['id']}"
    has_rows = bool(dd.get("rows")) and not dd.get("error")
    null_label = dd.get("null_label", "—")
    col_defs = dd["columns"]
    actions_html = (
        '<div class="drill-actions">'
        '<button class="drill-action" data-action="open-tab">Open in new tab &#8599;</button>'
        '<button class="drill-action" data-action="download-csv">Download CSV &#8595;</button>'
        '</div>'
    ) if has_rows else ""

    raw_data_html = ""
    if dd.get("error"):
        body = f'<p class="drill-note">Could not load defaulter list: {html.escape(dd["error"])}</p>'
    elif not dd.get("rows"):
        body = '<p class="drill-note">No defaulters for this window.</p>'
    else:
        header_cells = "".join(f"<th>{html.escape(c['label'])}</th>" for c in col_defs)
        row_html = []
        full_rows = []
        for r in dd["rows"]:
            # tag each cell with its column type so free-text columns can wrap while
            # timestamps and ids stay on one line
            cells = "".join(
                f"<td class=\"cell-{html.escape(str(c['type']))}\">"
                f"{format_cell(c['type'], v, c.get('null_label', null_label))}</td>"
                for c, v in zip(col_defs, r)
            )
            row_html.append(f"<tr>{cells}</tr>")
            full_rows.append(
                [format_cell(c["type"], v, c.get("null_label", null_label), unmask=True) for c, v in zip(col_defs, r)]
            )
        body = (
            '<div class="drill-scroll"><table class="drill-table"><thead><tr>'
            f'{header_cells}</tr></thead><tbody>{"".join(row_html)}</tbody></table></div>'
        )
        # unmasked mobiles for CSV export only -- the visible table and "open in new tab" stay masked
        raw_json = json.dumps(
            {"columns": [c["label"] for c in col_defs], "rows": full_rows}, ensure_ascii=False
        ).replace("</", "<\\/")
        raw_data_html = f'<script type="application/json" class="drill-raw-data">{raw_json}</script>'
    return f"""
        <tr class="drill-panel-row" id="{panel_id}" style="display:none">
          <td colspan="10">
            <div class="drill-panel" data-metric-name="{html.escape(m["name"])}" data-window="{html.escape(dd["window"])}">
              <div class="drill-title-row">
                <div class="drill-title">{html.escape(dd["window"])} defaulters &mdash; not counted in the numerator</div>
                {actions_html}
              </div>
              {body}
              {raw_data_html}
            </div>
          </td>
        </tr>"""


def build_metric_row(m):
    name = html.escape(m["name"])
    desc = html.escape(m["description"])
    is_stuck_metric = "stuck" in m["name"].lower()

    if m["tbd"]:
        cells = '<td class="tbd-cell" colspan="9">Not yet built &mdash; TBD</td>'
        return f"""
        <tr class="metric-row tbd-row">
          <td class="metric-name">{name}<div class="metric-desc">{desc}</div></td>
          {cells}
        </tr>"""

    raw_values = m.get("values") or [None] * 9
    floats = [to_float(v) for v in raw_values]
    is_count_metric = m.get("unit") == "count"
    maturity = m.get("maturity") or [None] * 9
    horizon = m.get("horizon_days")
    counts = m.get("counts") or [None] * 9

    def counts_html(idx):
        """Small print under a value: the raw numerator/denominator behind it."""
        raw = counts[idx] if idx < len(counts) else None
        if not raw or "/" not in str(raw):
            return ""
        num, _, den = str(raw).partition("/")
        try:
            num, den = f"{int(num):,}", f"{int(den):,}"
        except ValueError:
            pass
        return f'<span class="cell-counts">{html.escape(num)}/{html.escape(den)}</span>'
    has_drilldown = bool(m.get("drilldown"))
    drill_id = f"drill-{m['id']}"

    def maturity_bits(idx):
        """Returns (cell_class_suffix, marker_html, title_attr) for one window.
        A label of "matured" (optionally "matured|<note>") is final: no marker, but any
        note becomes a hover, which is how a shifted-clock cell states its real dates."""
        label = maturity[idx] if idx < len(maturity) else None
        if not label:
            return "", "", ""
        if label == "matured" or label.startswith("matured|"):
            _, _, note = label.partition("|")
            return "", "", (f' title="{html.escape(note)}"' if note else "")
        # label is "<close date>|<days until close>" -- report when the number
        # becomes final rather than how much of the window has elapsed
        close, _, days = label.partition("|")
        when = f" ({days} more day{'' if days == '1' else 's'})" if days else ""
        # a rate over a fixed denominator can only rise as events land; a step
        # conversion has both sides still accruing, so it can fall too
        if m.get("maturing_direction") == "either":
            outcome = "Both sides of this ratio are still growing, so it can move either way."
        else:
            outcome = "The value can only rise."
        tip = f"Still counting &mdash; this window stays open until {close}{when}. {outcome}"
        return " maturing", '<span class="mat-mark">*</span>', f' title="{tip}"'

    def wrap_drill(idx, inner):
        # only the D-1 column (index 0) gets the drilldown toggle
        if has_drilldown and idx == 0:
            return (
                f'<button class="drill-toggle" data-target="{drill_id}" aria-expanded="false">'
                f'{inner}<span class="drill-caret">&#9662;</span></button>'
            )
        return inner

    if is_count_metric:
        cells_html = []
        for idx, dv in enumerate(floats):
            if dv is None:
                cells_html.append('<td class="metric-cell empty">&mdash;</td>')
                continue
            status = status_for_count(dv)
            color = STATUS.get(status, "#898781")
            mcls, mark, tip = maturity_bits(idx)
            inner = f'<span class="dot" style="background:{color}"></span>{int(dv)}{mark}' + counts_html(idx)
            cells_html.append(f'<td class="metric-cell{mcls}"{tip}>{wrap_drill(idx, inner)}</td>')
        cells = "".join(cells_html)
        frac_note = ""
    else:
        # all percentage metrics arrive on a 0-100 scale straight from their queries;
        # never rescale here -- a genuinely collapsed metric (e.g. 0.4%) must show 0.4%
        display_values = floats

        # conversion metrics get a neutral dot: there is no agreed target, so the
        # L0 "under 90% is critical" scale would paint a healthy rate red
        is_conversion = m.get("kind") == "conversion"

        cells_html = []
        for idx, dv in enumerate(display_values):
            if dv is None:
                cells_html.append('<td class="metric-cell empty">&mdash;</td>')
                continue
            if is_conversion:
                color = STATUS["neutral"]
            else:
                status = status_for(dv, inverted=is_stuck_metric)
                color = STATUS.get(status, "#898781")
            mcls, mark, tip = maturity_bits(idx)
            inner = f'<span class="dot" style="background:{color}"></span>{dv:.1f}%{mark}' + counts_html(idx)
            cells_html.append(f'<td class="metric-cell{mcls}"{tip}>{wrap_drill(idx, inner)}</td>')
        cells = "".join(cells_html)
        frac_note = ' <span class="frac-note">(normalized from 0-1 fraction)</span>' if is_fraction else ""

    row_html = f"""
        <tr class="metric-row">
          <td class="metric-name">{name}{frac_note}<div class="metric-desc">{desc}</div></td>
          {cells}
        </tr>"""
    return row_html + build_drilldown_panel(m)


def grid_cell(v):
    """Grid cell encoding: "value", optionally "~num/den" for the small print, optionally
    "|tooltip" when the figure is still partial. Returns (inner_html, title_attr)."""
    if v is None or v == "":
        return "&mdash;", ""
    body, _, tip = str(v).partition("|")
    val, _, counts = body.partition("~")
    mark = ""
    if val.endswith("*"):
        val, mark = val[:-1], '<span class="mat-mark">*</span>'
    inner = html.escape(val) + mark
    if counts:
        inner += f'<span class="cell-counts">{html.escape(counts)}</span>'
    return inner, (f' title="{html.escape(tip)}"' if tip else "")


def build_grid_block(t):
    """A standalone table rendered under a journey's metric table."""
    if t.get("error"):
        body = f'<p class="drill-note">Could not load: {html.escape(t["error"])}</p>'
    elif not t.get("rows"):
        body = '<p class="drill-note">No data.</p>'
    else:
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in (t.get("columns") or []))
        trs = []
        for r in t["rows"]:
            tds = []
            for i, v in enumerate(r):
                if i == 0:
                    tds.append(f'<td class="grid-rowhead">{fmt_text(v)}</td>')
                else:
                    inner, title = grid_cell(v)
                    cls = "metric-cell maturing" if "mat-mark" in inner else "metric-cell"
                    tds.append(f'<td class="{cls}"{title}>{inner}</td>')
            trs.append("<tr>" + "".join(tds) + "</tr>")
        body = (
            '<table class="metrics-table grid-table"><thead><tr>'
            f'{head}</tr></thead><tbody>{"".join(trs)}</tbody></table>'
        )
    desc = f'<div class="section-note">{t["description"]}</div>' if t.get("description") else ""
    note = f'<div class="section-note grid-foot">{t["note"]}</div>' if t.get("note") else ""
    return (
        f'<div class="grid-block"><div class="grid-title">{html.escape(t["name"])}</div>'
        f"{desc}{body}{note}</div>"
    )


def build_journey_table(journey, metrics):
    in_journey = [m for m in metrics if m["journey"] == journey and m.get("type") != "table"]
    by_tier = {t: [m for m in in_journey if m.get("tier", "L0") == t] for t in TIERS}
    # only label the sections when a journey actually has both tiers, so journeys
    # that are still L0-only render exactly as they did before
    show_sections = sum(1 for t in TIERS if by_tier[t]) > 1

    parts = []
    rendered = 0
    for t in TIERS:
        tier_metrics = by_tier[t]
        if not tier_metrics:
            continue
        if show_sections:
            # the note explains the cohort, the horizon and why recent columns are blank,
            # so it is always relevant to a tier that has one
            note = TIER_NOTES.get(t)
            note_html = f'<div class="section-note">{note}</div>' if note else ""
            parts.append(
                f'<tr class="section-row"><td colspan="{len(WINDOW_LABELS) + 1}">'
                f'{TIER_LABELS[t]}{note_html}</td></tr>'
            )
            # the first section sits directly under the table head, so its column
            # labels are still on screen; later sections need them repeated
            if rendered:
                parts.append(
                    '<tr class="repeat-header"><th></th>'
                    + "".join(f"<th>{w}</th>" for w in WINDOW_LABELS)
                    + "</tr>"
                )
        parts.extend(build_metric_row(m) for m in tier_metrics)
        rendered += 1
    rows = "".join(parts)
    header_cells = "".join(f"<th>{w}</th>" for w in WINDOW_LABELS)
    grids = "".join(
        build_grid_block(t)
        for t in metrics
        if t["journey"] == journey and t.get("type") == "table"
    )
    return f"""
    <div class="journey-panel" id="panel-{journey}" role="tabpanel" aria-labelledby="tab-{journey}">
      <table class="metrics-table">
        <thead>
          <tr>
            <th class="metric-name-header">Metric</th>
            {header_cells}
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>{grids}
    </div>"""


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_dir, "dashboard_data.json"), encoding="utf-8") as f:
        data = json.load(f)

    metrics = data["metrics"]
    generated_at = data["generated_at_utc"]

    tabs_html = "".join(
        f'<button class="tab" id="tab-{j}" role="tab" aria-selected="{"true" if i == 0 else "false"}" '
        f'aria-controls="panel-{j}" data-journey="{j}">{JOURNEY_LABELS[j]}</button>'
        for i, j in enumerate(JOURNEYS)
    )
    panels_html = "".join(build_journey_table(j, metrics) for j in JOURNEYS)

    template_path = os.path.join(base_dir, "template.html")
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    output = (
        template
        .replace("{{TABS}}", tabs_html)
        .replace("{{PANELS}}", panels_html)
        .replace("{{GENERATED_AT}}", generated_at)
    )

    out_path = os.path.join(base_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
