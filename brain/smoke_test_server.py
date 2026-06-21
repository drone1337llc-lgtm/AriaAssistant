"""Quick server test — start uvicorn in a subprocess, hit /health, kill it."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
PORT = 18770  # different port so it doesn't collide with the real server


def main():
    print(f"=== Aria Brain server test (port {PORT}) ===")
    env_overrides = {
        "ARIA_BRAIN_PORT": str(PORT),
        "MOOD_STATE_PATH": str(HERE / "test_mood.json"),
    }

    print("Starting uvicorn...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "aria_brain.server:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "info"],
        cwd=str(HERE),
        env={**os.environ, **env_overrides},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=0,
    )

    # Background thread: print everything the subprocess emits, don't block us.
    def printer():
        try:
            for line in iter(proc.stdout.readline, ""):
                print(f"  [srv] {line.rstrip()}")
        except Exception:
            pass
    t = threading.Thread(target=printer, daemon=True)
    t.start()

    try:
        base = f"http://127.0.0.1:{PORT}"

        # Wait for server to come up
        print("Waiting for uvicorn to bind...")
        up = False
        for i in range(30):
            time.sleep(1)
            try:
                r = httpx.get(f"{base}/health", timeout=3.0)
                if r.status_code == 200:
                    up = True
                    break
            except Exception:
                pass
        if not up:
            print(f"  uvicorn didn't come up in {i+1}s")
            return 1
        print(f"  up after {i+1}s")

        # Give ChromaDB warmup a couple of extra seconds (it loads an 80MB model)
        print("Letting warmup settle (2s)...")
        time.sleep(2)

        print()
        print("=== GET /health ===")
        r = httpx.get(f"{base}/health", timeout=10.0)
        print(f"  status: {r.status_code}")
        data = r.json()
        print(f"  brain_version: {data['brain_version']}")
        print(f"  memory: {data['memory']}")
        print(f"  mood: value={data['mood']['value']:.2f} label={data['mood']['label']}")

        print()
        print("=== GET /mood ===")
        r = httpx.get(f"{base}/mood", timeout=5.0)
        print(f"  status: {r.status_code}, body: {r.json()}")

        print()
        print("=== POST /message (this calls the LLM) ===")
        t0 = time.monotonic()
        r = httpx.post(
            f"{base}/message",
            json={"text": "hey, it's me. testing the brain server.", "source": "smoke"},
            timeout=120.0,
        )
        elapsed = time.monotonic() - t0
        print(f"  status: {r.status_code} (took {elapsed:.1f}s)")
        msg = r.json()
        print(f"  reply: {msg['reply'][:160]}")
        print(f"  mood: {msg['mood']:.2f} ({msg['mood_label']})")
        print(f"  memories_used: {msg['memories_used']}")

        print()
        print("=== POST /reflect ===")
        t0 = time.monotonic()
        r = httpx.post(f"{base}/reflect", timeout=120.0)
        elapsed = time.monotonic() - t0
        print(f"  status: {r.status_code} (took {elapsed:.1f}s)")
        refl = r.json()
        print(f"  thought: {refl['thought'][:160]}")

        print()
        print("=== all endpoints OK ===")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())