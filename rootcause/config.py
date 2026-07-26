"""Runtime settings, all overridable via environment variables.

Nothing secret is ever hard-coded; the SigNoz API key is read from the
environment only when the apply script needs it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # --- OpenTelemetry export ---
    otlp_endpoint: str = "http://localhost:4317"
    otlp_protocol: str = "grpc"          # "grpc" (4317) or "http" (4318)
    service_name: str = "rootcause-hydro"
    service_version: str = "0.1.0"
    environment: str = "hackathon"
    console_export: bool = False         # also print telemetry to stdout
    disable_otlp: bool = False           # skip OTLP entirely (offline/smoke test)
    metric_export_interval_ms: int = 10000

    # --- simulation ---
    sim_tick_seconds: float = 5.0        # wall-clock seconds per tick
    sim_minutes_per_tick: float = 10.0   # simulated minutes advanced per tick
    dose_every_ticks: int = 6            # run a dosing cycle every N ticks (~hourly)
    zone: str = "zone-a"
    crop: str = "lettuce"
    stage: str = "veg"                   # seedling | veg | flower
    photoperiod_hours: float = 18.0
    seed: int = 42

    # --- control plane ---
    api_host: str = "0.0.0.0"
    api_port: int = 8099

    # --- SigNoz (for the apply script) ---
    signoz_url: str = "http://localhost:8080"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", cls.otlp_endpoint),
            otlp_protocol=os.getenv("ROOTCAUSE_OTLP_PROTOCOL", cls.otlp_protocol),
            service_name=os.getenv("OTEL_SERVICE_NAME", cls.service_name),
            environment=os.getenv("ROOTCAUSE_ENV", cls.environment),
            console_export=_b("ROOTCAUSE_CONSOLE", cls.console_export),
            disable_otlp=_b("ROOTCAUSE_DISABLE_OTLP", cls.disable_otlp),
            metric_export_interval_ms=int(
                os.getenv("ROOTCAUSE_METRIC_INTERVAL_MS", cls.metric_export_interval_ms)
            ),
            sim_tick_seconds=float(os.getenv("ROOTCAUSE_TICK_SECONDS", cls.sim_tick_seconds)),
            sim_minutes_per_tick=float(
                os.getenv("ROOTCAUSE_MINUTES_PER_TICK", cls.sim_minutes_per_tick)
            ),
            dose_every_ticks=int(os.getenv("ROOTCAUSE_DOSE_EVERY_TICKS", cls.dose_every_ticks)),
            zone=os.getenv("ROOTCAUSE_ZONE", cls.zone),
            crop=os.getenv("ROOTCAUSE_CROP", cls.crop),
            stage=os.getenv("ROOTCAUSE_STAGE", cls.stage),
            photoperiod_hours=float(os.getenv("ROOTCAUSE_PHOTOPERIOD", cls.photoperiod_hours)),
            seed=int(os.getenv("ROOTCAUSE_SEED", cls.seed)),
            api_host=os.getenv("ROOTCAUSE_HOST", cls.api_host),
            api_port=int(os.getenv("ROOTCAUSE_PORT", cls.api_port)),
            signoz_url=os.getenv("SIGNOZ_URL", cls.signoz_url),
        )

    def resource_attributes(self) -> dict:
        return {
            "service.name": self.service_name,
            "service.version": self.service_version,
            "deployment.environment": self.environment,
        }
