"""Shared constants: healthy operating bands for the hydroponic system.

These double as (a) the physical targets the control loop aims for and
(b) the thresholds used by the SigNoz dashboards, alerts and SLOs. Keeping
them in one place means the simulator, the controller and the alert config
never drift apart.
"""
from __future__ import annotations

# pH -- most leafy crops are happy in a narrow band; outside it nutrients
# "lock out" even when present in the reservoir.
PH_BAND = (5.5, 6.5)          # warn outside this
PH_IDEAL = (5.8, 6.2)         # controller target band
PH_TARGET = 6.0

# EC (electrical conductivity, mS/cm) == nutrient strength.
EC_BAND = (1.2, 2.4)          # generic safe band
EC_TARGET = 1.6               # veg-stage lettuce target
TDS_PER_EC = 640.0            # ppm per mS/cm (the "500 scale" is 500; Hanna uses 640)

# Water temperature (deg C). Warm water holds less oxygen -> root rot.
WATER_TEMP_IDEAL = (18.0, 22.0)
WATER_TEMP_CRITICAL = 24.0    # page above this

# Dissolved oxygen (mg/L). Below ~5 roots start to suffocate.
DO_MIN = 5.0

# Reservoir
RESERVOIR_CAPACITY_L = 100.0
WATER_LEVEL_MIN_PCT = 20.0
RESERVOIR_HOURS_CRITICAL = 3.0  # predictive "dry soon" alert

# Metric catalogue: (otel_metric_name, unit). Units follow UCUM where sensible.
METRICS = [
    ("hydro.ph", "1"),
    ("hydro.ec", "mS/cm"),
    ("hydro.tds", "ppm"),
    ("hydro.water_temp", "Cel"),
    ("hydro.air_temp", "Cel"),
    ("hydro.humidity", "%"),
    ("hydro.dissolved_oxygen", "mg/L"),
    ("hydro.water_level", "%"),
    ("hydro.reservoir_volume", "L"),
    ("hydro.light_ppfd", "umol/m2/s"),
    ("hydro.co2", "ppm"),
    ("hydro.pump_flow", "L/min"),
    ("hydro.reservoir.hours_to_empty", "h"),
]


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
