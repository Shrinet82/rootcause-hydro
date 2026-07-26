# 🌱 RootCause — Mission Control for a Hydroponic Farm

**Observability for a living system.** RootCause runs a physics-based digital twin of a
hydroponic grow rig and operates it like a **production service** on
[SigNoz](https://signoz.io): golden-signal metrics, a nutrient-dosing control loop
rendered as **distributed traces**, trace-correlated logs, exceptions, plant-health
**SLOs**, and alerts that **page you before your plants die**.

> Built for the **Agents of SigNoz** hackathon — **Track 03: Build Your Own**.

---

## Why this is different

Most observability demos watch software. RootCause watches a **living, physical system** —
and it turns out a hydroponic reservoir maps almost perfectly onto the concepts SREs use
every day:

| SRE concept | Hydroponic reality |
|---|---|
| **Distributed trace** | One nutrient-dosing cycle: `sensor.read → controller.decide → pump.actuate → sensor.verify` |
| **Golden signals** | pH, EC (nutrient strength), water temp, dissolved oxygen, water level |
| **SLO + error budget** | "pH stays in 5.5–6.5 for 99% of the day" |
| **Incident / SEV** | pH lockout, nutrient burn, **pump failure = total outage** |
| **Exception** | Dosing pump timeout, sensor returning `NaN` |
| **Predictive alert** | "Reservoir will be **dry in ~3h** at the current drain rate" |

A dosing cycle *is* a sense → decide → actuate → verify control loop — which is exactly the
shape of a distributed trace. That mapping is the whole idea.

## What's real vs. simulated (read this)

- **Simulated:** the *farm*. A physics-informed twin ([`twin.py`](rootcause/twin.py)) models
  diurnal light/temperature cycles, nutrient uptake (EC falls as plants drink), pH drift,
  oxygen solubility vs. temperature, and reservoir drain. The data is **synthetic but
  causal** — you can look at any signal and reason about *why* it moved. No `random()` spam.
- **100% real:** the *observability*. Real OpenTelemetry SDK, real OTLP export, real spans /
  metrics / logs / exceptions, real SigNoz dashboards and alerts.

Bring one cheap sensor (a $2 DHT22) and you can stream one **real** signal alongside the
twin — the pipeline doesn't care where the numbers come from.

## Architecture

```
                 ┌─────────────────────────────┐
   POST /fault/* │      RootCause (FastAPI)     │
  ───────────────▶  ┌────────┐   ┌────────────┐ │
   POST /clear   │  │ digital │──▶│  dosing    │ │   OpenTelemetry (OTLP)
   GET  /status  │  │  twin   │   │  control   │ │──────────────┐
                 │  └────────┘   │  loop      │ │              │
                 │      │        └────────────┘ │              ▼
                 │      │  metrics/traces/logs   │        ┌───────────┐
                 │      ▼                        │        │  SigNoz   │
                 │  OTel providers (telemetry.py)│        │ dashboards│
                 └─────────────────────────────┘         │  + alerts │
                                                          └───────────┘
```

## Quickstart

```bash
git clone <this-repo> && cd rootcause-hydro
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set OTEL_EXPORTER_OTLP_ENDPOINT to your SigNoz
python -m rootcause.run       # streams telemetry + serves the control API on :8099
```

Within a minute you'll see the `rootcause-hydro` service in SigNoz with metrics flowing and
`dosing.cycle` traces appearing. Then create the dashboards and drive a demo:

```bash
# create dashboards in SigNoz (or import signoz/dashboards/*.json from the UI)
export SIGNOZ_API_KEY=<key from SigNoz → Settings → API Keys>
python signoz/apply_signoz.py --create

# inject faults live during your demo
python -m rootcause.cli status
python -m rootcause.cli inject heatwave
python -m rootcause.cli clear
```

## SigNoz setup

**Metrics emitted** (all tagged `zone`, `crop`, `stage`):

`hydro.ph` · `hydro.ec` · `hydro.tds` · `hydro.water_temp` · `hydro.air_temp` ·
`hydro.humidity` · `hydro.dissolved_oxygen` · `hydro.water_level` ·
`hydro.reservoir_volume` · `hydro.light_ppfd` · `hydro.co2` · `hydro.pump_flow` ·
`hydro.reservoir.hours_to_empty`

**Dashboards** (`signoz/dashboards/`, import from the UI or via `--create`) — panel types
are matched to each signal, not one-chart-fits-all:
- **Grow Room Overview** — current vitals as **Value** tiles (threshold-coloured
  green/amber/red) + pH/EC **trend** lines.
- **Reservoir & Dosing** — reservoir/pump **Value** tiles + nutrient & pump **trends**.
- **Plant-Health SLO** — a **Table** scorecard (metric · current · target) + SLO trend lines.

> Colours come from per-panel thresholds. If your SigNoz version rejects the threshold
> block on import, regenerate without it:
> `python signoz/apply_signoz.py --write-json --no-thresholds`.

**Alerts** (`python signoz/apply_signoz.py` prints the full list):

| Alert | Rule | Sev |
|---|---|---|
| pH out of band | `hydro.ph` > 6.5 or < 5.5 | warning |
| Water temp critical | `hydro.water_temp` > 24 | critical |
| Dissolved O₂ low | `hydro.dissolved_oxygen` < 5 | critical |
| Nutrient burn / deficiency | `hydro.ec` > 2.4 or < 1.2 | warning |
| **Reservoir dry soon** | `hydro.reservoir.hours_to_empty` < 3 | critical (predictive) |
| Pump actuation failure | Exceptions alert on `PumpTimeoutError` | critical |
| Abnormal drain / drift | Anomaly alert on `hydro.ec` | warning |

> Dashboard JSON follows SigNoz's builder-query format; if a field is rejected by your
> SigNoz version, import the JSON from the UI or add panels by hand using the metric names
> above. The engine and metric names are the stable part.

## Fault injection → what the judges see

| Fault | Physical effect | Shows up in SigNoz as |
|---|---|---|
| `heatwave` | water temp ↑ → O₂ ↓ | temp breaches SLO, DO-low alert |
| `pump_failure` | no circulation | **error traces** on `pump.actuate` (PumpTimeoutError) |
| `ph_drift` | pH climbs ~4× | dosing loop fights back (or overshoots) |
| `leak` | reservoir drains fast | **"dry in ~Xh"** predictive alert |
| `nutrient_burn` | EC climbs | EC-high alert |
| `sensor_glitch` | pH reads `NaN` | error span on `sensor.read` + data-quality log |

## The 2-minute demo

See **[DEMO.md](DEMO.md)** for the full script: baseline → inject a fault → watch the alert
page → (optional) let the SRE-copilot recommend the fix → recovery.

## Verify it offline (no SigNoz needed)

```bash
PYTHONPATH=. ROOTCAUSE_CONSOLE=1 ROOTCAUSE_DISABLE_OTLP=1 python3 scripts/smoke_test.py
```

Runs the twin for a simulated day, fires a healthy dosing cycle and a pump-failure one
(prints the nested trace + the recorded exception to your console), injects a leak, and
asserts the physics behaves. Ends with `SMOKE TEST PASSED`.

## Project layout

```
rootcause/
  twin.py         # physics-informed digital twin (the "farm")
  telemetry.py    # OpenTelemetry: traces + metrics + logs, one place
  dosing.py       # control loop rendered as dosing.cycle traces
  faults.py       # injectable fault scenarios (shared source of truth)
  forecast.py     # online reservoir drain forecaster (predictive alert)
  app.py          # FastAPI control plane + background sim loop
  run.py / cli.py # entrypoint + demo CLI
signoz/
  apply_signoz.py # generate/create dashboards; print alert specs
  dashboards/*.json
scripts/smoke_test.py
```

## Roadmap

- Multi-zone farm (per-zone SLOs, cross-zone correlation)
- Real sensor bridge (DHT22 / Atlas pH probe over serial/MQTT)
- SRE-copilot: read SigNoz via the **MCP server**, diagnose the active fault, recommend or
  auto-apply the corrective dose (human-in-the-loop) — reuses the `detect → diagnose → act`
  pattern from the author's Track 1 project
- Swap the linear drain forecaster for Holt-Winters / Prophet

## How it maps to the judging criteria

- **Potential Impact** — crop loss is money; vertical farming is a real, growing domain.
- **Creativity** — observability on a *living* system; a dosing loop as a distributed trace.
- **Technical Excellence** — causal digital twin, clean OTel semantic conventions, SLOs.
- **Best Use of SigNoz** — traces **and** metrics **and** logs **and** exceptions **and**
  dashboards **and** four alert types (threshold, exception, anomaly, predictive).
- **User Experience** — a control plane + dashboards a grower would actually watch.
- **Presentation** — a fault-injection demo arc with a memorable money-shot.

## License

MIT — see [LICENSE](LICENSE).
