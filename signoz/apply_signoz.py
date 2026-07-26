"""Generate (and optionally create) the SigNoz dashboards + alert specs.

Single source of truth for the panels lives in PANELS below, so the JSON
files under signoz/dashboards/ and any API-created dashboards never drift.

Usage
-----
    # just write the importable JSON files (no network):
    python signoz/apply_signoz.py --write-json

    # create the dashboards in a running SigNoz via its API:
    export SIGNOZ_URL=http://localhost:8080
    export SIGNOZ_API_KEY=<key from SigNoz Settings -> API Keys>
    python signoz/apply_signoz.py --create

Dashboard JSON follows SigNoz's builder-query format. Field names occasionally
change between SigNoz versions -- if --create rejects a panel, import the JSON
from the UI (Dashboards -> + New -> Import JSON) or build panels by hand using
the metric names below. The alert thresholds are printed for quick UI setup.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# --- compact panel spec: (metric, title, unit, panel_type) ---
PANELS = {
    "grow_room_overview": {
        "title": "RootCause - Grow Room Overview",
        "description": "Golden signals for the reservoir. Green = healthy band.",
        "tags": ["rootcause", "hydroponics"],
        "panels": [
            ("hydro.ph", "pH", "none", "graph"),
            ("hydro.ec", "EC (mS/cm)", "none", "graph"),
            ("hydro.water_temp", "Water Temp", "celsius", "graph"),
            ("hydro.dissolved_oxygen", "Dissolved Oxygen (mg/L)", "none", "graph"),
            ("hydro.water_level", "Water Level", "percent", "graph"),
            ("hydro.reservoir.hours_to_empty", "Hours to Empty", "h", "value"),
        ],
    },
    "reservoir_and_dosing": {
        "title": "RootCause - Reservoir & Dosing",
        "description": "Nutrient consumption, dosing activity and reservoir drain.",
        "tags": ["rootcause", "hydroponics", "dosing"],
        "panels": [
            ("hydro.ec", "EC burn-down (plants drinking)", "none", "graph"),
            ("hydro.tds", "TDS (ppm)", "none", "graph"),
            ("hydro.reservoir_volume", "Reservoir Volume (L)", "none", "graph"),
            ("hydro.pump_flow", "Pump Flow (L/min)", "none", "graph"),
            ("hydro.co2", "CO2 (ppm)", "none", "graph"),
            ("hydro.light_ppfd", "Light PPFD", "none", "graph"),
        ],
    },
    "plant_health_slo": {
        "title": "RootCause - Plant Health SLO",
        "description": "Time-in-band for the vital signs. Track your error budget.",
        "tags": ["rootcause", "hydroponics", "slo"],
        "panels": [
            ("hydro.ph", "pH (SLO: 5.5-6.5)", "none", "graph"),
            ("hydro.water_temp", "Water Temp (SLO: <24C)", "celsius", "graph"),
            ("hydro.dissolved_oxygen", "Dissolved O2 (SLO: >5 mg/L)", "none", "graph"),
        ],
    },
}

# --- alerts: (name, metric, op, threshold, severity, note) ---
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

# Suggested non-threshold alerts (create in UI):
#  * Exceptions-based alert on PumpTimeoutError  -> Alerts -> Exceptions
#  * Anomaly alert on hydro.ec drop-rate         -> Alert type: Anomaly


def _metric_query(metric: str, legend: str, agg: str = "avg"):
    return {
        "dataSource": "metrics",
        "queryName": "A",
        "expression": "A",
        "aggregateOperator": agg,
        "timeAggregation": agg,
        "spaceAggregation": agg,
        "aggregateAttribute": {
            "key": metric, "dataType": "float64", "type": "Gauge", "isColumn": True,
        },
        "filters": {"op": "AND", "items": []},
        "groupBy": [{"key": "zone", "dataType": "string", "type": "tag", "isColumn": False}],
        "having": [],
        "functions": [],
        "orderBy": [],
        "legend": legend,
        "reduceTo": "last",
        "stepInterval": 60,
        "disabled": False,
    }


def _widget(idx: int, metric: str, title: str, unit: str, panel: str):
    return {
        "id": f"w{idx}",
        "title": title,
        "description": "",
        "panelTypes": panel,
        "yAxisUnit": unit,
        "query": {
            "queryType": "builder",
            "promql": [],
            "clickhouse_sql": [],
            "builder": {
                "queryData": [_metric_query(metric, title)],
                "queryFormulas": [],
            },
        },
    }


def build_dashboard(spec: dict) -> dict:
    widgets, layout = [], []
    for i, (metric, title, unit, panel) in enumerate(spec["panels"]):
        widgets.append(_widget(i, metric, title, unit, panel))
        layout.append({"i": f"w{i}", "x": (i % 2) * 6, "y": (i // 2) * 3, "w": 6, "h": 3})
    return {
        "title": spec["title"],
        "description": spec["description"],
        "tags": spec["tags"],
        "layout": layout,
        "widgets": widgets,
        "variables": {},
    }


def write_json(outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    for name, spec in PANELS.items():
        path = os.path.join(outdir, f"{name}.json")
        with open(path, "w") as f:
            json.dump(build_dashboard(spec), f, indent=2)
        print(f"wrote {path}")
    with open(os.path.join(outdir, "..", "alerts.json"), "w") as f:
        json.dump(
            [
                {"name": n, "metric": m, "op": o, "threshold": t,
                 "severity": s, "note": note}
                for (n, m, o, t, s, note) in ALERTS
            ],
            f, indent=2,
        )
    print("wrote signoz/alerts.json")


def create_via_api() -> int:
    import requests  # local import so --write-json needs no deps

    url = os.getenv("SIGNOZ_URL", "http://localhost:8080").rstrip("/")
    key = os.getenv("SIGNOZ_API_KEY")
    if not key:
        print("ERROR: set SIGNOZ_API_KEY (SigNoz -> Settings -> API Keys)", file=sys.stderr)
        return 2
    headers = {"SIGNOZ-API-KEY": key, "Content-Type": "application/json"}
    ok = True
    for name, spec in PANELS.items():
        body = build_dashboard(spec)
        try:
            r = requests.post(f"{url}/api/v1/dashboards", headers=headers,
                              json=body, timeout=15)
            if r.status_code < 300:
                print(f"created dashboard: {spec['title']}")
            else:
                ok = False
                print(f"FAILED {spec['title']}: {r.status_code} {r.text[:200]}")
                print("  -> import signoz/dashboards/%s.json from the UI instead" % name)
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"FAILED {spec['title']}: {exc}")
    print_alert_guide()
    return 0 if ok else 1


def print_alert_guide() -> None:
    print("\n--- Create these alerts in SigNoz (Alerts -> New Alert -> Metric) ---")
    for (n, m, o, t, s, note) in ALERTS:
        print(f"  [{s:8}] {n:26} : {m} {o} {t}   ({note})")
    print("  [exception] Pump actuation failure   : Exceptions alert on PumpTimeoutError")
    print("  [anomaly ] Abnormal EC drop / drain  : Anomaly alert on hydro.ec\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--write-json", action="store_true", help="write importable dashboard JSON")
    p.add_argument("--create", action="store_true", help="create dashboards via SigNoz API")
    args = p.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    if args.write_json or not args.create:
        write_json(os.path.join(here, "dashboards"))
        print_alert_guide()
    if args.create:
        return create_via_api()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
