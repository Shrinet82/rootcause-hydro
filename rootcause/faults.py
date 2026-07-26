"""Fault injection -- the source of every dramatic moment in the demo.

The FaultManager is the single shared source of truth. The twin and the
dosing controller both consult it (via `name in fault_manager`), so toggling
a fault from the API instantly changes physics and control behaviour.
"""
from __future__ import annotations

from typing import Set

KNOWN_FAULTS = {
    "heatwave",       # water/air temp climbs -> dissolved oxygen crashes (root rot)
    "pump_failure",   # circulation stops; dosing actuation raises PumpTimeoutError
    "ph_drift",       # pH climbs ~4x faster than normal
    "leak",           # reservoir drains far faster than evapotranspiration
    "nutrient_burn",  # EC creeps above the safe band
    "sensor_glitch",  # pH probe intermittently returns NaN
}


class UnknownFault(ValueError):
    pass


class FaultManager:
    def __init__(self):
        self._active: Set[str] = set()

    def inject(self, name: str) -> None:
        if name not in KNOWN_FAULTS:
            raise UnknownFault(f"unknown fault '{name}'. known: {sorted(KNOWN_FAULTS)}")
        self._active.add(name)

    def clear(self, name: str = None) -> None:
        if name is None:
            self._active.clear()
        else:
            self._active.discard(name)

    def active(self) -> Set[str]:
        return set(self._active)

    def __contains__(self, name: str) -> bool:
        return name in self._active

    def __repr__(self) -> str:
        return f"FaultManager(active={sorted(self._active)})"
