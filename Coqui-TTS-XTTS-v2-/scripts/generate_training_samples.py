import os
import requests
import time
import subprocess
import random
from pathlib import Path

# --- Configuration ---
API_KEY = "972e4fc0fdb74834fa34422c1b228b7b82cd971628659d461073759081925bfa"
VOICE_ID = "HV4UOL5rtTGkWTULlq6W"
OUTPUT_DIR = Path("data/astrobud_voice/wavs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Your comprehensive list
SAMPLES = [
    ("Hello, I'm AstroBud, your personal desktop AI assistant. How can I help you today?", 0.35, 0.15),
    ("Good morning! I hope you had a restful sleep. What are we working on today?", 0.30, 0.20),
    ("Alright, I've finished. Let me know if you'd like me to make any changes.", 0.35, 0.10),
    ("I'll get that done for you right away. Give me just a moment.", 0.35, 0.15),
    ("That's a really interesting point. Tell me more about what you found.", 0.30, 0.20),
    ("Don't worry, this is a common issue and it's easy to fix once you know how.", 0.40, 0.10),
    ("The quick brown fox jumps over the lazy dog. Every letter of the alphabet.", 0.35, 0.10),
    ("Pack my box with five dozen liquor jugs.", 0.40, 0.05),
    ("Sphinx of black quartz, judge my vow.", 0.40, 0.05),
    ("I can read your screen, run code, manage your calendar, and answer questions instantly.", 0.35, 0.15),
    ("Machine learning is transforming the way we interact with technology.", 0.35, 0.10),
    ("The model accuracy improved significantly after we made those adjustments.", 0.35, 0.10),
    ("I've checked all the dependencies and everything looks good to go.", 0.40, 0.10),
    ("The training process is almost complete. We should have results soon.", 0.35, 0.15),
    ("Let me handle this for you while you focus on the bigger picture.", 0.30, 0.20),
    ("I've analyzed the logs and everything looks stable.", 0.35, 0.2),
    ("Let me pull up those files for you right away.", 0.3, 0.15),
    ("I'm sorry, I couldn't find the folder you're looking for.", 0.4, 0.1),
    ("That's a fascinating question, let me look into it.", 0.35, 0.25),
    ("I've finished the task, is there anything else you need?", 0.3, 0.1),
    ("I am genuinely so excited to see how this project turns out!", 0.25, 0.4),
    ("Oh, I really hope we can get this fixed before the deadline.", 0.35, 0.3),
    ("That is absolutely brilliant! I love that idea.", 0.3, 0.35),
    ("I'm a little bit worried about the performance on this one.", 0.45, 0.15),
    ("The salt breeze came across from the sea.", 0.35, 0.1),
    ("The wide road shimmered in the hot sun.", 0.35, 0.1),
    ("Sphinx of black quartz, judge my vow.", 0.4, 0.05),
    ("Pack my box with five dozen liquor jugs.", 0.4, 0.05),
    ("The swans were swimming in the park pond.", 0.35, 0.15),
    ("The birch canoe slid on the smooth planks.", 0.35, 0.15),
    ("Glue the sheet to the dark blue background.", 0.35, 0.15),
    ("A pot of tea helps to pass the evening.", 0.35, 0.2),
    ("A rich farm is rare in this sandy waste.", 0.30, 0.1),
    ("The hogs were fed chopped corn and garbage.", 0.30, 0.1),
    ("Four hours of steady work faced us.", 0.35, 0.15),
    ("I've analyzed the data and here is what I found.", 0.35, 0.2),
    ("I can definitely help you with that right now.", 0.30, 0.25),
    ("Let me check the system status for you.", 0.35, 0.15),
    ("That's an interesting approach, I hadn't thought of it that way.", 0.35, 0.20),
    ("I've updated the configuration files as requested.", 0.40, 0.10),
    ("Would you like me to summarize the main points?", 0.35, 0.25),
    ("I'm ready when you are, just let me know.", 0.30, 0.20),
    ("That seems to be the most efficient solution.", 0.35, 0.15),
    ("I've been working on this for a while and it's finally ready.", 0.30, 0.15),
    ("Is there anything else you need assistance with today?", 0.35, 0.20),
    ("The mountain peak was covered in a thick layer of snow.", 0.35, 0.15),
    ("A gentle rain began to fall as the sun went down.", 0.30, 0.20),
    ("The history of this city is filled with many stories.", 0.35, 0.10),
    ("The garden was filled with bright, fragrant flowers.", 0.35, 0.25),
    ("It was a long journey, but it was worth every moment.", 0.30, 0.25),
    ("The ship sailed quietly across the calm ocean waters.", 0.35, 0.10),
    ("The old library was quiet and smelled of aged paper.", 0.30, 0.15),
    ("The city lights twinkled like stars in the distance.", 0.35, 0.20),
    ("To implement a binary search tree, we first define the node class with left and right pointers.", 0.25, 0.1),
    ("The Python list comprehension provides a concise way to create lists from existing iterables.", 0.25, 0.1),
    ("Debugging asynchronous functions requires careful attention to the event loop state.", 0.25, 0.1),
    ("The model architecture utilizes a transformer block with multi-head attention mechanisms.", 0.3, 0.15),
    ("The boss fight in the final level is absolutely punishing without the right build.", 0.35, 0.2),
    ("I've spent hours optimizing my frame rates to ensure a smooth competitive experience.", 0.3, 0.2),
    ("There's something deeply immersive about the open-world design in this title.", 0.35, 0.25),
    ("The meta-game has shifted significantly after the latest patch notes were released.", 0.3, 0.15),
    ("The juxtaposition of postmodern angst against classical structure creates a unique narrative tension.", 0.35, 0.3),
    ("Historically speaking, the Industrial Revolution fundamentally altered the human relationship with labor.", 0.35, 0.25),
    ("One must consider the socioeconomic implications of the proposed legislative framework.", 0.4, 0.2),
    ("The aesthetic qualities of the era were defined by a rigorous adherence to symmetry and balance.", 0.35, 0.25),
    ("His gaze was unyielding, a silent challenge that made my breath hitch in my chest.", 0.25, 0.4),
    ("The air between us seemed to crackle with an intensity I hadn't prepared myself for.", 0.25, 0.45),
    ("I wanted to look away, but his presence was a gravitational force I couldn't escape.", 0.25, 0.4),
    ("He whispered my name, and the sound of it was enough to make the world blur around the edges.", 0.2, 0.5),
    ("There was a raw, unfiltered honesty in the way he looked at me that left me completely undone.", 0.2, 0.5),
    ("I didn't know what he wanted from me, but God help me, I knew I wanted to give it to him.", 0.25, 0.45),
]

def generate_sample(text, stab, styl, index):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": API_KEY}
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": stab, "similarity_boost": 0.85, "style": styl, "use_speaker_boost": True}
    }
    
    mp3_path = OUTPUT_DIR / f"ana_{index:04d}.mp3"
    wav_path = OUTPUT_DIR / f"ana_{index:04d}.wav"
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        with open(mp3_path, "wb") as f: f.write(response.content)
        # Convert to XTTS required format (22050Hz is safest for XTTS)
        subprocess.run(["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "22050", "-ac", "1", "-sample_fmt", "s16", str(wav_path)], capture_output=True)
        mp3_path.unlink()
        return True
    return False

# Generate 200 samples
print("Starting generation of 200 samples...")
for i in range(1, 201):
    base_text, _, _ = SAMPLES[(i-1) % len(SAMPLES)]
    
    # Randomly vary stability and style
    stab = round(random.uniform(0.25, 0.45), 2)
    styl = round(random.uniform(0.1, 0.4), 2)
    
    print(f"Generating {i}/200: [stab:{stab} styl:{styl}] {base_text[:30]}...")
    if generate_sample(base_text, stab, styl, i):
        time.sleep(2.5) 
    else:
        print("Generation failed.")
        break
print("Done!")