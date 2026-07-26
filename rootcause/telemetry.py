"""OpenTelemetry wiring: traces, metrics and logs, all from one place.

Consolidating provider setup here (and importing it exactly once at startup)
avoids the classic "my span showed up as a sibling instead of a child"
bug that comes from initialising tracing in more than one module.
"""
from __future__ import annotations

import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.metrics import Observation
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from .config import Settings
from .constants import METRICS

_MISSING = (
    "OTLP exporter not installed. Run `pip install -r requirements.txt`, "
    "or set ROOTCAUSE_DISABLE_OTLP=1 to run offline."
)


def _otlp_exporters(settings: Settings):
    """Import the OTLP exporters lazily so offline/smoke runs need no gRPC."""
    if settings.otlp_protocol.startswith("http"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    ep = settings.otlp_endpoint
    return (
        OTLPSpanExporter(endpoint=ep),
        OTLPMetricExporter(endpoint=ep),
        OTLPLogExporter(endpoint=ep),
    )


class Telemetry:
    """Holds the providers so we can flush/shut them down cleanly."""

    def __init__(self, tracer, meter, logger, providers):
        self.tracer = tracer
        self.meter = meter
        self.logger = logger
        self._providers = providers

    def flush(self):
        for p in self._providers:
            try:
                p.force_flush()
            except Exception:
                pass

    def shutdown(self):
        for p in self._providers:
            try:
                p.shutdown()
            except Exception:
                pass


def setup_telemetry(settings: Settings) -> Telemetry:
    resource = Resource.create(settings.resource_attributes())

    span_exp = metric_exp = log_exp = None
    if not settings.disable_otlp:
        try:
            span_exp, metric_exp, log_exp = _otlp_exporters(settings)
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(_MISSING) from exc

    # --- Traces ---
    tp = TracerProvider(resource=resource)
    if span_exp is not None:
        tp.add_span_processor(BatchSpanProcessor(span_exp))
    if settings.console_export:
        tp.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tp)

    # --- Metrics ---
    readers = []
    if metric_exp is not None:
        readers.append(
            PeriodicExportingMetricReader(
                metric_exp, export_interval_millis=settings.metric_export_interval_ms
            )
        )
    if settings.console_export:
        readers.append(
            PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=settings.metric_export_interval_ms,
            )
        )
    mp = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(mp)

    # --- Logs ---
    lp = LoggerProvider(resource=resource)
    if log_exp is not None:
        lp.add_log_record_processor(BatchLogRecordProcessor(log_exp))
    if settings.console_export:
        lp.add_log_record_processor(SimpleLogRecordProcessor(ConsoleLogExporter()))
    set_logger_provider(lp)

    app_logger = logging.getLogger("rootcause")
    app_logger.setLevel(logging.INFO)
    app_logger.handlers.clear()
    app_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=lp))
    app_logger.propagate = False

    tracer = trace.get_tracer("rootcause")
    meter = metrics.get_meter("rootcause")
    return Telemetry(tracer, meter, app_logger, [tp, mp, lp])


class MetricSet:
    """Continuously-sampled gauges for every sensor reading.

    Uses the synchronous Gauge API when available and transparently falls
    back to observable gauges on older SDKs, so the same `.set()` call works
    either way.
    """

    def __init__(self, meter):
        self._latest = {}
        self._sync = hasattr(meter, "create_gauge")
        self._gauges = {}
        for name, unit in METRICS:
            if self._sync:
                self._gauges[name] = meter.create_gauge(name, unit=unit)
            else:
                meter.create_observable_gauge(
                    name, callbacks=[self._callback(name)], unit=unit
                )

    def _callback(self, name):
        def cb(_options):
            item = self._latest.get(name)
            return [Observation(item[0], item[1])] if item else []
        return cb

    def set(self, name: str, value, attributes: dict):
        if value is None:
            return
        try:
            if value != value:  # NaN guard
                return
        except Exception:
            return
        if self._sync:
            self._gauges[name].set(value, attributes)
        else:
            self._latest[name] = (value, attributes)
