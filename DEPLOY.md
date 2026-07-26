# Deploying RootCause / exposing it to others

Two things people want to reach: the **Mission Control page** (the gauges) and your
**SigNoz dashboards** (traces, alerts). They deploy differently.

---

## A. Mission Control page → a permanent public URL (recommended)

The gauge page is a self-contained FastAPI app: the digital twin runs in-process, so it
needs **no SigNoz** to render. That makes it trivial to host. It ships with
`ROOTCAUSE_DISABLE_OTLP=1` by default so it "just works" anywhere.

### Option 1 — Render (Docker, free, ~2 min)
1. Push this repo to GitHub (done).
2. Render → **New → Blueprint** → connect the repo. It reads `render.yaml`, builds the
   `Dockerfile`, and gives you `https://rootcause-mission-control.onrender.com`.
3. Share that URL. Judges can watch the gauges **and click the fault buttons live.**

### Option 2 — Fly.io (Docker, free tier)
```bash
curl -L https://fly.io/install.sh | sh
flyctl auth signup
flyctl launch --now        # reads fly.toml + Dockerfile
# -> https://rootcause-hydro.fly.dev
```

### Option 3 — Railway / any Docker host
Point it at the repo; it detects the `Dockerfile`. Expose port `8099` (or `$PORT`).

> Want the deployed page to feed a **real** SigNoz too? Override the env:
> `ROOTCAUSE_DISABLE_OTLP=0` and `OTEL_EXPORTER_OTLP_ENDPOINT=<reachable SigNoz OTLP>`.

---

## B. SigNoz dashboards → share during the judging window

SigNoz is heavier (ClickHouse), so for a hackathon the fastest way to let others see **your
running SigNoz** is a tunnel from your machine.

### Cloudflare Tunnel (no signup, https, instant)
```bash
# install once (Linux):
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -O cloudflared && chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/

cloudflared tunnel --url http://localhost:8080   # -> public URL for SigNoz
cloudflared tunnel --url http://localhost:8099   # -> public URL for Mission Control
```
Each command prints a `https://<random>.trycloudflare.com` URL. Paste them in your submission.

**Notes / gotchas**
- The tunnel lives only while the command runs and your machine is awake — perfect for a
  live demo/judging window, not a permanent link. Pair it with the recorded demo video as
  the always-available proof.
- SigNoz is behind its own login, so a public tunnel is still gated. Create a **read-only
  viewer** account for judges (SigNoz → Settings → Members) and share those creds.
- `ngrok http 8080` works too (needs a free authtoken).

### Durable SigNoz (optional, beyond the deadline)
Run SigNoz's Docker Compose on a small cloud VM (2 vCPU / 4 GB, e.g. a DigitalOcean
droplet), open port 8080 behind a reverse proxy + TLS, point RootCause's
`OTEL_EXPORTER_OTLP_ENDPOINT` at it. That gives a permanent SigNoz URL.

---

## What to put in your submission
- **Live gauges:** the Render/Fly URL (permanent, clickable, self-contained).
- **SigNoz depth:** the cloudflared URL during judging **+** the demo video (always available).
- **Code:** this repo.
