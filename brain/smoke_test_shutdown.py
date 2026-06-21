"""Verify the Brain shuts down cleanly via Ctrl-C and /shutdown."""
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
PORT = 18771


def drain_output(proc, label):
    def reader():
        try:
            for line in iter(proc.stdout.readline, ""):
                print(f"  [{label}] {line.rstrip()}")
        except Exception:
            pass
    t = threading.Thread(target=reader, daemon=True)
    t.start()


def test_ctrl_c():
    print("=" * 60)
    print("TEST 1: Ctrl-C shutdown")
    print("=" * 60)
    env = {"ARIA_BRAIN_PORT": str(PORT), "PATH": __import__("os").environ.get("PATH", "")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "aria_brain.main"],
        cwd=str(HERE),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=0,
    )
    drain_output(proc, "brain")
    try:
        # Wait for ready
        for i in range(20):
            time.sleep(1)
            try:
                r = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=2.0)
                if r.status_code == 200:
                    print(f"  brain up after {i+1}s")
                    break
            except Exception:
                pass
        else:
            print("  brain didn't come up")
            return False

        # Send SIGINT (Ctrl-C equivalent on Windows is also SIGINT)
        print("  sending SIGINT (Ctrl-C)...")
        proc.send_signal(3)  # SIGINT

        # Wait for it to die
        for i in range(10):
            time.sleep(1)
            if proc.poll() is not None:
                print(f"  brain exited cleanly after {i+1}s (rc={proc.returncode})")
                return True
        print("  brain didn't exit, force killing")
        proc.kill()
        return False
    finally:
        if proc.poll() is None:
            proc.kill()


def test_shutdown_endpoint():
    print()
    print("=" * 60)
    print("TEST 2: /shutdown endpoint")
    print("=" * 60)
    port2 = PORT + 1
    env = {"ARIA_BRAIN_PORT": str(port2), "PATH": __import__("os").environ.get("PATH", "")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "aria_brain.main"],
        cwd=str(HERE),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=0,
    )
    drain_output(proc, "brain")
    try:
        for i in range(20):
            time.sleep(1)
            try:
                r = httpx.get(f"http://127.0.0.1:{port2}/health", timeout=2.0)
                if r.status_code == 200:
                    print(f"  brain up after {i+1}s")
                    break
            except Exception:
                pass

        print("  calling POST /shutdown...")
        r = httpx.post(f"http://127.0.0.1:{port2}/shutdown", timeout=5.0)
        print(f"  response: {r.status_code} {r.json()}")

        for i in range(10):
            time.sleep(1)
            if proc.poll() is not None:
                print(f"  brain exited cleanly after {i+1}s (rc={proc.returncode})")
                return True
        print("  brain didn't exit, force killing")
        proc.kill()
        return False
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    ok1 = test_ctrl_c()
    ok2 = test_shutdown_endpoint()
    print()
    if ok1 and ok2:
        print("✓ Both shutdown paths work")
    else:
        print(f"✗ ctrl-c={ok1} endpoint={ok2}")