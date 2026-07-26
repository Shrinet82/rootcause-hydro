# RootCause — 2-minute demo script

Goal: take the judge from "it's a dashboard" to "oh, it *pages you before the plants die*."
Keep SigNoz open in one window, a terminal in the other.

**Before you record:** `python -m rootcause.run` has been up for a few minutes so the
dashboards have history. Have the "Grow Room Overview" dashboard open.

---

### 0:00 — The hook (15s)
> "This is a hydroponic farm. But I'm not running it like a garden — I'm running it like a
> production service. Every vital sign is a metric, every feeding is a distributed trace,
> and plant health is an SLO with an error budget."

Show the **Grow Room Overview** dashboard: pH, EC, water temp, dissolved oxygen, water
level — all live, all in their healthy bands.

### 0:15 — The trace money-shot (25s)
Open **Traces** → a `dosing.cycle`. Expand the waterfall:
`sensor.read → controller.decide → pump.actuate → sensor.verify`.
> "This is one feeding cycle. The controller measured pH 6.5, decided to dose 12 ml of
> pH-down, actuated the pump, and verified it converged — as a distributed trace. Nobody
> has a flame graph of a plant being fed."

### 0:40 — Inject an incident (30s)
```bash
python -m rootcause.cli inject pump_failure
```
> "Now the circulation pump dies — the kind of silent failure that kills a crop overnight."

In SigNoz: the next `dosing.cycle` turns **red** — an **error trace** with a recorded
`PumpTimeoutError`. Dissolved oxygen starts sliding.

### 1:10 — The alert pages (20s)
Show the firing alert (Dissolved O₂ low / Pump actuation failure).
> "The exception-based alert fires on the pump timeout, and the O₂ alert catches the
> downstream effect. I'd get paged now — hours before I'd ever notice wilting."

### 1:30 — The predictive save (20s)
```bash
python -m rootcause.cli clear
python -m rootcause.cli inject leak
```
> "Different failure: a slow leak. The reservoir isn't empty yet — but RootCause forecasts
> the drain rate and tells me it'll be **dry in under three hours**. That's a page I can act
> on *before* it's an outage."

Show `hydro.reservoir.hours_to_empty` dropping and the predictive alert.

### 1:50 — Close (10s)
```bash
python -m rootcause.cli clear
```
> "Simulated farm, real observability — real OpenTelemetry, real SigNoz. If you can't
> observe it, you don't own it. Even if it's lettuce."

---

**Optional wow (if MCP is wired):** ask the SigNoz MCP server in plain English
*"what caused the oxygen drop at 14:00?"* and let it answer from the telemetry.
