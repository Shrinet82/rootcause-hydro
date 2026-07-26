"""Generate (and optionally create) the SigNoz dashboards + alert specs.

Design principle: match the *panel type* to the signal.
  * current vitals  -> Value panels (big number + threshold colour)
  * SLO summary     -> Table panel (metric / current / target at a glance)
  * trends          -> Time-series panels
Not everything is a line chart.

Single source of truth for the panels lives in DASHBOARDS below, so the JSON
files under signoz/dashboards/ and any API-created dashboards never drift.

Usage
-----
    python signoz/apply_signoz.py --write-json                 # write importable JSON
    python signoz/apply_signoz.py --write-json --no-thresholds # if colours break import
    SIGNOZ_API_KEY=... python signoz/apply_signoz.py --create  # create via API

Dashboard JSON follows SigNoz's builder-query format. Field names occasionally
change between SigNoz versions -- if --create or import rejects a panel, use the
UI (Dashboards -> New -> Import JSON) or add panels by hand with the metric
names and thresholds below. The engine + metric names are the stable part.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

# ---- threshold specs: (operator, value, colour, label). "low is bad" uses <=.
TH_GREEN, TH_AMBER, TH_RED = "#2bbf6a", "#f5a623", "#ff4d4f"

# panel spec keys: title, metric(s), unit, type, thresholds
#   type: "value" | "graph" | "table"
#   thresholds: list of (operator, value, colour, label)
DASHBOARDS = {
    "grow_room_overview": {
        "title": "RootCause - Grow Room Overview",
        "description": "Vitals at a glance. Value tiles for now, trends below.",
        "tags": ["rootcause", "hydroponics"],
        "panels": [
            {"title": "pH", "metric": "hydro.ph", "unit": "none", "type": "value",
             "thresholds": [(">=", 6.5, TH_RED, "high"), (">=", 6.2, TH_AMBER, "warn"),
                            ("<=", 5.5, TH_RED, "low"), ("<=", 5.8, TH_AMBER, "warn")]},
            {"title": "EC (mS/cm)", "metric": "hydro.ec", "unit": "none", "type": "value",
             "thresholds": [(">=", 2.4, TH_RED, "burn"), ("<=", 1.2, TH_RED, "starve")]},
            {"title": "Water Temp", "metric": "hydro.water_temp", "unit": "celsius",
             "type": "value",
             "thresholds": [(">=", 24, TH_RED, "root rot"), (">=", 22, TH_AMBER, "warm")]},
            {"title": "Dissolved O2 (mg/L)", "metric": "hydro.dissolved_oxygen",
             "unit": "none", "type": "value",
             "thresholds": [("<=", 5, TH_RED, "suffocating"), ("<=", 6, TH_AMBER, "low")]},
            {"title": "Water Level (%)", "metric": "hydro.water_level", "unit": "percent",
             "type": "value",
             "thresholds": [("<=", 20, TH_RED, "low"), ("<=", 40, TH_AMBER, "watch")]},
            {"title": "Hours to Empty", "metric": "hydro.reservoir.hours_to_empty",
             "unit": "h", "type": "value",
             "thresholds": [("<=", 3, TH_RED, "critical"), ("<=", 12, TH_AMBER, "watch")]},
            {"title": "pH - trend", "metric": "hydro.ph", "unit": "none", "type": "graph"},
            {"title": "EC - trend", "metric": "hydro.ec", "unit": "none", "type": "graph"},
        ],
    },
    "reservoir_and_dosing": {
        "title": "RootCause - Reservoir & Dosing",
        "description": "Reservoir status tiles + nutrient/pump trends.",
        "tags": ["rootcause", "hydroponics", "dosing"],
        "panels": [
            {"title": "Reservoir Volume (L)", "metric": "hydro.reservoir_volume",
             "unit": "none", "type": "value",
             "thresholds": [("<=", 20, TH_RED, "low"), ("<=", 40, TH_AMBER, "watch")]},
            {"title": "Pump Flow (L/min)", "metric": "hydro.pump_flow", "unit": "none",
             "type": "value", "thresholds": [("<=", 0.1, TH_RED, "pump down")]},
            {"title": "Hours to Empty", "metric": "hydro.reservoir.hours_to_empty",
             "unit": "h", "type": "value",
             "thresholds": [("<=", 3, TH_RED, "critical"), ("<=", 12, TH_AMBER, "watch")]},
            {"title": "EC burn-down (plants drinking)", "metric": "hydro.ec",
             "unit": "none", "type": "graph"},
            {"title": "Reservoir Volume - trend", "metric": "hydro.reservoir_volume",
             "unit": "none", "type": "graph"},
            {"title": "CO2 (ppm)", "metric": "hydro.co2", "unit": "none", "type": "graph"},
            {"title": "Light PPFD", "metric": "hydro.light_ppfd", "unit": "none",
             "type": "graph"},
        ],
    },
    "plant_health_slo": {
        "title": "RootCause - Plant Health SLO",
        "description": "Vitals scorecard (table) + SLO trend lines.",
        "tags": ["rootcause", "hydroponics", "slo"],
        "panels": [
            {"title": "Vitals scorecard", "type": "table",
             "metrics": [("hydro.ph", "pH (target 5.5-6.5)"),
                         ("hydro.water_temp", "Water Temp (<24C)"),
                         ("hydro.dissolved_oxygen", "Dissolved O2 (>5)"),
                         ("hydro.ec", "EC (1.2-2.4)")]},
            {"title": "pH (SLO: 5.5-6.5)", "metric": "hydro.ph", "unit": "none",
             "type": "graph"},
            {"title": "Water Temp (SLO: <24C)", "metric": "hydro.water_temp",
             "unit": "celsius", "type": "graph"},
            {"title": "Dissolved O2 (SLO: >5 mg/L)", "metric": "hydro.dissolved_oxygen",
             "unit": "none", "type": "graph"},
        ],
    },
}

# alerts: (name, metric, op, threshold, severity, note)
ALERTS = [
    ("pH out of band (high)", "hydro.ph", ">", 6.5, "warning", "nutrient lockout risk"),
    ("pH out of band (low)", "hydro.ph", "<", 5.5, "warning", "nutrient lockout risk"),
    ("Water temp critical", "hydro.water_temp", ">", 24.0, "critical", "root-rot / low O2"),
    ("Dissolved oxygen low", "hydro.dissolved_oxygen", "<", 5.0, "critical", "roots suffocating"),
    ("EC below safe band", "hydro.ec", "<", 1.2, "warning", "nutrient deficiency"),
    ("EC above safe band", "hydro.ec", ">", 2.4, "warning", "nutrient burn"),
    ("Reservoir dry soon", "hydro.reservoir.hours_to_empty", "<", 3.0, "critical",
     "PREDICTIVE - page before it's empty"),
]


def _metric_query(metric, legend, query_name="A", agg="avg", group_by=("zone",)):
    return {
        "dataSource": "metrics",
        "queryName": query_name,
        "expression": query_name,
        "aggregateOperator": agg,
        "timeAggregation": agg,
        "spaceAggregation": agg,
        "aggregateAttribute": {
            "key": metric, "dataType": "float64", "type": "Gauge", "isColumn": True,
        },
        "filters": {"op": "AND", "items": []},
        "groupBy": [
            {"key": k, "dataType": "string", "type": "tag", "isColumn": False}
            for k in group_by
        ],
        "having": [], "functions": [], "orderBy": [],
        "legend": legend, "reduceTo": "last", "stepInterval": 60, "disabled": False,
    }


def _thresholds(specs):
    out = []
    for op, val, color, label in specs:
        out.append({
            "index": str(uuid.uuid4())[:8], "keyIndex": 0, "moveThreshold": 0,
            "selectedGraph": "value", "thresholdColor": color, "thresholdFormat": "Number",
            "thresholdLabel": label, "thresholdOperator": op, "thresholdTableOptions": "",
            "thresholdUnit": "", "thresholdValue": val,
        })
    return out


def _widget(idx, panel, with_thresholds=True):
    ptype = panel["type"]
    if ptype == "table":
        letters = "ABCDEFGH"
        queries = [
            _metric_query(m, legend, query_name=letters[i], group_by=())
            for i, (m, legend) in enumerate(panel["metrics"])
        ]
        unit = "none"
    else:
        group_by = () if ptype == "value" else ("zone",)
        queries = [_metric_query(panel["metric"], panel["title"], group_by=group_by)]
        unit = panel.get("unit", "none")
    w = {
        "id": f"w{idx}",
        "title": panel["title"],
        "description": "",
        "panelTypes": ptype,
        "yAxisUnit": unit,
        "query": {
            "queryType": "builder", "promql": [], "clickhouse_sql": [],
            "builder": {"queryData": queries, "queryFormulas": []},
        },
    }
    if with_thresholds and panel.get("thresholds"):
        w["thresholds"] = _thresholds(panel["thresholds"])
    return w


def _size(ptype):
    return {"value": (3, 3), "graph": (6, 3), "table": (12, 4)}.get(ptype, (6, 3))


def build_dashboard(spec, with_thresholds=True):
    widgets, layout = [], []
    x = y = rowh = 0
    for i, panel in enumerate(spec["panels"]):
        widgets.append(_widget(i, panel, with_thresholds))
        w, h = _size(panel["type"])
        if x + w > 12:
            x, y, rowh = 0, y + rowh, 0
        layout.append({"i": f"w{i}", "x": x, "y": y, "w": w, "h": h})
        x += w
        rowh = max(rowh, h)
    return {
        "title": spec["title"], "description": spec["description"], "tags": spec["tags"],
        "layout": layout, "widgets": widgets, "variables": {},
    }


def write_json(outdir, with_thresholds=True):
    os.makedirs(outdir, exist_ok=True)
    for name, spec in DASHBOARDS.items():
        path = os.path.join(outdir, f"{name}.json")
        with open(path, "w") as f:
            json.dump(build_dashboard(spec, with_thresholds), f, indent=2)
        types = ", ".join(sorted({p["type"] for p in spec["panels"]}))
        print(f"wrote {path}  (panel types: {types})")
    with open(os.path.join(outdir, "..", "alerts.json"), "w") as f:
        json.dump([{"name": n, "metric": m, "op": o, "threshold": t,
                    "severity": s, "note": note}
                   for (n, m, o, t, s, note) in ALERTS], f, indent=2)
    print("wrote signoz/alerts.json")


def create_via_api(with_thresholds=True):
    import requests
    url = os.getenv("SIGNOZ_URL", "http://localhost:8080").rstrip("/")
    key = os.getenv("SIGNOZ_API_KEY")
    if not key:
        print("ERROR: set SIGNOZ_API_KEY (SigNoz -> Settings -> API Keys)", file=sys.stderr)
        return 2
    headers = {"SIGNOZ-API-KEY": key, "Content-Type": "application/json"}
    ok = True
    for name, spec in DASHBOARDS.items():
        try:
            r = requests.post(f"{url}/api/v1/dashboards", headers=headers,
                              json=build_dashboard(spec, with_thresholds), timeout=15)
            if r.status_code < 300:
                print(f"created: {spec['title']}")
            else:
                ok = False
                print(f"FAILED {spec['title']}: {r.status_code} {r.text[:160]}")
                print(f"  -> import signoz/dashboards/{name}.json from the UI instead")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"FAILED {spec['title']}: {exc}")
    print_alert_guide()
    return 0 if ok else 1


def print_alert_guide():
    print("\n--- Create these alerts in SigNoz (Alerts -> New Alert -> Metric) ---")
    for (n, m, o, t, s, note) in ALERTS:
        print(f"  [{s:8}] {n:26} : {m} {o} {t}   ({note})")
    print("  [exception] Pump actuation failure   : Exceptions alert on PumpTimeoutError")
    print("  [anomaly ] Abnormal EC drop / drain  : Anomaly alert on hydro.ec\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--write-json", action="store_true")
    p.add_argument("--create", action="store_true")
    p.add_argument("--no-thresholds", action="store_true",
                   help="omit colour thresholds if they break import on your SigNoz version")
    args = p.parse_args()
    wt = not args.no_thresholds
    here = os.path.dirname(os.path.abspath(__file__))
    if args.write_json or not args.create:
        write_json(os.path.join(here, "dashboards"), wt)
        print_alert_guide()
    if args.create:
        return create_via_api(wt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
