@echo off
"C:\ProgramData\chocolatey\bin\ffmpeg.exe" -y -f gdigrab -framerate 30 -i desktop -t 15 -c:v libx264 -preset ultrafast -crf 28 "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\logs\aria_after.mp4" 2>&1
