"""Entrypoint: `python -m rootcause.run` -- serves the API and runs the sim."""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("ROOTCAUSE_HOST", "0.0.0.0")
    # Cloud platforms (Render/Fly/Railway) inject $PORT; fall back to our default.
    port = int(os.getenv("PORT") or os.getenv("ROOTCAUSE_PORT", "8099"))
    uvicorn.run("rootcause.app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
