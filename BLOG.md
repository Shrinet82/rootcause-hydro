---
title: "I put a hydroponic farm on an SRE dashboard — and gave a plant an on-call rotation"
published: false
tags: observability, opentelemetry, signoz, iot
cover_image: ""
---

> Built for the **Agents of SigNoz** hackathon (WeMakeDevs × SigNoz), Track 03 — Build Your Own.
> Code: https://github.com/Shrinet82/rootcause-hydro · Live gauges: http://20.120.242.78:8099

## The idea nobody was building

Every other hackathon project pointed observability at software — AI agents, APIs, pipelines.
I wanted to point it at something *alive*: a **hydroponic farm**. Not because farms need
Grafana, but because a hydroponic reservoir turns out to be a near-perfect teaching model for
the exact concepts SREs use every day.

Watch a hydroponic rig long enough and you realise it *is* a distributed system:

| SRE concept | Hydroponic reality |
|---|---|
| Distributed trace | one nutrient-dosing cycle: read → decide → dose → verify |
| Golden signals | pH, EC (nutrient strength), water temp, dissolved oxygen, water level |
| SLO + error budget | "pH stays in 5.5–6.5 for 99% of the day" |
| Incident / SEV | pH lockout, nutrient burn, **pump failure = total outage** |
| Predictive alert | "reservoir will be dry in ~3h at the current drain rate" |

That last insight — **a dosing cycle is a sense → decide → actuate → verify control loop,
which is exactly the shape of a distributed trace** — is the whole project.

## What I built: RootCause

A physics-based **digital twin** of a deep-water-culture rig, instrumented end to end with
**OpenTelemetry** and operated like a production service on **SigNoz**.

One rule I set myself: **the farm is simulated, but the observability is 100% real.** The twin
produces synthetic-but-*causal* data (pH drifts up as plants strip nutrients, EC falls as they
drink, warm water holds less oxygen, the reservoir slowly empties). The telemetry — spans,
metrics, logs, exceptions — is real OpenTelemetry over OTLP into a real SigNoz. No `random()`
noise; you can look at any signal and reason about *why* it moved.

**Stack:** Python + `asyncio`, OpenTelemetry SDK → OTLP → self-hosted SigNoz, FastAPI control
plane, a brutalist HTML dashboard.

## The money-shot: a plant being fed, as a trace

Every dosing cycle emits one trace:

```
dosing.cycle
├── sensor.read        ph.measured=6.42  ec.measured=1.44
├── controller.decide  corrections=ph_down,nutrient_ab
├── pump.actuate       pump.id=ph-pump-1  dose.ml=10.5
├── pump.actuate       pump.id=nutrient-pump-1  dose.ml=6.4
└── sensor.verify      ph.after=6.17  converged=true
```

Open it in SigNoz's flame graph and you see exactly where a feeding spends its time. It's a
screenshot no one expects: **a flame graph of a plant getting fed.**

*(screenshot: dosing.cycle trace waterfall)*

## Then I broke it on purpose

RootCause ships six injectable faults, each perturbing the same physics equations so incidents
look real in SigNoz:

- **`pump_failure`** → `pump.actuate` raises a `PumpTimeoutError`, the cycle becomes a **red
  error trace**, and dissolved oxygen starts sliding. An **exceptions-based alert** fires.
- **`heatwave`** → water temp climbs past 24 °C, oxygen drops — a **threshold alert** trips.
- **`leak`** → the reservoir drains fast. This is my favourite: instead of waiting for an
  empty-tank threshold, a tiny online forecaster projects the drain rate and fires a
  **predictive** *"dry in ~3 h"* alert — a page you can actually act on.

*(screenshot: SigNoz Alerts → Triggered)*

## What SigNoz showed me

- **Traces** turned "the dosing felt off" into "the pump.actuate span errored at 20:14, here's
  the exception." 
- **Dashboards** — and here I made a deliberate choice: **not everything is a line chart.**
  Current vitals are **Value** tiles (green/amber/red), the SLO view is a **Table** scorecard,
  and only genuine trends are time-series. Matching the panel type to the signal is half of
  "good observability UX."
- **Alerts** across three shapes (threshold, exception, predictive) — the predictive one is
  the difference between monitoring and *operating*.

*(screenshot: Grow Room Overview — value tiles + trends)*

## The one thing SigNoz couldn't do — so I built it

For a farm wall-display you want **radial gauges**, and SigNoz (rightly, it's an engineering
tool) has no gauge panel. So I built a bespoke **Grow Room Mission Control** page — a
brutalist, light-theme operator screen with real SVG gauges, a reservoir tank, a scrolling
ticker, a vitals-aware incident banner, and **fault-injection buttons**. SigNoz stays the
observability backend; this is the glance-screen on top of it.

It's self-contained (the twin runs in-process), so it deploys anywhere with no SigNoz —
**http://20.120.242.78:8099** — and judges can click the fault buttons themselves.

*(screenshot: brutalist Mission Control, all green)*

## What I learned

- **Observability is a modelling exercise before it's a tooling exercise.** The hard part
  wasn't the SDK; it was deciding what a "span" and an "SLO" *mean* for a plant. Once the
  mental model was right, the instrumentation was easy.
- **Causal fakes beat random fakes.** A physics-informed twin makes every dashboard defensible
  and every fault demo believable.
- **Panel type is a UX decision.** A wall of identical line charts hides the story; value tiles
  + a table + a few trends tell it.

## Try it

```bash
git clone https://github.com/Shrinet82/rootcause-hydro && cd rootcause-hydro
pip install -r requirements.txt
PYTHONPATH=. ROOTCAUSE_CONSOLE=1 ROOTCAUSE_DISABLE_OTLP=1 python3 scripts/smoke_test.py  # no SigNoz needed
python -m rootcause.run   # point OTEL_EXPORTER_OTLP_ENDPOINT at your SigNoz, open :8099
```

If you can't observe it, you don't own it — even if it's lettuce. 🌱

*Built July 2026 for Agents of SigNoz. The farm is simulated from a physics model; the traces,
metrics, logs, and detection are real.*
