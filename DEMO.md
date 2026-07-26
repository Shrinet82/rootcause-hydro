# RootCause — 2-minute demo script

Goal: take a judge from "it's a dashboard" to "oh, it **pages you before the plants die**."
The arc is a real incident: healthy → failure → alert → predictive save → recovery.

## Record it on Ubuntu
- **Screen capture:** OBS Studio (`sudo apt install obs-studio`) or SimpleScreenRecorder. 1080p, 30fps.
- **Quick GIFs:** Peek (`flatpak install flathub com.uploadedlobster.peek`).
- **Edit / captions:** Kdenlive (`sudo apt install kdenlive`).
- **Voiceover:** record live, or narrate in Audacity and lay it over in Kdenlive.

## Layout before you hit record
Two windows side by side (or two tabs you alt-tab between):
- **Left:** Mission Control — http://20.120.242.78:8099/ (or `localhost:8099`).
- **Right:** SigNoz — http://20.120.242.78:8080/ , with the **Traces** view and the
  **Grow Room Overview** dashboard pre-opened in tabs.
- Let it run a few minutes first so charts have history. Set `ROOTCAUSE_DOSE_EVERY_TICKS=2`
  for snappier dosing during the recording.

---

### 0:00–0:15 · Hook
**On screen:** Mission Control, all gauges green, banner "ALL SYSTEMS NOMINAL", ticker scrolling.
**Caption:** *RootCause — observability for a living system.*
**Voiceover:**
> "This is a hydroponic farm — but I'm running it like a production service. Every vital sign
> is a metric, every feeding is a distributed trace, and plant health is an SLO with an error
> budget. If you can't observe it, you don't own it — even if it's lettuce."

### 0:15–0:40 · The money-shot (a plant being fed, as a trace)
**On screen:** SigNoz → Traces → open a `dosing.cycle`. Expand the waterfall.
**Caption:** *One feeding = one distributed trace.*
**Voiceover:**
> "Here's one nutrient-dosing cycle as a trace: the controller read pH 6.4, decided to dose
> pH-down and nutrients, actuated the pumps, and verified it converged — `sensor.read →
> controller.decide → pump.actuate → sensor.verify`. Nobody has a flame graph of a plant
> being fed."

### 0:40–1:10 · Inject an incident
**On screen:** Mission Control → click **PUMP FAILURE**. Banner flips red "ACTIVE INCIDENT".
Cut to SigNoz Traces.
**Caption:** *Circulation pump dies — the silent killer.*
**Voiceover:**
> "Now the circulation pump fails — the kind of silent failure that kills a crop overnight.
> The next dosing cycle turns into a **red error trace** with a recorded `PumpTimeoutError`,
> and dissolved oxygen starts sliding."

### 1:10–1:30 · The alert pages
**On screen:** SigNoz → Alerts → Triggered. Show "Pump actuation failure" / "Dissolved O₂ low"
firing.
**Caption:** *Exception-based + threshold alerts fire.*
**Voiceover:**
> "The exceptions alert fires on the pump timeout, and the oxygen alert catches the downstream
> effect. I'd get paged right now — hours before I'd ever notice wilting."

### 1:30–1:50 · The predictive save
**On screen:** Mission Control → **CLEAR ALL**, then click **LEAK**. Point at the
"Hours to Empty" gauge dropping; cut to the "Reservoir dry soon" alert.
**Caption:** *Forecast, not just threshold.*
**Voiceover:**
> "Different failure — a slow leak. The reservoir isn't empty yet, but RootCause forecasts the
> drain rate and says it'll be **dry in under three hours**. That's a page I can act on *before*
> it's an outage."

### 1:50–2:00 · Recover & close
**On screen:** Mission Control → **CLEAR ALL**. Gauges return to green, banner back to NOMINAL.
**Caption:** *Simulated farm · real OpenTelemetry · SigNoz.*
**Voiceover:**
> "Clear the faults, and the farm heals. Simulated farm, real observability — OpenTelemetry
> into SigNoz, end to end. That's RootCause."

---

### Optional flourish (if MCP is wired)
Ask the SigNoz MCP server in plain English — *"what caused the oxygen drop at 20:14?"* — and
let it answer from the telemetry on camera. Big "Best Use of SigNoz" moment.

### Screenshots to capture for the README / submission
1. Mission Control, all green (hero).
2. A `dosing.cycle` trace waterfall.
3. A red error trace under `pump_failure`.
4. SigNoz Alerts → Triggered (a firing alert).
5. Grow Room Overview dashboard (value tiles + trends).
