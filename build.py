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


def fmt_ts(v):
    if v is None:
        return "no ping"
    try:
        return datetime.fromisoformat(str(v)).strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except ValueError:
        return html.escape(str(v))


def build_drilldown_panel(m):
    dd = m.get("drilldown")
    if not dd:
        return ""
    panel_id = f"drill-{m['id']}"
    has_rows = bool(dd.get("rows")) and not dd.get("error")
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
        header_cells = "".join(f"<th>{html.escape(c)}</th>" for c in dd["columns"])
        row_html = []
        full_rows = []
        for r in dd["rows"]:
            nas_id, mobile, otp_wait, first_ping, last_ping, total_pings = r
            cells = (
                f"<td>{html.escape(str(nas_id))}</td>"
                f"<td>{mask_mobile(mobile)}</td>"
                f"<td>{fmt_ts(otp_wait)}</td>"
                f"<td>{fmt_ts(first_ping)}</td>"
                f"<td>{fmt_ts(last_ping)}</td>"
                f"<td>{total_pings}</td>"
            )
            row_html.append(f"<tr>{cells}</tr>")
            full_rows.append([str(nas_id), str(mobile), fmt_ts(otp_wait), fmt_ts(first_ping), fmt_ts(last_ping), str(total_pings)])
        body = f"""<table class="drill-table"><thead><tr>{header_cells}</tr></thead><tbody>{"".join(row_html)}</tbody></table>"""
        # unmasked mobiles for CSV export only -- the visible table and "open in new tab" stay masked
        raw_json = json.dumps({"columns": dd["columns"], "rows": full_rows}, ensure_ascii=False).replace("</", "<\\/")
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
    has_drilldown = bool(m.get("drilldown"))
    drill_id = f"drill-{m['id']}"

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
            inner = f'<span class="dot" style="background:{color}"></span>{int(dv)}'
            cells_html.append(f'<td class="metric-cell">{wrap_drill(idx, inner)}</td>')
        cells = "".join(cells_html)
        frac_note = ""
    else:
        # detect 0-1 fraction metrics (e.g. Address->Confirm) and normalize to percentage for display
        non_null = [f for f in floats if f is not None]
        is_fraction = bool(non_null) and all(0 <= f <= 1 for f in non_null)
        display_values = [f * 100 if (f is not None and is_fraction) else f for f in floats]

        cells_html = []
        for idx, dv in enumerate(display_values):
            if dv is None:
                cells_html.append('<td class="metric-cell empty">&mdash;</td>')
                continue
            status = status_for(dv, inverted=is_stuck_metric)
            color = STATUS.get(status, "#898781")
            inner = f'<span class="dot" style="background:{color}"></span>{dv:.1f}%'
            cells_html.append(f'<td class="metric-cell">{wrap_drill(idx, inner)}</td>')
        cells = "".join(cells_html)
        frac_note = ' <span class="frac-note">(normalized from 0-1 fraction)</span>' if is_fraction else ""

    row_html = f"""
        <tr class="metric-row">
          <td class="metric-name">{name}{frac_note}<div class="metric-desc">{desc}</div></td>
          {cells}
        </tr>"""
    return row_html + build_drilldown_panel(m)


def build_journey_table(journey, metrics):
    rows = "".join(build_metric_row(m) for m in metrics if m["journey"] == journey)
    header_cells = "".join(f"<th>{w}</th>" for w in WINDOW_LABELS)
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
      </table>
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
