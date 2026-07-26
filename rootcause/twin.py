"""A physics-informed digital twin of a small deep-water-culture hydroponic rig.

The data is synthetic but *causal*: pH drifts up as plants strip nutrients,
EC falls as they drink, warm water holds less oxygen, lights drive a diurnal
temperature/humidity cycle, and the reservoir slowly empties. A judge can
look at any signal and reason about *why* it moved -- which is the whole
point, and what separates this from random `fake_metric()` noise.

Faults perturb these same equations, so incidents look real in SigNoz.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

from .constants import (
    EC_TARGET,
    RESERVOIR_CAPACITY_L,
    TDS_PER_EC,
    clamp,
)


@dataclass
class TwinState:
    ph: float = 6.0
    ec: float = 1.6                 # mS/cm
    tds: float = 1024.0             # ppm
    water_temp_c: float = 20.0
    air_temp_c: float = 21.0
    humidity_pct: float = 60.0
    do_mg_l: float = 7.5            # dissolved oxygen
    water_level_pct: float = 90.0
    reservoir_volume_l: float = 90.0
    light_ppfd: float = 0.0
    co2_ppm: float = 450.0
    pump_flow_l_min: float = 2.5
    sim_minutes: float = 0.0

    def as_dict(self) -> dict:
        return {k: round(v, 3) for k, v in asdict(self).items()}


class HydroTwin:
    def __init__(
        self,
        zone: str = "zone-a",
        crop: str = "lettuce",
        stage: str = "veg",
        photoperiod_hours: float = 18.0,
        seed: int = 42,
    ):
        self.zone = zone
        self.crop = crop
        self.stage = stage
        self.photoperiod_hours = photoperiod_hours
        self.ppfd_target = 250.0
        self.rng = random.Random(seed)
        self.s = TwinState()
        self._heat_ramp = 0.0

    # ---- helpers ----
    def _noise(self, sigma: float) -> float:
        return self.rng.gauss(0.0, sigma)

    @property
    def hour_of_day(self) -> float:
        return (self.s.sim_minutes / 60.0) % 24.0

    @property
    def is_light(self) -> bool:
        return self.hour_of_day < self.photoperiod_hours

    # ---- main integration step ----
    def step(self, dt_minutes: float, faults) -> TwinState:
        s = self.s
        s.sim_minutes += dt_minutes
        scale = dt_minutes / 10.0  # most rates are tuned per 10 sim-minutes
        light = self.is_light

        # Light
        s.light_ppfd = clamp(self.ppfd_target + self._noise(8), 0, 400) if light else 0.0

        # Air temperature: diurnal sinusoid, warmer under lights, + heatwave ramp
        base = 20.0 + 3.0 * math.sin(2 * math.pi * (self.hour_of_day - 9) / 24.0)
        if light:
            base += 2.0
        if "heatwave" in faults:
            self._heat_ramp = min(self._heat_ramp + 0.8 * scale, 12.0)
        else:
            self._heat_ramp = max(self._heat_ramp - 0.5 * scale, 0.0)
        base += self._heat_ramp
        s.air_temp_c = base + self._noise(0.3)

        # Humidity: falls as it warms and under lights
        s.humidity_pct = clamp(
            72 - (s.air_temp_c - 20) * 2.5 - (8 if light else 0) + self._noise(1.5), 25, 95
        )

        # Water temperature lags air temperature
        s.water_temp_c += (s.air_temp_c - s.water_temp_c) * 0.08 * scale + self._noise(0.05)

        # Pump (circulation + aeration)
        pump_ok = "pump_failure" not in faults
        s.pump_flow_l_min = (2.5 + self._noise(0.1)) if pump_ok else 0.0

        # Dissolved oxygen: solubility drops with temp; pump adds aeration;
        # stagnation (pump down) bleeds it away.
        do_sat = max(0.0, 14.6 - 0.4 * s.water_temp_c)
        aeration = 0.6 if pump_ok else 0.0
        s.do_mg_l += ((do_sat + aeration) - s.do_mg_l) * 0.1 * scale
        if not pump_ok:
            s.do_mg_l -= 0.05 * dt_minutes
        s.do_mg_l = clamp(s.do_mg_l + self._noise(0.05), 0.0, 15.0)

        # EC: plants drink -> EC falls (faster under light). Nutrient burn pushes it up.
        uptake = (0.0012 if light else 0.0004) * dt_minutes
        s.ec -= uptake
        if "nutrient_burn" in faults:
            s.ec += 0.010 * dt_minutes
        s.ec = clamp(s.ec + self._noise(0.005), 0.2, 4.0)
        s.tds = s.ec * TDS_PER_EC

        # pH: drifts up as nutrients are absorbed; ph_drift accelerates it.
        drift = 0.003 * dt_minutes
        if "ph_drift" in faults:
            drift *= 4.0
        s.ph = clamp(s.ph + drift + self._noise(0.006), 3.5, 8.5)

        # Reservoir: evapotranspiration + uptake; a leak drains it fast.
        et = (0.05 if light else 0.02) * dt_minutes
        if "leak" in faults:
            et += 0.40 * dt_minutes
        s.reservoir_volume_l = clamp(s.reservoir_volume_l - et, 0.0, RESERVOIR_CAPACITY_L)
        s.water_level_pct = 100.0 * s.reservoir_volume_l / RESERVOIR_CAPACITY_L

        # CO2: enriched under light, near-ambient at night
        s.co2_ppm = (1000 if light else 420) + self._noise(20)
        return s

    # ---- sensors (may misbehave under faults) ----
    def read_ph(self, faults) -> float:
        if "sensor_glitch" in faults and self.rng.random() < 0.5:
            return float("nan")
        return self.s.ph

    def read_ec(self, faults) -> float:
        return self.s.ec

    # ---- actuators (mutate reservoir chemistry) ----
    def apply_dose(self, kind: str, ml: float) -> None:
        if kind == "ph_down":
            self.s.ph = clamp(self.s.ph - 0.02 * ml, 3.5, 8.5)
        elif kind == "ph_up":
            self.s.ph = clamp(self.s.ph + 0.02 * ml, 3.5, 8.5)
        elif kind == "nutrient_ab":
            self.s.ec = clamp(self.s.ec + 0.01 * ml, 0.2, 4.0)
            self.s.tds = self.s.ec * TDS_PER_EC

    def top_up(self, liters: float) -> None:
        self.s.reservoir_volume_l = clamp(
            self.s.reservoir_volume_l + liters, 0.0, RESERVOIR_CAPACITY_L
        )
        self.s.water_level_pct = 100.0 * self.s.reservoir_volume_l / RESERVOIR_CAPACITY_L
