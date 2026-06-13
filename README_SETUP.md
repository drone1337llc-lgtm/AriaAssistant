# AriaCompanion — Godot Setup Checklist

> **Heads up (updated 2026-06-13):** the animation list in this file is from the
> old embedded-GLB pipeline and is out of date. Animations are now retargeted at
> runtime from the FBX files in `res://ani/` by `scripts/AnimationBuilder.cs`
> (see the `AnimSources` map on the AnimationBuilder node in `Main.tscn`). For the
> AI brain, voice (Coqui XTTS), facial expressions, self-healing, and the daily
> fine-tune loop, read **`docs/ARIA_AI_SETUP.md`**. For what changed in the latest
> pass, see **`docs/CHANGELOG_2026-06-13.md`**.

When you open this project for the first time, Godot needs to do a few things before Aria will walk. Follow this in order.

---

## Step 1: Open the project

1. Open Godot 4.6.3 (Mono / .NET build)
2. **Import** → navigate to `C:\Users\Tench\Documents\AriaCompanion` → double-click `project.godot`
3. Wait for first-time import to finish (may take 30-60s — Godot is compiling C# assemblies and importing the .glb/.vrm)

If you see errors in the output panel about missing addons, your `addons/vrm` and `addons/Godot-MToon-Shader` plugins are already enabled in `project.godot`, so you should be fine.

## Step 2: Verify Aria.glb imported correctly

1. In the **FileSystem** dock (left side), navigate to `Aria.glb`
2. Double-click it to open the imported scene
3. You should see a scene tree like:
   ```
   Armature
   ├── char1 (MeshInstance3D)
   ├── Hips (BoneAttachment3D, or a Skeleton3D wraps it)
   │   ├── LeftUpLeg
   │   │   └── ...
   │   └── ...
   └── AnimationPlayer   ← THIS is the magic node
   ```
4. Click the AnimationPlayer. In the bottom panel you should see an animation list with all 27 names:
   `idle, walk, climb, fall, surprised, react, sit_doze, running, walking_w, excited_walk, climb_down, climb_left, fall_long, jump, leap, talk_passion, talk_hip, talk_raised, walk_turn, you_groove, chair_sit, sit_to_stand, swim_idle, swim_fwd, dive, mirror, walk_to_sit`
5. Click "walk" and hit the play button (▶) at the top of the animation panel. Aria should do a walking motion in the viewport.

**If you see NO AnimationPlayer under Armature:** the .glb import is broken. Delete the import files:
- `C:\Users\Tench\Documents\AriaCompanion\.godot\imported\Aria.glb-*.sample` (any cached samples)
- `C:\Users\Tench\Documents\AriaCompanion\Aria.glb.import` (the import metadata)

Then re-import: right-click Aria.glb in the FileSystem dock → **Reimport**.

## Step 3: Set the AnimationPlayer's root_node

This is critical — without it, the bone paths in the animation tracks won't resolve, and Aria will stay in T-pose while "walking" across the screen (the bug you originally reported).

1. In the imported Aria scene, click the **AnimationPlayer** node
2. In the **Inspector** dock (right side), find the **Root Node** property (it's a `NodePath`)
3. Set it to `..` (parent — which is `Armature`)
4. **File → Save** the imported scene (or just close it; changes auto-save)

This tells Godot: "when this animation says 'rotate Hips/LeftUpLeg/LeftLeg/...', look for those bones under Armature, not under the AnimationPlayer itself."

## Step 4: Open Main.tscn and check the scene

1. In the FileSystem dock, navigate to `scenes/Main.tscn` and double-click
2. The scene should look like:
   ```
   Main
   ├── WindowDetector
   ├── LLMBridge
   ├── CharacterController (Node3D)
   │   └── Aria (instance of Aria.glb)
   ├── Camera3D
   ├── DirectionalLight3D
   └── UI
       └── SpeechLabel
   ```
3. **Notice:** there is NO `AnimationPlayer` as a sibling of `Aria` anymore. The AnimationPlayer lives INSIDE the Aria instance, at `Aria/Armature/AnimationPlayer`.

## Step 5: Run the project

1. Press **F5** (or click the play button in the top-right)
2. Check the **Output** panel (bottom). You should see lines like:
   ```
   [Aria] AnimationPlayer has 1 libraries: [default]
   [Aria]   Library 'default': 27 animations: [idle, walk, climb, fall, surprised, react, ...]
   ```
3. Aria should appear as a window on your desktop, standing on the taskbar, then start walking around / climbing on other windows after 3-8 seconds.

---

## Troubleshooting

### "Could not find any AnimationPlayer in the imported Aria.glb"
The animation is not being detected. Check:
- Did you set the AnimationPlayer's `root_node` to `..`? (Step 3)
- Does the imported scene have the AnimationPlayer visible? (Step 2.3)
- Check the **Mesh** panel of the imported Aria.glb scene in the FileSystem dock — the GLB importer should show "27 animations" in the preview

### Aria is frozen in T-pose, sliding across the screen
This means the animation tracks can't find the bones. Go back to **Step 3** and make sure `root_node` is set correctly.

### Aria is visible but walks with feet sliding
The walk animation moves the feet through a 1-second cycle but your code moves Aria at 90 px/sec. The walk cycle's foot plant is at 1-second intervals, so the foot should "land" every 90 pixels. If she slides, either:
- Change `WalkSpeed` in the Inspector (try 30, 60, 120)
- The walk cycle's root motion isn't being applied (we don't have root motion enabled). This is a polish thing, not a blocker.

### Aria appears untextured / pink / missing materials
The MToon shader plugin might not be applied to the imported mesh. To fix:
1. Click on the `char1` MeshInstance3D inside the Aria scene
2. In the Inspector, look at the **Material Override** or **Surface Material Override**
3. The material should be using the MToon shader. If it's StandardMaterial3D, the texture is showing without toon shading.
4. To use MToon: click the Material → in shader dropdown, pick "MToon" → re-assign the base color texture

This is purely cosmetic — Aria will still move correctly without MToon, just with regular PBR shading instead of anime-style.

### The window doesn't show or shows black
Check the **Camera3D** position. It should be at `(0, 0.85, 2.3)` looking at the origin. The viewport is 300×600 px.

### LLM doesn't respond
Check `LLMBridge.cs` — the URL is hardcoded to `http://192.168.68.88:1010/v1/chat/completions`. If your LM Studio is on a different IP or port, change the `LMStudioUrl` field on the LLMBridge node in the Inspector.

---

## What's where

| What | Where |
|---|---|
| Aria model + 27 animations | `Aria.glb` (project root) |
| Main scene | `scenes/Main.tscn` |
| Movement + state machine | `scripts/CharacterController.cs` |
| Window edge detection | `scripts/WindowDetector.cs` |
| LLM bridge (LM Studio) | `scripts/LLMBridge.cs` |
| Main script (orchestrator) | `scripts/Main.cs` |
| Merge tool that built Aria.glb | `C:\...\astro_assistant\merge_aria_animations.py` |
| Original animation sources | `C:\Users\Tench\Desktop\AriaPart[1-4]Animations\Meshy_AI_biped\` |
| Backup VRoid source | `Aria.vrm` (project root, same as `C:\Users\Tench\Pictures\Aria\Aria.vrm`) |

---

## Animation map (what each state plays)

| State | Plays | Duration | Notes |
|---|---|---|---|
| Idle | `idle` (Sit_Cross_Legged, 9.57s) | 9.57s | Long idle loop. Will sit cross-legged. |
| Walk | `walk` (Walking, 1.03s) | 1.03s | Classic walk cycle. Loops. |
| Climb | `climb` (climbing_up_wall, 2.0s) | 2.0s | Climbing up a wall. |
| Fall | `fall` (Fall2, 0.7s) | 0.7s | Quick falling loop. |
| React / surprised | `surprised` (Hop_with_Arms_Raised, 2.37s) | 2.37s | Used both for the React state and for surprised events. |
| React | `react` (Wave_for_Help_4, 4.73s) | 4.73s | Used when LLM responds. (Currently PlayAnim is called with "surprised" in EnterReact — you can change that to "react" or any other animation you like.) |

**To swap animations:** edit `CharacterController.cs` and change the strings in the `Enter*` methods. Or right-click in the AnimationPlayer and rename the animation to match what the code calls.

**To make the controller use a more standing-up idle (instead of cross-legged sitting):** in `EnterIdle()`, change `PlayAnim("idle")` to `PlayAnim("walking_w")` or any subtle motion you prefer.
