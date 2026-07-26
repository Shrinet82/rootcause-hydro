"""The nutrient-dosing control loop -- rendered as a distributed trace.

Every cycle is one trace:

    dosing.cycle
    |-- sensor.read       (measure pH / EC)
    |-- controller.decide (compute correction)
    |-- pump.actuate      (dose -- can raise PumpTimeoutError)
    `-- sensor.verify     (re-measure, did it converge?)

A dosing cycle is literally a sense -> decide -> actuate -> verify control
loop, which is exactly the shape of a distributed trace. That mapping is the
core idea of the whole project.
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

    def _attrs(self):
        return {"zone": self.twin.zone, "crop": self.twin.crop, "stage": self.twin.stage}

    def run_cycle(self, faults) -> dict:
        """Run one dosing cycle. Never raises: failures become error spans."""
        self.cycles += 1
        result = {"correction": "none", "ml": 0.0, "converged": None, "error": None}
        with self.tracer.start_as_current_span("dosing.cycle") as cycle:
            for k, v in self._attrs().items():
                cycle.set_attribute(k, v)
            cycle.set_attribute("cycle.number", self.cycles)
            try:
                ph, ec = self._sense(faults)
                decision = self._decide(ph, ec)
                result.update(decision)
                self._actuate(decision, faults)
                converged = self._verify()
                result["converged"] = converged
                cycle.set_attribute("dosing.converged", converged)
            except Exception as exc:  # noqa: BLE001 -- we want everything as an error span
                cycle.record_exception(exc)
                cycle.set_status(Status(StatusCode.ERROR, str(exc)))
                result["error"] = f"{type(exc).__name__}: {exc}"
                self.logger.error("dosing.cycle failed: %s", result["error"])
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
        with self.tracer.start_as_current_span("controller.decide") as sp:
            ph_low, ph_high = PH_IDEAL
            correction, ml, reason = "none", 0.0, "all within band"
            if ph > ph_high:
                correction = "ph_down"
                ml = round(min(20.0, (ph - PH_TARGET) * 25.0), 1)
                reason = f"pH {ph:.2f} above {ph_high}"
            elif ph < ph_low:
                correction = "ph_up"
                ml = round(min(20.0, (PH_TARGET - ph) * 25.0), 1)
                reason = f"pH {ph:.2f} below {ph_low}"
            elif ec < EC_TARGET - 0.2:
                correction = "nutrient_ab"
                ml = round(min(30.0, (EC_TARGET - ec) * 40.0), 1)
                reason = f"EC {ec:.2f} below target {EC_TARGET}"
            sp.set_attribute("ph.target", PH_TARGET)
            sp.set_attribute("ph.error", round(ph - PH_TARGET, 3))
            sp.set_attribute("correction.type", correction)
            sp.set_attribute("correction.ml", ml)
            sp.set_attribute("decision.reason", reason)
            return {"correction": correction, "ml": ml, "reason": reason}

    def _actuate(self, decision, faults):
        with self.tracer.start_as_current_span("pump.actuate") as sp:
            sp.set_attribute("pump.id", "dosing-pump-1")
            sp.set_attribute("dose.ml", decision["ml"])
            sp.set_attribute("duration.ms", 850)
            if "pump_failure" in faults:
                raise PumpTimeoutError("dosing-pump-1 did not acknowledge within 2000ms")
            if decision["correction"] != "none" and decision["ml"] > 0:
                self.twin.apply_dose(decision["correction"], decision["ml"])
                self.logger.info(
                    "dosed %.1f ml (%s): %s",
                    decision["ml"], decision["correction"], decision["reason"],
                )

    def _verify(self) -> bool:
        with self.tracer.start_as_current_span("sensor.verify") as sp:
            ph_after = self.twin.s.ph
            converged = PH_IDEAL[0] <= ph_after <= PH_IDEAL[1]
            sp.set_attribute("ph.after", round(ph_after, 3))
            sp.set_attribute("converged", converged)
            return converged
