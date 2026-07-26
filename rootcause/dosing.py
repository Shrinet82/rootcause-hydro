"""The nutrient-dosing control loop -- rendered as a distributed trace.

Every cycle is one trace:

    dosing.cycle
    |-- sensor.read       (measure pH / EC)
    |-- controller.decide (compute corrections)
    |-- pump.actuate      (one per correction -- can raise PumpTimeoutError)
    `-- sensor.verify     (re-measure, did it converge?)

A dosing cycle is literally a sense -> decide -> actuate -> verify control
loop, which is exactly the shape of a distributed trace. That mapping is the
core idea of the whole project.

The controller corrects pH AND nutrient strength in the same cycle, so at
steady state every vital sits inside its healthy band.
"""
from __future__ import annotations

import math

from opentelemetry.trace import Status, StatusCode

from .constants import EC_TARGET, PH_IDEAL, PH_TARGET


class PumpTimeoutError(Exception):
    """Raised when an actuator (dosing pump) does not respond."""


class SensorReadError(Exception):
    """Raised when a sensor returns an invalid (NaN / out-of-range) reading."""


class DosingController:
    def __init__(self, twin, tracer, logger):
        self.twin = twin
        self.tracer = tracer
        self.logger = logger
        self.cycles = 0
        self.last = None

    def _attrs(self):
        return {"zone": self.twin.zone, "crop": self.twin.crop, "stage": self.twin.stage}

    def run_cycle(self, faults) -> dict:
        """Run one dosing cycle. Never raises: failures become error spans."""
        self.cycles += 1
        result = {"corrections": [], "converged": None, "error": None}
        with self.tracer.start_as_current_span("dosing.cycle") as cycle:
            for k, v in self._attrs().items():
                cycle.set_attribute(k, v)
            cycle.set_attribute("cycle.number", self.cycles)
            try:
                ph, ec = self._sense(faults)
                decisions = self._decide(ph, ec)
                result["corrections"] = [
                    {"type": d["correction"], "ml": d["ml"]} for d in decisions
                ]
                cycle.set_attribute(
                    "dosing.corrections",
                    ",".join(d["correction"] for d in decisions) or "none",
                )
                self._actuate(decisions, faults)
                converged = self._verify()
                result["converged"] = converged
                cycle.set_attribute("dosing.converged", converged)
            except Exception as exc:  # noqa: BLE001 -- everything becomes an error span
                cycle.record_exception(exc)
                cycle.set_status(Status(StatusCode.ERROR, str(exc)))
                result["error"] = f"{type(exc).__name__}: {exc}"
                self.logger.error("dosing.cycle failed: %s", result["error"])
        self.last = result
        return result

    # ---- spans ----
    def _sense(self, faults):
        with self.tracer.start_as_current_span("sensor.read") as sp:
            ph = self.twin.read_ph(faults)
            ec = self.twin.read_ec(faults)
            sp.set_attribute("ec.measured", round(ec, 3))
            if ph is None or math.isnan(ph):
                sp.set_attribute("ph.measured", "NaN")
                sp.set_status(Status(StatusCode.ERROR, "pH sensor returned NaN"))
                raise SensorReadError("pH sensor returned NaN")
            sp.set_attribute("ph.measured", round(ph, 3))
            return ph, ec

    def _decide(self, ph: float, ec: float):
        """Return a list of corrections (0-2): pH balancing and/or nutrient top-up."""
        with self.tracer.start_as_current_span("controller.decide") as sp:
            ph_low, ph_high = PH_IDEAL
            decisions = []
            if ph > ph_high:
                decisions.append({
                    "correction": "ph_down",
                    "ml": round(min(20.0, (ph - PH_TARGET) * 25.0), 1),
                    "reason": f"pH {ph:.2f} above {ph_high}",
                })
            elif ph < ph_low:
                decisions.append({
                    "correction": "ph_up",
                    "ml": round(min(20.0, (PH_TARGET - ph) * 25.0), 1),
                    "reason": f"pH {ph:.2f} below {ph_low}",
                })
            if ec < EC_TARGET - 0.2:
                decisions.append({
                    "correction": "nutrient_ab",
                    "ml": round(min(30.0, (EC_TARGET - ec) * 40.0), 1),
                    "reason": f"EC {ec:.2f} below target {EC_TARGET}",
                })
            sp.set_attribute("ph.measured", round(ph, 3))
            sp.set_attribute("ec.measured", round(ec, 3))
            sp.set_attribute("ph.target", PH_TARGET)
            sp.set_attribute("ph.error", round(ph - PH_TARGET, 3))
            sp.set_attribute(
                "corrections", ",".join(d["correction"] for d in decisions) or "none"
            )
            return decisions

    def _actuate(self, decisions, faults):
        for d in decisions:
            is_ph = d["correction"].startswith("ph")
            with self.tracer.start_as_current_span("pump.actuate") as sp:
                sp.set_attribute("pump.id", "ph-pump-1" if is_ph else "nutrient-pump-1")
                sp.set_attribute("correction.type", d["correction"])
                sp.set_attribute("dose.ml", d["ml"])
                sp.set_attribute("duration.ms", 850)
                if "pump_failure" in faults:
                    raise PumpTimeoutError(
                        f"{d['correction']} pump did not acknowledge within 2000ms"
                    )
                if d["ml"] > 0:
                    self.twin.apply_dose(d["correction"], d["ml"])
                    self.logger.info(
                        "dosed %.1f ml (%s): %s", d["ml"], d["correction"], d["reason"]
                    )

    def _verify(self) -> bool:
        with self.tracer.start_as_current_span("sensor.verify") as sp:
            ph_after = self.twin.s.ph
            converged = PH_IDEAL[0] <= ph_after <= PH_IDEAL[1]
            sp.set_attribute("ph.after", round(ph_after, 3))
            sp.set_attribute("converged", converged)
            return converged
