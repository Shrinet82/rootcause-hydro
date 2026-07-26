"""Tiny CLI to drive a running RootCause instance during a demo.

    python -m rootcause.cli status
    python -m rootcause.cli inject heatwave
    python -m rootcause.cli clear
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

BASE = os.getenv("ROOTCAUSE_API", "http://localhost:8099")


def _print(resp):
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    resp.raise_for_status()


def main() -> None:
    p = argparse.ArgumentParser(description="RootCause control CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    inj = sub.add_parser("inject")
    inj.add_argument("fault")
    sub.add_parser("clear")
    args = p.parse_args()

    try:
        if args.cmd == "status":
            _print(requests.get(f"{BASE}/status", timeout=5))
        elif args.cmd == "inject":
            _print(requests.post(f"{BASE}/fault/{args.fault}", timeout=5))
        elif args.cmd == "clear":
            _print(requests.post(f"{BASE}/clear", timeout=5))
    except requests.RequestException as exc:
        print(f"error talking to {BASE}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
