"""Quick environment check for a PC2 venv. Run with the venv's python.exe:
    <venv>\\Scripts\\python.exe pc2_check.py
Prints TTS import status + torch/CUDA status, with no shell-quoting headaches.
"""
import sys

print("python:", sys.version.split()[0], sys.executable)

try:
    from TTS.tts.models.xtts import Xtts  # noqa: F401
    print("TTS_IMPORT: OK")
except Exception as e:
    print("TTS_IMPORT: FAIL ->", repr(e))

try:
    import torch
    print("TORCH:", torch.__version__, "CUDA_AVAILABLE:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
except Exception as e:
    print("TORCH: FAIL ->", repr(e))
