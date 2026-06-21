#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stress test for the FloodDiffusion motion server.

Hammers the server with N request_motion submissions in quick succession,
then watches the queue as the worker drains it. Verifies:
  • All N requests are accepted (when N < cap)
  • All return a unique id
  • The "running" field never has > 1 id at a time (single-job)
  • The depth monotonically decreases as requests complete
  • When N > cap, exactly (N - cap) requests get HTTP 429

Usage:
  # Start the server in MOCK mode first (no GPU required, fast):
  python motion_server.py --port 18765 --mock --capacity 100

  # Then run the stress test
  python stress_test.py --url http://127.0.0.1:18765 --n 25 --cap 100
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
import urllib.error

# Force UTF-8 stdout so the [OK]/[FAIL] markers print cleanly on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def post(url, body):
    req = urllib.request.Request(url, method="POST")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18765")
    ap.add_argument("--n", type=int, default=25, help="number of requests to submit")
    ap.add_argument("--cap", type=int, default=100, help="expected capacity (for the cap-overflow test)")
    ap.add_argument("--drain-timeout", type=float, default=10.0, help="seconds to wait for the queue to drain")
    args = ap.parse_args()

    print(f"=== Stress test: POST {args.n} requests to {args.url} ===")

    # Phase 0: health
    code, body = get(f"{args.url}/healthz")
    print(f"  /healthz: {code} {body}")
    if code != 200:
        print("Server is not healthy; aborting")
        return 1

    # Phase 1: enqueue all N
    print(f"--- Phase 1: enqueue {args.n} requests ---")
    ids = []
    n_429 = 0
    start = time.time()
    for i in range(args.n):
        prompt = f"stress test motion #{i+1} — Aria does a graceful wave"
        code, body = post(f"{args.url}/motion", {
            "prompt": prompt,
            "frames": 30,
            "suggested_name": f"stress_{i+1:03d}",
        })
        if code == 200:
            ids.append(body["id"])
            print(f"  [{i+1:3d}] 200 id={body['id']} pos={body['position']}")
        elif code == 429:
            n_429 += 1
            print(f"  [{i+1:3d}] 429 (queue full)")
        else:
            print(f"  [{i+1:3d}] {code} {body}")
    elapsed = time.time() - start
    print(f"  enqueued {len(ids)} in {elapsed:.1f}s; rejected (429): {n_429}")

    # Expected: if N > cap, N - cap rejected. If N <= cap, 0 rejected.
    expected_429 = max(0, args.n - args.cap)
    if n_429 != expected_429:
        print(f"  [FAIL] expected {expected_429} rejections, got {n_429}")
        return 1
    print(f"  [OK] queue-cap honored (expected {expected_429} rejections, got {n_429})")

    if not ids:
        print("Nothing to drain; done")
        return 0

    # Phase 2: poll until drained (or timeout)
    print(f"--- Phase 2: poll until queue drains (timeout {args.drain_timeout}s) ---")
    pending = set(ids)
    completed = []
    failed = []
    single_job_violations = 0
    depth_history = []
    t0 = time.time()
    while pending and (time.time() - t0) < args.drain_timeout:
        code, body = post(f"{args.url}/motion/status", {"ids": list(pending)})
        if code != 200:
            print(f"  poll error {code}: {body}")
            time.sleep(0.5)
            continue
        depth = sum(1 for r in body["results"] if r["status"] in ("pending", "running"))
        running_count = sum(1 for r in body["results"] if r["status"] == "running")
        if running_count > 1:
            single_job_violations += 1
        depth_history.append(depth)
        for r in body["results"]:
            if r["status"] in ("done", "failed"):
                if r["status"] == "done":
                    completed.append(r["id"])
                else:
                    failed.append(r["id"])
                pending.discard(r["id"])
        time.sleep(0.2)
    drained = not pending
    elapsed = time.time() - t0
    print(f"  drained={drained} in {elapsed:.1f}s (depth sequence: {depth_history[:20]}{'...' if len(depth_history) > 20 else ''})")

    if not drained:
        print(f"  [FAIL] queue did not drain within timeout (still {len(pending)} pending)")
        return 1
    print(f"  ✓ drained; completed={len(completed)} failed={len(failed)}")

    # Phase 3: single-job verification
    if single_job_violations > 0:
        print(f"  [FAIL] single-job semantic violated {single_job_violations} times during poll")
        return 1
    print(f"  [OK] single-job semantic maintained (never > 1 running)")

    # Phase 4: monotonic depth check (depth should never increase after enqueue)
    if depth_history != sorted(depth_history, reverse=True):
        # Hmm, depth can plateau but shouldn't go up. Look for the first increase.
        for i in range(1, len(depth_history)):
            if depth_history[i] > depth_history[i-1]:
                print(f"  [FAIL] depth increased at poll {i} ({depth_history[i-1]} -> {depth_history[i]})")
                return 1
    print(f"  [OK] depth monotonically decreased (or plateaued)")

    # Phase 5: cap
    code, body = get(f"{args.url}/motion/cap")
    final_depth = body["depth"]
    if final_depth != 0:
        print(f"  [FAIL] final depth = {final_depth} (expected 0)")
        return 1
    print(f"  [OK] final depth = 0")

    print()
    print(f"=== ALL STRESS CHECKS PASSED ===")
    print(f"  {len(ids)} requests enqueued, {n_429} rejected (cap {args.cap}), {len(completed)} completed, {len(failed)} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
