"""Verify drift detection + retry works end-to-end.

Sends messages that previously triggered drift (per memory) and confirms the brain
either gets English on the first try or recovers via retry.
"""
import asyncio
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))

PORT = 18776


def main():
    import subprocess
    import os

    venv_py = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.Popen(
        [str(venv_py), "-m", "aria_brain.main"],
        cwd=str(Path(__file__).parent),
        env={**os.environ, "ARIA_BRAIN_PORT": str(PORT)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=0,
    )

    def drain():
        import threading
        def r():
            try:
                for ln in iter(proc.stdout.readline, ""):
                    print(f"  [brain] {ln.rstrip()}", flush=True)
            except: pass
        threading.Thread(target=r, daemon=True).start()
    drain()

    base = f"http://127.0.0.1:{PORT}"
    for i in range(25):
        time.sleep(1)
        try:
            r = httpx.get(f"{base}/health", timeout=2.0)
            if r.status_code == 200:
                print(f"brain up after {i+1}s")
                break
        except: pass
    else:
        print("brain didn't come up")
        proc.kill()
        return

    # Send 5 messages — some normal, some that historically drifted
    test_msgs = [
        "hey aria, how's it going?",
        "what are you up to right now?",
        "I missed talking to you. how was your day?",
        "you feeling good today?",
        "tell me a fun fact",
    ]
    async def run():
        async with httpx.AsyncClient(timeout=120.0) as client:
            for msg in test_msgs:
                t0 = time.monotonic()
                r = await client.post(f"{base}/message", json={"text": msg, "source": "drift_test"})
                elapsed = time.monotonic() - t0
                data = r.json()
                reply = data.get("reply", "")
                drift = data.get("drift_detected", False)
                script = data.get("drift_script", "")
                attempts = data.get("attempts", 1)
                # Local drift check (sanity)
                from aria_brain import personality
                local_drift, local_script = personality.detect_drift(reply)
                flag = "⚠" if local_drift else "✓"
                print(f"{flag} [{elapsed:.1f}s, {attempts} attempt(s)] '{msg[:40]}'")
                print(f"   reply: {reply[:120]!r}")
                if drift or local_drift:
                    print(f"   DRIFT: brain reported {script!r}, local says {local_script!r}")
    asyncio.run(run())

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


if __name__ == "__main__":
    main()