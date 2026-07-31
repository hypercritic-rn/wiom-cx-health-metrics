#!/usr/bin/env python3
"""Pulls all Product Health - CX metrics from Metabase and writes dashboard_data.json.

Metabase key resolution order: METABASE_KEY env var, then Desktop/.env (local dev).
"""
import json
import os
import re
import sys
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
    return None, None, last_err


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_dir, "metrics_config.json"), encoding="utf-8") as f:
        metrics = json.load(f)

    key = get_key()
    results = []
    for m in metrics:
        entry = {
            "id": m["id"],
            "journey": m["journey"],
            "name": m["name"],
            "description": m["description"],
            "tbd": m["tbd"],
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
                # first row, columns after the kpi-name column are D-1..M-3
                row = rows[0] if rows else []
                values = row[1:] if len(row) > 1 else [None] * 9
                entry["values"] = values
                entry["error"] = None

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
