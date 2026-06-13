#!/usr/bin/env python3
"""
voice_schedule.py — Nightly voice training scheduler for PC 2
============================================================
Run once on PC 2 to set up the nightly training cron/Task Scheduler job.

What it does:
  1. Schedules voice_train.py to run every night at 3:00 AM
  2. On completion, triggers voice_transfer.py to push model to PC 1
  3. Logs everything to logs/voice_schedule.log

Usage (run once on PC 2):
    python voice_schedule.py          # set up the scheduled task
    python voice_schedule.py --remove  # remove the scheduled task
    python voice_schedule.py --test    # run immediately without scheduling

Requires:
    PC 1 is reachable at PC1_HOST (set in voice_transfer.py or env var)
"""

import os, sys, time, subprocess, logging
from pathlib import Path

SCHEDULE_LOG = Path("C:/Users/Tench/Documents/AI Learning/astro_assistant/logs/voice_schedule.log")
TRAIN_SCRIPT = Path(__file__).parent / "voice_train.py"
TRANSFER_SCRIPT = Path(__file__).parent / "voice_transfer.py"
PYTHON_EXE = sys.executable

# Training time window: 3:00 AM daily
TRAIN_TIME  = "03:00"   # 24-hour format
TRAIN_DAY   = "DAILY"   # or "MONDAY", "TUESDAY", "WEEKDAY", etc.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(SCHEDULE_LOG),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("voice_schedule")


def setup_windows_task():
    """Register a Windows Task Scheduler job for nightly training."""
    task_name = "AstroBud_NightlyVoiceTraining"

    # Build the PowerShell command that chains train → transfer
    train_cmd  = f'& "{PYTHON_EXE}" "{TRAIN_SCRIPT}"'
    transfer_cmd = f'& "{PYTHON_EXE}" "{TRANSFER_SCRIPT}"'
    combined = f'{train_cmd}; if ($LASTEXITCODE -eq 0) {{ {transfer_cmd} }}'

    ps_script = f"""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -Command "{combined}"'
$trigger = New-ScheduledTaskTrigger -Daily -At '{TRAIN_TIME}'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

# Remove existing task if it exists
Unregister-ScheduledTask -TaskName '{task_name}' -Confirm:$false -ErrorAction SilentlyContinue

# Register new task
Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'AstroBud nightly XTTS v2 voice training (PC 2)'

Write-Output "Task '{task_name}' registered. Runs daily at {TRAIN_TIME}."
"""

    log.info(f"Registering Windows Task Scheduler job: {task_name}")
    log.info(f"  Train:  {TRAIN_SCRIPT}")
    log.info(f"  Transfer: {TRANSFER_SCRIPT}")
    log.info(f"  Time:   {TRAIN_TIME} daily")

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            log.info("✓ Scheduled task registered successfully")
            log.info(result.stdout.strip())
        else:
            log.error(f"Task registration failed:\n{result.stderr}")
            return False
    except Exception as e:
        log.error(f"PowerShell error: {e}")
        return False

    return True


def remove_windows_task():
    """Remove the nightly training task."""
    task_name = "AstroBud_NightlyVoiceTraining"
    log.info(f"Removing scheduled task: {task_name}")
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f'Unregister-ScheduledTask -TaskName "{task_name}" -Confirm:$false'],
            capture_output=True, timeout=30,
        )
        log.info("✓ Task removed")
    except Exception as e:
        log.error(f"Failed to remove task: {e}")


def test_run():
    """Run the full pipeline now without scheduling."""
    log.info("=" * 60)
    log.info("  TEST RUN — voice_train + voice_transfer")
    log.info("=" * 60)

    # Run training
    log.info("\n--- Step 1: Training ---")
    train_result = subprocess.run(
        [PYTHON_EXE, str(TRAIN_SCRIPT)],
        capture_output=True, text=True,
    )
    if train_result.returncode != 0:
        log.error("Training failed:")
        log.error(train_result.stderr[-1000:])
        return False
    else:
        log.info("✓ Training complete")

    # Run transfer
    log.info("\n--- Step 2: Transfer to PC 1 ---")
    xfer_result = subprocess.run(
        [PYTHON_EXE, str(TRANSFER_SCRIPT)],
        capture_output=True, text=True,
    )
    if xfer_result.returncode != 0:
        log.warning("Transfer failed (PC 1 may be offline):")
        log.warning(xfer_result.stderr[-500:])
        return False
    else:
        log.info("✓ Transfer complete")

    log.info("=" * 60)
    log.info("  ALL DONE — pipeline verified")
    log.info("=" * 60)
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AstroBud voice training scheduler")
    parser.add_argument("--remove", action="store_true", help="Remove the scheduled task")
    parser.add_argument("--test",   action="store_true", help="Run pipeline now without scheduling")
    args = parser.parse_args()

    log.info("AstroBud Nightly Voice Training Scheduler")
    log.info(f"PC 2: {os.environ.get('COMPUTERNAME', 'unknown')}")
    log.info(f"Python: {PYTHON_EXE}")

    if args.remove:
        remove_windows_task()
    elif args.test:
        test_run()
    else:
        setup_windows_task()
        log.info("\nScheduled task is active. Next run: "
                 f"{TRAIN_TIME} daily.")
        log.info("To run manually now: python voice_schedule.py --test")
        log.info("To remove: python voice_schedule.py --remove")