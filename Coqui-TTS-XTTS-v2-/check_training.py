from tensorboard.backend.event_processing import event_accumulator
import os
from datetime import datetime

logdir = r"C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\run\training"
runs = [d for d in os.listdir(logdir) if os.path.isdir(os.path.join(logdir, d))]
runs.sort(key=lambda x: os.path.getmtime(os.path.join(logdir, x)), reverse=True)

for run in runs[:1]:
    run_path = os.path.join(logdir, run)
    ea = event_accumulator.EventAccumulator(run_path)
    ea.Reload()
    print(f"Run: {run}")
    print(f"Scalars: {ea.Tags()['scalars']}")
    for tag in ea.Tags()["scalars"]:
        events = ea.Scalars(tag)
        if events:
            last = events[-1]
            print(f"  {tag}: step={last.step}, value={last.value:.6f}, wall_time={datetime.fromtimestamp(last.wall_time).strftime('%H:%M:%S')}")