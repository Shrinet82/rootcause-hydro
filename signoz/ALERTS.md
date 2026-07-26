# Firing the RootCause alerts in SigNoz

Create these in **SigNoz → Alerts → New Alert**. Each one is paired with the fault that
triggers it (use the Mission Control buttons at `localhost:8099`, or `python -m
rootcause.cli inject <fault>`). Set a short **evaluation window (5 min)** and **"for" = at
least once / 1 min** so they fire quickly during a demo.

| # | Alert | Type | Rule | Fire it with |
|---|---|---|---|---|
| 1 | **Water temp critical** | Metric | `hydro.water_temp` **above 24** | `heatwave` |
| 2 | **Dissolved O₂ low** | Metric | `hydro.dissolved_oxygen` **below 5** | `heatwave` or `pump_failure` |
| 3 | **Reservoir dry soon** (predictive) | Metric | `hydro.reservoir.hours_to_empty` **below 3** | `leak` |
| 4 | **Pump actuation failure** | Exceptions | `PumpTimeoutError` count **> 0** | `pump_failure` |
| 5 | pH out of band | Metric | `hydro.ph` **above 6.5** | `ph_drift` |
| 6 | Nutrient burn / starve | Metric | `hydro.ec` **above 2.4** / **below 1.2** | `nutrient_burn` |

## Step-by-step (alert #1, the others are the same shape)
1. **Alerts → New Alert → Metrics-based.**
2. Query builder: metric **`hydro.water_temp`**, aggregation **avg** (optionally *group by* `zone`).
3. Condition: send when value is **above** the threshold **24**, occurring **at least once**
   during the last **5 min**.
4. Severity **critical**; name **"Water temp critical (root rot)"**; add a notification
   channel (Slack/email) or leave default for a local demo.
5. **Save.**
6. Open **Mission Control → click `heatwave`.** Water temp climbs past 24 °C within a minute
   or two → the alert flips to **Firing** (Alerts → Triggered). Screenshot it.

## Step-by-step (alert #4, exceptions-based)
1. **Alerts → New Alert → Exceptions-based.**
2. Filter to `serviceName = rootcause-hydro` and exception type containing **`PumpTimeoutError`**.
3. Condition: count **> 0** in the last **5 min**.
4. Save. Click **`pump_failure`** in Mission Control. The next `dosing.cycle` throws a
   `PumpTimeoutError` (visible under **Exceptions** and as a red error trace) → alert fires.

> Tip: with `ROOTCAUSE_DOSE_EVERY_TICKS=6` and `ROOTCAUSE_TICK_SECONDS=3`, a dosing cycle
> runs ~every 18 s, so the pump-failure exception appears fast. Lower `DOSE_EVERY_TICKS` to
> `2` for an even snappier demo.

`python signoz/apply_signoz.py` prints this same threshold list any time.
