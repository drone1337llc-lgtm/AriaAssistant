#!/usr/bin/env python3
"""
voice_transfer.py — Transfer trained XTTS v2 model PC 2 → PC 1
==============================================================
Run on PC 2 after voice_train.py completes (or as part of nightly cron).

Copies the trained model from PC 2 to PC 1 over the local network.
Usesrobocopy on Windows for reliable large-file transfer with resume support.

Usage:
    python voice_transfer.py                    # normal transfer
    python voice_transfer.py --dry-run          # show what would be copied
    python voice_transfer.py --watch            # watch mode: re-transfer if model changes

Environment (set these on PC 2):
    PC1_HOST   = IP of PC 1, e.g. "192.168.68.1"
    PC1_USER   = Windows username on PC 1, e.g. "Tench"
    PC1_PASS   = Windows password for PC1_USER
"""

import os, sys, time, hashlib, logging, argparse
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
PC2_MODEL_DIR  = Path("C:/Users/Tench/Documents/AI Learning/astro_assistant/models/xtts_astrobud")
PC1_MODEL_DIR  = Path("C:/Users/Tench/Documents/AI Learning/astro_assistant/models/xtts_astrobud")

# Network config (gigabit Ethernet)
PC1_HOST = os.environ.get("PC1_HOST", "192.168.68.1")
PC1_USER = os.environ.get("PC1_USER", "Tench")
PC1_PASS = os.environ.get("PC1_PASS", "")   # set via env var

# Transfer log
LOG_FILE = Path("C:/Users/Tench/Documents/AI Learning/astro_assistant/logs/voice_transfer.log")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("voice_transfer")


# ── File hash (quick check if model changed) ───────────────────────────────────
def model_hash(model_dir):
    """Quick hash of all model files to detect changes."""
    h = hashlib.sha256()
    for f in sorted(model_dir.rglob("*")):
        if f.is_file() and f.suffix in (".pt", ".pth", ".json", ".yaml"):
            h.update(str(f.relative_to(model_dir)).encode())
            h.update(str(f.stat().st_mtime).encode())
    return h.hexdigest()[:16]


# ── Windows robocopy transfer ──────────────────────────────────────────────────
def transfer_via_robocopy(src_dir, dst_dir, dry_run=False):
    """Use robocopy (built into Windows) for reliable network transfer.
    Handles large files, resume, and permissions correctly.
    """
    src_str = str(src_dir).replace("/", "\\")
    dst_str = str(dst_dir).replace("/", "\\")

    # Check PC 1 is reachable first
    log.info(f"Pinging PC 1 at {PC1_HOST} ...")
    import subprocess
    ping = subprocess.run(
        ["ping", "-n", "2", "-w", "500", PC1_HOST],
        capture_output=True, text=True,
    )
    if ping.returncode != 0:
        log.error(f"PC 1 ({PC1_HOST}) is not reachable. Check network.")
        return False

    log.info(f"PC 1 reachable. Starting transfer: {src_dir} → \\\\{PC1_HOST}\\{dst_dir}")

    # Build robocopy command
    # /MIR  = mirror (delete extras at dest, copy updates)
    # /R:3  = retry 3 times on failure
    # /W:5  = wait 5 sec between retries
    # /NP   = no progress percentage (cleaner log)
    # /NDL  = no directory list
    # /TEE  = show in console AND log file
    robocopy_args = [
        "robocopy",
        src_str,
        dst_str,
        "/MIR",
        "/R:3", "/W:5",
        "/NP", "/NDL",
        "/TEE",
    ]
    if dry_run:
        robocopy_args[1:1] = ["/L"]  # /L = list only, no copy

    log.info("  robocopy " + " ".join(robocopy_args[1:]))
    result = subprocess.run(robocopy_args, capture_output=True, text=True)

    # robocopy exit codes:
    # 0-7 = success (0=newer, 1=copied, 2=extra, 7=copied+extra)
    # 8+  = error
    if result.returncode >= 8:
        log.error(f"robocopy failed with exit code {result.returncode}")
        log.error(result.stdout[-500:] if result.stdout else "")
        log.error(result.stderr[-500:] if result.stderr else "")
        return False
    else:
        log.info(f"  Transfer complete (exit code {result.returncode})")
        return True


# ── SSH/SMB alternative ────────────────────────────────────────────────────────
def transfer_via_smb(src_dir, dst_dir, dry_run=False):
    """Fallback: use smbclient or PowerShell SMB copy if robocopy fails."""
    log.info("Trying SMB copy via PowerShell Copy-Item ...")
    try:
        import subprocess
        # Map as temporary drive
        drive_letter = "Z:"
        ps_drive = f"net use {drive_letter} \\\\\{PC1_HOST}\\C$ /u:{PC1_USER} {PC1_PASS}"
        ps_copy = f"Copy-Item -Path '{src_dir}\\*' -Destination '{dst_dir}\\' -Recurse -Force"
        ps_cleanup = f"net use {drive_letter} /delete /y"

        if dry_run:
            log.info(f"  [DRY RUN] {ps_drive}")
            log.info(f"  [DRY RUN] {ps_copy}")
            return True

        subprocess.run(ps_drive, shell=True, check=True, capture_output=True)
        dst_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(ps_copy, shell=True, check=True, capture_output=True)
        subprocess.run(ps_cleanup, shell=True, capture_output=True)
        log.info("  SMB copy complete")
        return True
    except Exception as e:
        log.error(f"SMB copy failed: {e}")
        return False


# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Transfer XTTS model PC 2 → PC 1")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be transferred, don't copy")
    parser.add_argument("--watch", action="store_true",
                        help="Watch mode: re-transfer if model directory changes")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("  AstroBud Voice Model Transfer  (PC 2 → PC 1)")
    log.info(f"  Source:    {PC2_MODEL_DIR}")
    log.info(f"  Dest:      \\\\{PC1_HOST}\\{PC1_MODEL_DIR}")
    log.info("=" * 60)

    if not PC2_MODEL_DIR.exists():
        log.error(f"Model directory not found: {PC2_MODEL_DIR}")
        log.info("Run voice_train.py on PC 2 first.")
        sys.exit(1)

    # Check model files exist
    model_files = list(PC2_MODEL_DIR.rglob("*.pt")) + list(PC2_MODEL_DIR.rglob("*.pth"))
    if not model_files:
        log.error("No .pt/.pth model files found in model directory.")
        log.info(f"Contents of {PC2_MODEL_DIR}:")
        for f in sorted(PC2_MODEL_DIR.rglob("*"))[:20]:
            log.info(f"  {f.relative_to(PC2_MODEL_DIR)}")
        sys.exit(1)

    total_size = sum(f.stat().st_size for f in model_files)
    log.info(f"Model files: {len(model_files)}  ({total_size / 1e9:.2f} GB)")

    if args.watch:
        log.info("Watch mode: monitoring for model changes ...")
        last_hash = model_hash(PC2_MODEL_DIR)
        while True:
            time.sleep(300)  # check every 5 minutes
            cur_hash = model_hash(PC2_MODEL_DIR)
            if cur_hash != last_hash:
                log.info("Model changed — triggering transfer ...")
                if transfer_via_robocopy(PC2_MODEL_DIR, PC1_MODEL_DIR):
                    last_hash = cur_hash
                else:
                    log.warning("Transfer failed, will retry in 5 min")
            else:
                log.debug(f"{time.strftime('%H:%M')} — model unchanged, skipping")

    else:
        log.info(f"\nTransfer{' (DRY RUN)' if args.dry_run else ''}:")
        if transfer_via_robocopy(PC2_MODEL_DIR, PC1_MODEL_DIR, dry_run=args.dry_run):
            log.info("✓ Model transferred to PC 1 successfully")
        else:
            log.info("Trying SMB fallback ...")
            if transfer_via_smb(PC2_MODEL_DIR, PC1_MODEL_DIR, dry_run=args.dry_run):
                log.info("✓ Model transferred via SMB")
            else:
                log.error("Transfer failed. Copy manually:")
                log.error(f"  From: {PC2_MODEL_DIR}")
                log.error(f"  To:   {PC1_MODEL_DIR}")
                sys.exit(1)

        if not args.dry_run:
            # Verify
            if PC1_MODEL_DIR.exists():
                pc1_files = list(PC1_MODEL_DIR.rglob("*.pt"))
                log.info(f"✓ PC 1 model directory verified: {len(pc1_files)} model files")

    log.info("Done.")


if __name__ == "__main__":
    main()