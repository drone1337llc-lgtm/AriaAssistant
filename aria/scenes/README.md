# Aria scenes

`Main.tscn` is the production desktop-companion scene. Don't change its
structure casually — it's wired into the C# orchestrator with hard
NodePath references.

`IKDebug.tscn` is a developer tool. Open it in the Godot editor and
press F6 (Play) to run it. You'll see Aria in a normal (non-transparent)
window with a dark background, an orbit camera, and an HUD showing the
live IK state.

## IKDebug controls

| Key            | Effect                                                  |
|----------------|---------------------------------------------------------|
| Left mouse     | `ik_reach` right arm to the clicked point                |
| Shift+Left     | `ik_reach` left arm                                       |
| Right mouse    | `ik_look` (head turns to the clicked point)             |
| R              | Random reach (right arm)                                 |
| L              | Look at a random point near Aria                          |
| T              | `ik_lean` forward, amount 0.6                            |
| Y              | `ik_twist` yaw=30, pitch=-5                              |
| G              | `ik_grip` right hand closed                              |
| H              | `ik_grip` right hand open                                |
| K              | `ik_release_all`                                          |
| F              | Random walk (translates the Aria root as a stand-in)    |
| P              | Play a random animation from the AnimationLibrary      |
| M              | `request_motion` (only logs; no server reachable here) |
| Q / E          | Camera orbit (yaw)                                       |
| W / S          | Camera zoom (dolly)                                      |
| Esc            | Quit                                                     |

Active IK chains are drawn as small cyan spheres at their target
positions, with a red marker at the most recent target. The HUD shows
chain name, target coords, blend mode, and weight.

The scene uses the same `AriaIKController` and `AriaDirective` types
as the production scene, so any bug you see here reproduces in the
main scene.
