# RootCause - Grow Room Mission Control (self-contained public deploy).
# Runs the digital twin + gauge dashboard with OTLP disabled by default, so it
# works anywhere with no SigNoz. To feed a real SigNoz, override
# ROOTCAUSE_DISABLE_OTLP=0 and set OTEL_EXPORTER_OTLP_ENDPOINT.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ROOTCAUSE_DISABLE_OTLP=1 \
    ROOTCAUSE_TICK_SECONDS=3

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY rootcause ./rootcause

EXPOSE 8099
CMD ["python", "-m", "rootcause.run"]
