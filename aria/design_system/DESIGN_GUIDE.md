# AstroBud Design System

> _"Who knows where she came from, or if she might brick your computer — but hey, at least she's cute."_

AstroBud is a **local, offline-first desktop AI companion** for Windows. She lives
on your desktop (and in your system tray), watches your screen, remembers what you
worked on, talks back in a cheerful voice, and reacts with little glowing moods.
She runs entirely on your own machine against a local LLM (LM Studio) and a local
voice model (Coqui XTTS) — no cloud required, with a graceful Claude fallback.

This design system captures AstroBud's real visual language — the **deep-space
glass**, the **state-color glow** that encodes her mood, the **speech bubble**, and
the gleefully over-engineered "control matrix" UI — so anyone can build on-brand
AstroBud surfaces.

---

## The products represented

AstroBud is one personality wearing three pieces of software. All three were
provided as read-only local codebases (see **Sources** below).

| Surface | What it is | Stack | Where the design lives |
|---|---|---|---|
| **The Companion (overlay)** | The floating on-desktop character: a sprite that bobs, a speech bubble, an "Ask me anything…" chat bar, a right-click menu, and a colored glow that changes with her state. | Python · PyQt6 | `astro_assistant/astrobud_overlay.py` |
| **The Control Matrix (dashboard)** | The settings cockpit — pick neural profiles, set her helpfulness level, watch "vector sandbox logs," manage storage, review flagged bugs. | Python · Streamlit | `astro_assistant/dashboard.py` |
| **The 3D Companion (Aria)** | A walking, sitting, dancing VRoid character who roams your desktop, with AI brain, voice, and facial expressions. | Godot 4 · C# | `AriaCompanion/` |
| **The Voice** | Coqui **XTTS-v2** voice-cloning fork that gives her a custom spoken voice. | Python · PyTorch | `Coqui-TTS-XTTS-v2-/` |

**Two names, one character.** The product is **AstroBud**; the embodied 3D
character is **Aria**. The overlay can also load *swappable character skins*
(it shipped with third-party ones — see caveat below).

---

## ⚠️ Important asset caveats — READ THIS

1. **No brand mascot render exists in the source.** Aria (the real character) is a
   VRoid/VRM model — the only image files are **UV texture atlases**, not usable
   portraits. So this system ships an **original abstract "companion sprite" mark**
   (`assets/astrobud-mark.svg`) built in AstroBud's own glow language. **If you have
   a clean Aria render (transparent PNG), send it — it should become the mascot.**
2. **The bundled character skins are copyrighted third parties** — the overlay's
   `characters/` folder contained **Sony's _Astro Bot_** and **Nintendo's _Zelda_**.
   These are *not* AstroBud brand assets and are deliberately **excluded**. Do not
   reproduce them. They illustrate only that the companion supports swappable skins.
3. **Fonts are substitutions.** The apps render in **Segoe UI** (Windows system
   font). For web we use **Nunito** (UI/body stand-in for Segoe UI) and **Baloo 2**
   (cute rounded display). Swap if a real brand font is specified.

---

## Sources (provided as read-only local folders)

- `AI Learning/astro_assistant/` — Python backend + PyQt6 overlay + Streamlit
  dashboard. Key files read: `README.md`, `config.json`, `dashboard.py`,
  `astrobud_overlay.py`, `characters/*/manifest.json`.
- `AriaCompanion/` — Godot 4 / C# desktop 3D companion. Key files:
  `docs/ARIA_AI_SETUP.md`, `docs/CHANGELOG_2026-06-13.md`, `scripts/*.cs`.
- `Coqui-TTS-XTTS-v2-/` — XTTS-v2 voice-cloning fork (`data/astrobud_voice/`).
- `AI Learning/aria_dataset.jsonl` — captured companion dialogue (persona/tone).

---

## CONTENT FUNDAMENTALS

AstroBud speaks in **two registers**, and keeping them apart is the whole game.

### 1. The Companion voice — warm, tiny, a little chaotic
This is what *she* says, out loud, in 1–2 short sentences (everything is spoken via
TTS, so it must be short).

- **Person:** First person, talking *to* you. "I'm Aria, your new anime companion!"
- **Tone:** Cheerful, affectionate, low-key clingy in a cute way. She calls you
  _friend_ and _buddy_. "Hi again, friend!" · "Hey buddy, ready for some fun?"
- **Robot flair:** AstroBot persona drops `beep boop`; the README persona chirps in
  `*bloop*` and `*whir*`. Use sparingly, as seasoning — never every line.
- **Ambient company:** She fills silence gently, never naggy. _"It's so peaceful
  when you're not typing away; I hope everything is going well!"_
- **Screen-aware asides:** Light, observational, offers help without pushing.
  _"Ah, Claude's got you working hard today, huh?"_
- **Length:** Hard cap ~1–2 sentences. If it wouldn't sound natural spoken aloud in
  4 seconds, it's too long.
- **Emotion is data.** Every line carries an `emotion` (joy/neutral/…) and an
  `action` (wave/none/…). Copy and mood travel together.

### 2. The System voice — gleeful technobabble
The dashboard narrates itself like the bridge of a starship that's mostly held
together with hope. This is deliberate, affectionate over-engineering.

- **Casing:** Title Case Control Panels. "Core Neural Profiles," "System
  Directives," "Assistance Matrix Levels," "Dynamic Storage Threshold Metrics."
- **Inflate the mundane:** a settings save becomes _"AstroBud parameters
  synchronized!"_; clearing temp files is the _"Memory & Storage Optimization
  Center"_; logs are the _"Live Vector Sandbox."_
- **Friendly status, never cold errors:** _"AstroBud is active and scanning
  environmental nodes."_ / _"AstroBud is resting."_ Failures stay gentle and
  fixable: _"LM Studio unreachable."_
- **Emoji are load-bearing.** The control panel is emoji-forward — every header and
  button leads with one (🤖 ⚙️ ⚡ 💡 📊 🧹 🐛). This is on-brand, not noise.
- **Exclamation, yes. Snark, no.** It's enthusiastic, never sarcastic at the user.

### Quick do / don't
- ✅ "AstroBud is active and scanning environmental nodes." ✅ "Hi again, friend!"
- ✅ "Memory & Storage Optimization Center" ✅ "*bloop* — all synced!"
- ❌ "Settings saved." (too flat) ❌ A 3-sentence spoken line (too long for TTS)
- ❌ Cold stack-trace errors shown to the user. ❌ Emoji in the Companion's *spoken* text.

---

## VISUAL FOUNDATIONS

AstroBud's look is **"a cute robot living inside dark glass."** Everything is a
translucent navy panel floating in space, rimmed with a faint blue light, and the
*one* thing that changes color is her mood.

**Color & vibe.** The world is deep-space navy (`#05060F` → `#08091C`), almost
black-blue. Text and frost are cool whites with a periwinkle tint (`#F5FAFF`,
`#E8EEFF`, `#D0D8FF`). The single interactive accent is **cornflower blue**
(`#6496FF`, hover `#78AAF0`). Imagery skews cool, glossy, and softly glowing —
think chrome-and-LED, never warm or grainy.

**The state-glow system (the signature).** The companion is wrapped in a colored
drop-shadow halo whose **hue encodes her state**, and whose intensity rises with
engagement (exactly as in `astrobud_overlay.py`):
- 🔵 **Idle** — `#5082FF`, alpha .39 (resting blue)
- 🩵 **Listening** — `#50C8FF`, alpha .55 (cyan)
- 🟡 **Thinking** — `#FFC83C`, alpha .63 (amber)
- 🟢 **Speaking** — `#50FF96`, alpha .70 (green)
- 🔴 **Offline/Fault** — `#FF5C6E` (coral)

All glows are `0 6px 35px <state>` — a big, soft, downward halo. Reuse this hue
language everywhere: status pills, focus states, log severities.

**Type.** Native apps use **Segoe UI**. Web: **Baloo 2** (chunky rounded) for the
wordmark and big headings — it carries the "cute"; **Nunito** for UI/body; **JetBrains
Mono** for logs, config, hotkeys and the technobabble micro-labels (uppercase,
`letter-spacing: .14em`).

**Surfaces, borders, corners.** Cards are translucent dark-navy glass
(`rgba(8,9,28,.82)`) with `backdrop-filter: blur(18px)`, a **1px periwinkle border**
(`rgba(150,170,255,.28)`), and generously rounded corners — measured radii are **8px**
(inputs), **10px** (menus), **12px** (panels), **14px** (speech bubble & big cards).
No hard right angles; nothing sits flat on a white page.

**Shadows.** Two kinds only: a soft black panel shadow (`0 6px 35px rgba(0,0,0,.45)`)
for depth, and the colored **glow** for life. Speech bubbles get a lighter cool
shadow (`0 8px 24px rgba(20,24,60,.25)`). No inner shadows, no harsh edges.

**The speech bubble.** Cool near-white (`rgba(245,250,255,.92)`), `14px` radius,
periwinkle border, a **downward tail** pointing at the character, navy ink
(`#1A1A2E`), and a **typewriter reveal** (~3 chars / 22ms). It floats just above her
head and follows it.

**Backgrounds.** No gradients-as-decoration and no busy imagery. The default canvas
is near-black space; the only "texture" is the glow bleeding from panels and the
companion. Glass + blur does the heavy lifting.

**Motion.** Gentle and organic, never snappy. The companion **floats** on a sine
wave (`sin(t·0.85)·7px`); speaking adds a fast micro-bob, thinking a slower sway.
Text types on. Hovers brighten (raise the blue/alpha a notch); the send button goes
`#6496FF → #78AAF0`. Presses don't shrink — they deepen color. Focus = the cornflower
ring (`0 0 0 3px rgba(100,150,255,.35)`). Respect `prefers-reduced-motion`.

**Transparency & blur.** Used constantly — this is a desktop *overlay*, so panels are
semi-transparent dark glass that let the desktop show through, unified by backdrop
blur. Chat field is the faintest wash (`rgba(255,255,255,.05)`).

**Layout rules.** The companion pins to a screen corner and stays **always-on-top**;
the bubble sits above her, the chat bar below. Dashboards are wide two-column control
panels. Hit targets stay comfortable; spacing rides a 4px scale.

---

## ICONOGRAPHY

AstroBud has a **split icon strategy**, and both halves are intentional.

1. **Emoji are the brand's primary iconography.** The Streamlit control panel is
   emoji-forward — every section header and button is led by one, and they carry
   meaning: 🤖 (AstroBud), ⚙️ Core Neural Profiles, ⚡ System Directives,
   💡 Assistance Matrix, 📊 logs/metrics, 🧹 storage, 🐛/🐞 bug log, 🔌 server,
   🌐 network, 🌙 sleep, 🟢/🔴 status, ✅/💾/🗑️/♻️/📤/📄/🔄 actions, ⌨️ hotkeys,
   🏷️ category, 🏁 boot, 📥 load. **Use the platform's native emoji** — don't
   recreate them as SVG. They set the playful, approachable tone.
2. **A clean line set for fine UI chrome.** Where emoji would be too loud (toolbar
   glyphs, chevrons, close/▸ arrows, the send arrow `→`), use a thin-stroke line
   icon set. There was no icon font in the source, so this system **substitutes
   [Lucide](https://lucide.dev)** (1.5–2px stroke, rounded caps) loaded from CDN —
   _flagged as a substitution._ It matches the soft, rounded, glassy feel.
3. **Unicode as micro-glyphs.** The overlay literally uses `→` for "send" and `▸`
   for menus. Lean on simple unicode arrows/dots for tiny affordances.
4. **The companion mark.** `assets/astrobud-mark.svg` — the original glowing-sprite
   logo (rounded glass head, cyan LED eyes, antenna). Use it as app icon / wordmark
   lockup. **Never** substitute it with the copyrighted skins.

---

## Index / manifest

**Root**
- `styles.css` — global entry point (consumers link this). `@import`s only.
- `readme.md` — this guide.
- `SKILL.md` — Agent-Skills wrapper for Claude Code.

**Tokens** (`tokens/`) — all `@import`ed by `styles.css`
- `colors.css` · `typography.css` · `spacing.css` (radii, shadows, glow system) · `fonts.css`

**Assets** (`assets/`)
- `astrobud-mark.svg` — original companion logo mark.

**Foundation cards** (`guidelines/`) — specimens shown in the Design System tab
(Type · Colors · Spacing · Brand groups).

**Components** (`components/`) — reusable React primitives (see each `.prompt.md`):
- `core/` — Button, StatusPill, Badge, Toggle, Slider, Select, GlassPanel, Metric
- `companion/` — SpeechBubble, CompanionMark (state-glow sprite), Kbd

**UI kits** (`ui_kits/`)
- `companion_overlay/` — the floating desktop companion (bubble + chat + glow + menu).
- `control_matrix/` — the Streamlit-style settings dashboard recreated for web.

_See SKILL.md and each kit's README for usage._
