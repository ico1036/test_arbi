#!/usr/bin/env python3
"""
Polymarket Paper Trading Dashboard

Run this directly:
    python run_dashboard.py
    python run_dashboard.py --port 3000
"""
import sys
sys.path.insert(0, "src")

from polyarb.dashboard import run_dashboard

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Paper Trading Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port to run on")
    args = parser.parse_args()
    run_dashboard(port=args.port)
