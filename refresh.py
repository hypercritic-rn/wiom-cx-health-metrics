#!/usr/bin/env python3
"""Pulls all Product Health - CX metrics from Metabase and writes dashboard_data.json.

Metabase key resolution order: METABASE_KEY env var, then Desktop/.env (local dev).
"""
import json
import os
import re
import sys
import time
import urllib.request
import datetime

METABASE_URL = "https://metabase.wiom.in"
SNOWFLAKE_DB_ID = 113


def get_key():
    key = os.environ.get("METABASE_KEY")
    if key:
        return key.strip()
    env_path = os.path.expanduser("~/Desktop/.env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"'([^']+)'", content)
        if m:
            return m.group(1).strip()
    raise RuntimeError("No Metabase key found (set METABASE_KEY or provide Desktop/.env)")


def run_query(key, sql, retries=3, timeout=280):
    payload = {"database": SNOWFLAKE_DB_ID, "type": "native", "native": {"query": sql}}
    req = urllib.request.Request(
        f"{METABASE_URL}/api/dataset",
        data=json.dumps(payload).encode(),
        headers={"X-API-Key": key, "Content-Type": "application/json"},
    )
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.load(resp)
            rows = result.get("data", {}).get("rows", [])
            cols = [c["name"] for c in result.get("data", {}).get("cols", [])]
            return rows, cols, None
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            # transient DNS/network blips need time to clear, not an instant retry
            if attempt < retries - 1:
                time.sleep(10)
    return None, None, last_err


def _to_num(v):
    if isinstance(v, str):
        if v.strip() in ("", "-"):
            return None
        try:
            return float(v)
        except ValueError:
            return v
    return v


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_dir, "metrics_config.json"), encoding="utf-8") as f:
        metrics = json.load(f)

    key = get_key()
    results = []
    for m in metrics:
        # a "table" entry is a standalone grid rendered below the journey's metric table,
        # not a single-rate metric row -- store the whole result set rather than one row
        if m.get("type") == "table":
            rows, cols, err = run_query(key, m["query"])
            results.append({
                "id": m["id"],
                "journey": m["journey"],
                "type": "table",
                "name": m["name"],
                "description": m["description"],
                "note": m.get("note"),
                "columns": cols,
                "rows": rows,
                "error": err[:500] if err else None,
            })
            print(f"  [{'ok' if not err else 'ERR'}] (table) {m['name']}")
            continue
        entry = {
            "id": m["id"],
            "journey": m["journey"],
            "name": m["name"],
            "description": m["description"],
            "tbd": m["tbd"],
            "unit": m.get("unit"),
            # tier drives which section of the journey panel the metric renders in;
            # kind drives the colour scale (conversion rates have no 100% target)
            "tier": m.get("tier", "L0"),
            "kind": m.get("kind"),
            "horizon_days": m.get("horizon_days"),
            "maturing_direction": m.get("maturing_direction"),
        }
        if m["tbd"]:
            entry["values"] = None
            entry["error"] = None
        else:
            rows, cols, err = run_query(key, m["query"])
            if err:
                entry["values"] = None
                entry["error"] = err[:500]
            else:
                # first row, columns after the kpi-name column are D-1..M-3 (some metrics only
                # return a shorter prefix, e.g. D-1..D-3 -- pad the rest with None)
                row = rows[0] if rows else []
                values = (row[1:] if len(row) > 1 else [])[:9]
                values += [None] * (9 - len(values))
                # Metabase serializes some DECIMAL columns as strings -- coerce the
                # value columns to float so consumers never see a numeric string
                values = [_to_num(v) for v in values]
                entry["values"] = values
                entry["error"] = None
                # conversion metrics also return a maturity label per window in
                # columns 10-18 ("matured", or "X/Y" booking-days complete), so the
                # dashboard can mark which columns are final. Metrics that return only
                # the 10 value columns simply have no maturity row.
                maturity = row[10:19] if m.get("horizon_days") and len(row) > 10 else []
                entry["maturity"] = (maturity + [None] * 9)[:9] if maturity else None
                # columns 20-28 carry the raw "numerator/denominator" per window,
                # shown as small print under each percentage
                counts = row[19:28] if m.get("horizon_days") and len(row) > 19 else []
                entry["counts"] = (counts + [None] * 9)[:9] if counts else None

            if m.get("drilldown"):
                d_rows, d_cols, d_err = run_query(key, m["drilldown"]["query"])
                entry["drilldown"] = {
                    "window": m["drilldown"]["window"],
                    "columns": m["drilldown"]["columns"],
                    "null_label": m["drilldown"].get("null_label", "—"),
                    "rows": d_rows,
                    "error": d_err[:500] if d_err else None,
                }
        results.append(entry)
        print(f"  [{'TBD' if m['tbd'] else 'ok' if not entry.get('error') else 'ERR'}] {m['name']}")

    output = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metrics": results,
    }
    out_path = os.path.join(base_dir, "dashboard_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
