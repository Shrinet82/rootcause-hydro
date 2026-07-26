"""FastAPI control plane + the background simulation loop.

Start it with `python -m rootcause.run`. It streams telemetry to SigNoz
continuously and exposes endpoints to inject faults live during a demo.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .config import Settings
from .constants import RESERVOIR_HOURS_CRITICAL, WATER_LEVEL_MIN_PCT
from .dosing import DosingController
from .faults import KNOWN_FAULTS, FaultManager, UnknownFault
from .forecast import ReservoirForecaster
from .telemetry import MetricSet, setup_telemetry
from .twin import HydroTwin


@dataclass
class Runtime:
    settings: Settings
    telemetry: object
    twin: HydroTwin
    metrics: MetricSet
    faults: FaultManager
    controller: DosingController
    forecaster: ReservoirForecaster
    tick: int = 0


def _record_all(rt: Runtime, hours_to_empty: float) -> None:
    s = rt.twin.s
    attrs = {"zone": rt.twin.zone, "crop": rt.twin.crop, "stage": rt.twin.stage}
    m = rt.metrics.set
    m("hydro.ph", s.ph, attrs)
    m("hydro.ec", s.ec, attrs)
    m("hydro.tds", s.tds, attrs)
    m("hydro.water_temp", s.water_temp_c, attrs)
    m("hydro.air_temp", s.air_temp_c, attrs)
    m("hydro.humidity", s.humidity_pct, attrs)
    m("hydro.dissolved_oxygen", s.do_mg_l, attrs)
    m("hydro.water_level", s.water_level_pct, attrs)
    m("hydro.reservoir_volume", s.reservoir_volume_l, attrs)
    m("hydro.light_ppfd", s.light_ppfd, attrs)
    m("hydro.co2", s.co2_ppm, attrs)
    m("hydro.pump_flow", s.pump_flow_l_min, attrs)
    m("hydro.reservoir.hours_to_empty", hours_to_empty, attrs)


async def _sim_loop(rt: Runtime) -> None:
    st = rt.settings
    log = rt.telemetry.logger
    log.info(
        "simulation started: crop=%s stage=%s tick=%.1fs (%.0f sim-min/tick)",
        st.crop, st.stage, st.sim_tick_seconds, st.sim_minutes_per_tick,
    )
    while True:
        try:
            rt.twin.step(st.sim_minutes_per_tick, rt.faults)
            rt.forecaster.observe(rt.twin.s.sim_minutes, rt.twin.s.reservoir_volume_l)
            hte = rt.forecaster.hours_to_empty(rt.twin.s.reservoir_volume_l)
            _record_all(rt, hte)

            if rt.tick % st.dose_every_ticks == 0:
                rt.controller.run_cycle(rt.faults)

            # auto top-up when low, unless a leak is the (unresolved) cause
            if rt.twin.s.water_level_pct < WATER_LEVEL_MIN_PCT and "leak" not in rt.faults:
                rt.twin.top_up(60.0)
                log.info("reservoir topped up (+60 L)")

            rt.tick += 1
        except Exception:  # keep the loop alive no matter what
            log.exception("sim loop tick failed")
        await asyncio.sleep(st.sim_tick_seconds)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    telemetry = setup_telemetry(settings)
    twin = HydroTwin(
        zone=settings.zone, crop=settings.crop, stage=settings.stage,
        photoperiod_hours=settings.photoperiod_hours, seed=settings.seed,
    )
    rt = Runtime(
        settings=settings,
        telemetry=telemetry,
        twin=twin,
        metrics=MetricSet(telemetry.meter),
        faults=FaultManager(),
        controller=DosingController(twin, telemetry.tracer, telemetry.logger),
        forecaster=ReservoirForecaster(),
    )
    app.state.rt = rt
    task = asyncio.create_task(_sim_loop(rt))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        telemetry.flush()
        telemetry.shutdown()


_DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")

app = FastAPI(title="RootCause -- Hydroponic Mission Control", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index():
    """The bespoke Grow Room Mission Control operator screen (live gauges)."""
    return _DASHBOARD_HTML


@app.get("/status")
def status():
    rt: Runtime = app.state.rt
    return {
        "tick": rt.tick,
        "zone": rt.twin.zone,
        "dosing": rt.controller.last,
        "sim_minutes": round(rt.twin.s.sim_minutes, 1),
        "hour_of_day": round(rt.twin.hour_of_day, 2),
        "lights": "on" if rt.twin.is_light else "off",
        "active_faults": sorted(rt.faults.active()),
        "hours_to_empty": rt.forecaster.hours_to_empty(rt.twin.s.reservoir_volume_l),
        "reservoir_critical": (
            rt.forecaster.hours_to_empty(rt.twin.s.reservoir_volume_l)
            < RESERVOIR_HOURS_CRITICAL
        ),
        "state": rt.twin.s.as_dict(),
    }


@app.post("/fault/{name}")
def inject_fault(name: str):
    rt: Runtime = app.state.rt
    try:
        rt.faults.inject(name)
    except UnknownFault as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    rt.telemetry.logger.warning("FAULT INJECTED: %s", name)
    return {"injected": name, "active_faults": sorted(rt.faults.active())}


@app.post("/clear")
def clear_faults():
    rt: Runtime = app.state.rt
    rt.faults.clear()
    rt.telemetry.logger.info("all faults cleared")
    return {"active_faults": sorted(rt.faults.active())}
