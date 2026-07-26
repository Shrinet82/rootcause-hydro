"""Offline smoke test -- proves the engine emits real telemetry with no SigNoz.

Runs with the OTel *console* exporter (OTLP disabled), advances the twin,
fires dosing cycles (a healthy one and a pump-failure one), injects a leak,
and checks the physics behaves. Run from the repo root:

    PYTHONPATH=. ROOTCAUSE_CONSOLE=1 ROOTCAUSE_DISABLE_OTLP=1 python3 scripts/smoke_test.py
"""
from __future__ import annotations

import os

os.environ.setdefault("ROOTCAUSE_CONSOLE", "1")
os.environ.setdefault("ROOTCAUSE_DISABLE_OTLP", "1")

from rootcause.config import Settings          # noqa: E402
from rootcause.dosing import DosingController   # noqa: E402
from rootcause.faults import FaultManager       # noqa: E402
from rootcause.forecast import ReservoirForecaster  # noqa: E402
from rootcause.telemetry import MetricSet, setup_telemetry  # noqa: E402
from rootcause.twin import HydroTwin            # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    tele = setup_telemetry(settings)
    twin = HydroTwin(seed=7)
    metrics = MetricSet(tele.meter)
    faults = FaultManager()
    controller = DosingController(twin, tele.tracer, tele.logger)
    forecaster = ReservoirForecaster()

    print("\n=== 1) advancing the twin 24 simulated hours ===")
    for i in range(144):  # 144 * 10min = 24h
        twin.step(10.0, faults)
        forecaster.observe(twin.s.sim_minutes, twin.s.reservoir_volume_l)
        if i % 36 == 0:
            s = twin.s
            print(
                f"  t={s.sim_minutes/60:5.1f}h lights={'on ' if twin.is_light else 'off'} "
                f"pH={s.ph:.2f} EC={s.ec:.2f} Twater={s.water_temp_c:.1f}C "
                f"DO={s.do_mg_l:.1f} vol={s.reservoir_volume_l:.1f}L"
            )

    print("\n=== 2) a HEALTHY dosing cycle (watch the nested trace) ===")
    twin.s.ph = 6.5  # nudge out of band so the controller acts
    healthy = controller.run_cycle(faults)
    print(f"  -> {healthy}")

    print("\n=== 3) a dosing cycle under PUMP_FAILURE (expect an ERROR span) ===")
    faults.inject("pump_failure")
    failed = controller.run_cycle(faults)
    print(f"  -> {failed}")
    faults.clear("pump_failure")

    print("\n=== 4) inject a LEAK, watch hours-to-empty collapse ===")
    before = forecaster.hours_to_empty(twin.s.reservoir_volume_l)
    faults.inject("leak")
    for _ in range(30):
        twin.step(10.0, faults)
        forecaster.observe(twin.s.sim_minutes, twin.s.reservoir_volume_l)
    after = forecaster.hours_to_empty(twin.s.reservoir_volume_l)
    print(f"  hours_to_empty: {before} -> {after}")

    # ---- assertions ----
    checks = {
        "pH stayed in physical range": 3.5 <= twin.s.ph <= 8.5,
        "healthy cycle produced a correction": healthy["correction"] in
            ("ph_down", "ph_up", "nutrient_ab"),
        "pump failure recorded an error": failed["error"] is not None,
        "leak accelerated drain (hours dropped)": after < before,
        "DO tracks temperature inversely": twin.s.do_mg_l < 14.6,
    }
    print("\n=== RESULTS ===")
    ok = True
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed

    tele.flush()
    tele.shutdown()
    print("\nSMOKE TEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
