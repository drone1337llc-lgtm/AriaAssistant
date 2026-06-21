// SpringBoneSimulator.cs — gravity + spring physics for J_Sec_* bones
// (skirt, hair, bust). Runs in the Skeleton3D modifier stack, which fires
// AFTER the AnimationPlayer (and any other AnimationMixer) has applied its
// pose to the skeleton. This is the key fix for the "spring bones are
// invisible" bug: previously this was a Node called manually from
// CharacterController._Process, so the AnimationPlayer stomped our
// SetBonePoseRotation on the same frame. Now we extend SkeletonModifier3D
// and override _ProcessModification(); the Skeleton3D's update process
// calls us AFTER the AnimationMixer, so our pose changes survive.
//
// Skeleton3D bones point along their local Y axis at rest. The animation
// drives each bone's LOCAL rotation; the bone's tail in WORLD space is at:
//   bone_world_position + bone_world_basis * (0, length, 0).
//
// Spring physics: each frame, compute the bone's CURRENT world tail
// ("currentTail"). The bone wants to return to its rest tail position
// ("restTail"). The deviation is converted to a spring force plus gravity,
// integrated into a velocity, and the velocity is added to a new tail
// offset. The bone's WORLD Y axis is then rotated from its current
// direction to (restTail + accumulated offset) - boneHead.
//
// Why the TAIL is the spring anchor (not the HEAD): a bone's HEAD tracks
// its parent exactly (it pivots on the head), so a head-anchored spring
// has zero offset forever and the skirt would look glued to the body. The
// TAIL is the part that swings, so the physics has to act on the tail.

using Godot;
using System.Collections.Generic;

namespace Aria
{
	public partial class SpringBoneSimulator : SkeletonModifier3D
	{
		[Export] public bool Enabled = true;

		// TEMP DIAGNOSTIC — when true, ignore physics and force a big sine sway on
		// every non-root spring bone (±34°). If hair/skirt VISIBLY wave with this
		// on, bone rotations DO drive the mesh and the real spring math is the bug.
		// If nothing moves even with this on, the mesh isn't skinned to J_Sec_*
		// bones (a model/import problem). SET BACK TO false once diagnosed.
		[Export] public bool DebugForceSway = true;

		// Godot 4.6.3: a SkeletonModifier3D's SetBonePoseRotation writes are
		// invoked but don't reach the skinned mesh, whereas writes from a Node's
		// _Process DO (the IK controller proves it). When true, the modifier
		// stack does NOT run the sim; instead CharacterController._Process calls
		// Update(delta) every frame, right after IK. Set false to use the
		// modifier-stack path again if a future Godot build fixes it.
		[Export] public bool DriveFromProcess = false;

		// Physics
		//
		// Tuning notes:
		//   The equilibrium drape position is: GravityY / Stiffness (meters below rest).
		//   For visible but physically realistic secondary motion on a ~1.6m character:
		//     skirt equilibrium  ≈ 9.8 / 35 = 0.28m below rest  ← inside the character bounds
		//     hair equilibrium   ≈ 9.8 / 20 = 0.49m below rest  ← hair drapes visibly
		//     bust equilibrium   ≈ 9.8 / 80 = 0.12m below rest  ← subtle jiggle
		//
		//   PREVIOUS MISTAKE: stiffness was lowered to 4/3/10 (gravity/stiffness = 2.45m/3.27m/0.98m),
		//   which put equilibria UNDERGROUND. The bones were pulled below the floor, invisible.
		//   Always keep GravityY/Stiffness < 0.5m to stay within the character's bounds.
		//
		//   MaxOffset 0.5m caps visible deviation at 50cm so a strong jolt doesn't
		//   shoot the hair through the ceiling. MaxVelocity 8 matches the prior cap.
		[Export] public float GravityY = -9.8f;
		[Export] public float SkirtStiffness = 35f;    // equilibrium = 28cm below rest
		[Export] public float SkirtDamping = 1.5f;
		[Export] public float HairStiffness = 20f;     // equilibrium = 49cm below rest — visible drape
		[Export] public float HairDamping = 1.0f;
		[Export] public float BustStiffness = 80f;     // equilibrium = 12cm below rest — subtle jiggle
		[Export] public float BustDamping = 4.0f;
		[Export] public float MaxOffset = 0.5f;        // cap at 50cm
		[Export] public float MaxVelocity = 8f;

		// Inertia — when the body translates or rotates, the springs should
		// lag behind. Without this, walking/turning leaves the skirt/hair/bust
		// glued to the body because the spring force is only computed from
		// bone rotation, not from the parent's acceleration.
		//
		// We track the skeleton's world-origin velocity (cheap, one Vector3
		// per frame for the whole skeleton) and expose it as a pseudo-force
		// applied to every spring. The applied force is -accel (when the
		// body accelerates +X, the springs experience -X and swing back).
		//
		// InertiaScale lets you dial the effect up or down per category by
		// multiplying the per-bone contribution. 1.0 = physically intuitive;
		// 0 = no inertia (springs only respond to direct bone rotation).
		[Export] public float InertiaScale = 1.5f;
		[Export] public float RotationalInertiaScale = 2.0f;

		// Thigh collision — pushes skirt spring tails OUT of the thigh
		// capsule so the skirt drapes ON the thighs when sitting (instead
		// of clipping through them). Only applies to skirt bones (any
		// spring bone whose anchor bone is a hip or pelvis bone).
		// Thigh radius 0.10u is realistic for Aria's character (her hip
		// bone is ~0.10u from center; her thigh tapers to ~0.06u at the
		// knee). 0.10u is the conservative average.
		[Export] public bool ThighCollisionEnabled = true;
		[Export] public float ThighRadius = 0.10f;

		// Rate-limited per-frame log (one line per ~1.0s) so we can confirm
		// the modifier is being called by the Skeleton3D modifier stack. The
		// log line is independent of any spring motion — it proves the
		// C# override is being invoked. Set LogEverySec = 0 to disable.
		[Export] public float LogEverySec = 1.0f;
		private float _logAccum = 0f;
		private int _invokeCount = 0;

		/// <summary>Total number of times the override has been invoked
		/// (visible to external code for diagnostic purposes).</summary>
		public int InvokeCount => _invokeCount;

		// Per-bone state. Class (not struct) so we can mutate Velocity each frame
		// from a foreach loop without CS1654.
		private class SpringBone
		{
			public int Index;
			public int ParentIndex;
			public Vector3 RestOffsetLocal;   // bone's rest HEAD position in parent's LOCAL space
			public Vector3 RestTailLocal;     // bone's rest TAIL position in parent-LOCAL space (rest + (0,length,0))
			public float Length;              // rest bone length (rest tail - rest head, in parent-local)
			public bool IsRoot;               // root of its chain (driven by parent body bone, not spring)
			public float Stiffness;
			public float Damping;
			public Vector3 Velocity;          // m/s in world space

			// Current spring tail position tracked INDEPENDENTLY from the skeleton.
			// This avoids the problem where GetBoneGlobalPose might reflect the
			// animation reset (rest pose) rather than our spring-simulated rotation.
			// IsNaN (uninitialized) on the first frame; initialized from the bone's
			// animated direction on first use. Updated to newTailWorld each frame.
			public Vector3 CurrentTailWorld = new Vector3(float.NaN, float.NaN, float.NaN);

			public bool TailInitialized => !float.IsNaN(CurrentTailWorld.X);

			public string Category = "skirt"; // "skirt" | "hair" | "bust" — drives which thigh-collision rules apply
			public string Name = "";          // bone name, for debug
		}

		private Skeleton3D _skel;
		private readonly List<SpringBone> _bones = new();
		private bool _initialized;

		// Inertia tracking — frame N's skeleton origin/rotation is compared to
		// frame N-1's to derive linear+angular velocity, then acceleration is
		// applied to springs as a pseudo-force.
		private Vector3 _prevSkelOrigin;
		private Quaternion _prevSkelRot = Quaternion.Identity;
		private Vector3 _skelLinearVel;
		private Vector3 _skelAngularVel;   // axis-angle-ish, magnitude = rad/sec
		private bool _firstFrame = true;

		public override void _Ready()
		{
			// SkeletonModifier3D's GetSkeleton() returns the parent Skeleton3D
			// (or null if we're not parented to one). This is the same skeleton
			// the AnimationPlayer writes to and the one we read from.
			_skel = GetSkeleton();
			if (_skel == null)
			{
				GD.PrintErr("[SpringBone] No parent Skeleton3D — must be added as a child of a Skeleton3D to run in the modifier stack");
				return;
			}
			// Be defensive: explicitly set the parent class's Active flag to
			// true. The C++ field defaults to true, but if anything has touched
			// it before our _Ready runs (e.g. deserialization with default
			// values, a misconfigured C# binding shim), the modifier would
			// early-return in process_modification(). Setting it here ensures
			// the engine actually calls _ProcessModificationWithDelta.
			Active = true;
			// Resolve thigh bones for the collision pass. Standard Mixamo
			// humanoid rig names. If the rig uses something different
			// (e.g. a custom export), the indices stay -1 and collision
			// is a silent no-op.
			int n = _skel.GetBoneCount();
			for (int i = 0; i < n; i++)
			{
				var bn = _skel.GetBoneName(i).ToString();
				if (bn == "J_Bip_L_UpperLeg") _lUpperLegIdx = i;
				else if (bn == "J_Bip_R_UpperLeg") _rUpperLegIdx = i;
			}
			BuildChains();
			_initialized = true;
			GD.Print($"[SpringBone] >>> BUILD v7: GLOBAL-POSE + modifier-list <<<");
			// Diagnostic: list the skeleton's children in order. A SkeletonModifier3D
			// (or the AnimationMixer) running AFTER us would overwrite our J_Sec_
			// writes every frame — the last remaining explanation for "stiff".
			foreach (var c in _skel.GetChildren())
				GD.Print($"[SpringBone] skelchild: '{c.Name}' class={c.GetClass()} isModifier={(c is SkeletonModifier3D)}");
			GD.Print($"[SpringBone] modifier ACTIVE: {_bones.Count} bones, parent={_skel.GetPath()}, active={Active}, influence={Influence}");

			// DIAGNOSTIC: do the skinned meshes actually bind the J_Sec_* bones?
			// If a mesh shows "J_Sec_ binds=0" or points at a different skeleton,
			// that's why rotating those bones never deforms it.
			var searchRoot = _skel.GetParent()?.GetParent() ?? _skel;  // Skeleton3D -> Armature -> Aria
			var meshes = new List<MeshInstance3D>();
			CollectMeshes(searchRoot, meshes);
			foreach (var mi in meshes)
			{
				var skin = mi.Skin;
				if (skin == null) { GD.Print($"[SpringBone] SKINDIAG '{mi.Name}': NO Skin"); continue; }
				int binds = skin.GetBindCount();
				int jsec = 0;
				for (int k = 0; k < binds; k++)
				{
					int b = skin.GetBindBone(k);
					string bn = (b >= 0 && b < _skel.GetBoneCount()) ? _skel.GetBoneName(b).ToString()
								: skin.GetBindName(k).ToString();
					if (bn.StartsWith("J_Sec_")) jsec++;
				}
				GD.Print($"[SpringBone] SKINDIAG '{mi.Name}': binds={binds} J_Sec_binds={jsec} skeleton='{mi.Skeleton}'");
			}

			// DECISIVE DIAGNOSTIC: dump the IMPORTED hair mesh's actual per-vertex
			// bone/weight arrays. SKINDIAG above only counts binds; this measures
			// whether Godot kept the weight VALUES and whether the dominant bone of
			// each vertex resolves to a J_Sec_ skeleton bone. If "dominant J_Sec_"
			// is ~0% here while the source file has 40%, Godot's import dropped them.
			foreach (var mi in meshes)
			{
				if (!mi.Name.ToString().ToLower().Contains("hair")) continue;
				DumpImportedWeights(mi);
			}
			if (ThighCollisionEnabled)
			{
				GD.Print($"[SpringBone] thigh collision: L={_lUpperLegIdx} R={_rUpperLegIdx} radius={ThighRadius}u");
			}
		}

		/// <summary>Walk all bones; group those named J_Sec_* into chains,
		/// attach each chain to its first non-J_Sec ancestor (anchor bone).
		/// CurrentTailWorld on each new SpringBone is intentionally NaN to flag
		/// "uninitialized" — Update() will seed it from the bone direction on
		/// first use.</summary>
		private void BuildChains()
		{
			_bones.Clear();
			int n = _skel.GetBoneCount();
			for (int i = 0; i < n; i++)
			{
				var name = _skel.GetBoneName(i).ToString();
				if (!name.StartsWith("J_Sec_")) continue;

				// Find anchor: walk up parents until non-J_Sec_
				int parent = _skel.GetBoneParent(i);
				while (parent >= 0)
				{
					var pname = _skel.GetBoneName(parent).ToString();
					if (!pname.StartsWith("J_Sec_")) break;
					parent = _skel.GetBoneParent(parent);
				}

				// Stiffness by category. We tag the bone's Category too so
				// the per-frame Update loop can apply per-category logic
				// (e.g. thigh collision only applies to skirt bones).
				float stiff = SkirtStiffness, damp = SkirtDamping;
				string category = "skirt";
				if (name.Contains("Hair")) { stiff = HairStiffness; damp = HairDamping; category = "hair"; }
				else if (name.Contains("Bust")) { stiff = BustStiffness; damp = BustDamping; category = "bust"; }

				// Rest offset: bone's rest position relative to its parent in
				// PARENT'S LOCAL space. Skeleton3D's GetBoneRest returns the
				// rest in PARENT-LOCAL coordinates (the transform of this bone
				// when its parent is at origin). So the origin field of the
				// rest pose IS the rest offset from parent (= bone's rest HEAD
				// position in parent's local frame). For a J_Sec_ bone, the
				// bone's TAIL is the HEAD of its first J_Sec_ child (or, for
				// terminal leaves, the bone's own rest length along the bone's
				// local-Y axis). Use the distance to the first J_Sec_ child if
				// present; otherwise fall back to a 0.05u tip approximation.
				var restLocalToParent = _skel.GetBoneRest(i);
				Vector3 restOffsetLocal = restLocalToParent.Origin;

				// Find this bone's tail in PARENT'S LOCAL SPACE.
				//
				// GetBoneRest(i) gives bone_i's Transform in its parent's local space:
				//   .Origin = bone_i's head in parent-local
				//   .Basis  = bone_i's orientation relative to parent
				//
				// GetBoneRest(firstChild).Origin gives the child's head in BONE_I's local space.
				// To express it in PARENT's local space we apply restLocalToParent:
				//   restTailLocal = restLocalToParent * childRest.Origin
				//
				// Without this transform the stored restTailLocal is in a different
				// coordinate frame from the restTailWorld formula used at runtime,
				// causing the spring to oscillate around the wrong rest position.
				//
				// No-child fallback: 0.05u tip along the bone's own local Y axis,
				// expressed in parent-local space via restLocalToParent.Basis.
				Vector3 restTailLocal;
				int firstChild = _skel.GetBoneCount() > 0 ? FindFirstJSecChild(i) : -1;
				if (firstChild >= 0)
				{
					var childRest = _skel.GetBoneRest(firstChild);
					// childRest.Origin is in bone_i's local space → transform to parent-local
					restTailLocal = restLocalToParent * childRest.Origin;
				}
				else
				{
					// No child: tip is 0.05u along this bone's local Y in parent-local space
					restTailLocal = restOffsetLocal + restLocalToParent.Basis * new Vector3(0, 0.05f, 0);
				}
				float length = (restTailLocal - restOffsetLocal).Length();

				_bones.Add(new SpringBone
				{
					Index = i,
					ParentIndex = parent,
					IsRoot = (parent < 0 || !_skel.GetBoneName(parent).ToString().StartsWith("J_Sec_")),
					RestOffsetLocal = restOffsetLocal,
					RestTailLocal = restTailLocal,
					Length = length,
					Stiffness = stiff,
					Damping = damp,
					Category = category,
					Name = name,
				});
			}
			// Diagnostic: log the per-category bone count so we can confirm
			// the skirt/hair/bust tagging is right after a skeleton change.
			int skirtCount = 0, hairCount = 0, bustCount = 0;
			foreach (var b in _bones)
			{
				if (b.Category == "skirt") skirtCount++;
				else if (b.Category == "hair") hairCount++;
				else if (b.Category == "bust") bustCount++;
			}
			GD.Print($"[SpringBone] {_bones.Count} secondary-motion bones registered (skirt={skirtCount}, hair={hairCount}, bust={bustCount}, parent={_skel.GetPath()})");
			// Print the first 20 bone names so we can confirm what the
			// skeleton actually contains (useful when a bone is renamed
			// and a category ends up empty).
			if (_bones.Count > 0)
			{
				var sampleNames = new System.Collections.Generic.List<string>();
				foreach (var b in _bones)
					if (sampleNames.Count < 20) sampleNames.Add($"{b.Category}:{b.Name}");
				GD.Print($"[SpringBone] sample bones (first 20): {string.Join(", ", sampleNames)}");
			}
		}

		/// <summary>Called by the Skeleton3D's update process AFTER the
		/// AnimationPlayer has applied its pose. Per the Godot 4.3+ design,
		/// the modifier stack runs in child order and is guaranteed to fire
		/// after AnimationMixer, so our SetBonePoseRotation() calls here
		/// are not stomped by the animation this frame.
		///
		/// In Godot 4.6, _ProcessModificationWithDelta(double) is the correct
		/// C# binding name (the no-arg _ProcessModification() is marked obsolete
		/// and the generated source directs to this one). The GDScript side calls
		/// this via its internal _process_modification(delta) virtual.
		///
		/// This method delegates to Update(delta) so external code (e.g.
		/// CharacterController._Process) can also call Update(delta) as a
		/// fallback path if the modifier stack isn't running for some reason
		/// — both paths share the same per-frame state.</summary>
		public override void _ProcessModificationWithDelta(double delta)
		{
			if (!Enabled || !_initialized || _skel == null || _bones.Count == 0) return;
			_invokeCount++;
			if (LogEverySec > 0f)
			{
				_logAccum += (float)delta;
				if (_logAccum >= LogEverySec)
				{
					_logAccum = 0f;
					GD.Print($"[SpringBone] modifier invoked: frame={Engine.GetProcessFrames()} count={_invokeCount} bones={_bones.Count} active={Active}");
				}
			}
			// In Godot 4.6.3 the modifier-stack writes don't reach the mesh, so
			// when DriveFromProcess is set we let CharacterController._Process run
			// the sim instead (its writes DO apply). Avoid double-integration.
			if (!DriveFromProcess) Update(delta);
		}

		/// <summary>Public entry point — runs the spring simulation for
		/// one frame using the given delta. Called either by the
		/// Skeleton3D's modifier stack (_ProcessModificationWithDelta)
		/// or, as a fallback, by CharacterController._Process. The
		/// modifier-stack path is preferred (it runs after the
		/// AnimationPlayer, so its SetBonePoseRotation calls win).
		/// If the modifier stack isn't running for some reason, the
		/// fallback path keeps the springs alive even if it gets
		/// stomped by the next AnimationPlayer tick.</summary>
		public void Update(double delta)
		{
			if (!Enabled || !_initialized || _skel == null || _bones.Count == 0) return;
			float dt = (float)delta;
			if (dt <= 0f || dt > 0.1f) return;   // skip huge frames (e.g. breakpoint)

			// TEMP DIAGNOSTIC: force an obvious oscillation, bypassing physics.
			if (DebugForceSway)
			{
				float ts = Time.GetTicksMsec() / 1000.0f;
				float angle = Mathf.Sin(ts * 3.0f) * 0.6f;   // +/- ~34 degrees
				var rot = new Basis(Vector3.Right, angle);
				foreach (var sb in _bones)
				{
					if (sb.IsRoot) continue;
					// Write the GLOBAL pose, like the VRM addon does. In Godot 4.6
					// a SkeletonModifier3D's LOCAL pose writes don't reach skinning,
					// but global-pose writes do.
					Transform3D gp = _skel.GetBoneGlobalPose(sb.Index);
					gp.Basis = rot * gp.Basis;
					_skel.SetBoneGlobalPose(sb.Index, gp);
				}
				return;
			}

			Transform3D skelGlobal = _skel.GlobalTransform;

			// -- Compute skeleton linear + angular velocity THIS frame -------
			// The first frame is bootstrap (no prior state); treat velocity as
			// zero so we don't fire a huge spurious impulse on frame 2.
			Vector3 newLinearVel;
			Vector3 newAngularVel;
			if (_firstFrame)
			{
				newLinearVel = Vector3.Zero;
				newAngularVel = Vector3.Zero;
				_firstFrame = false;
			}
			else
			{
				Vector3 originNow = skelGlobal.Origin;
				newLinearVel = (originNow - _prevSkelOrigin) / dt;

				Quaternion rotNow = skelGlobal.Basis.GetRotationQuaternion();
				// Angular velocity from quaternion delta: dv = (q2 * q1^-1).GetAxis() * angle / dt
				Quaternion deltaQ = rotNow * _prevSkelRot.Inverse();
				float angle = 2f * Mathf.Acos(Mathf.Clamp(deltaQ.W, -1f, 1f));
				Vector3 axis = deltaQ.GetAxis();
				if (angle > Mathf.Pi) angle -= 2f * Mathf.Pi;  // unwrap
				newAngularVel = axis * (angle / dt);
				if (float.IsNaN(newAngularVel.X)) newAngularVel = Vector3.Zero;
			}

			// Inertial pseudo-force (in world space): when the body accelerates
			// +X, the springs experience an apparent -X and swing back. Same
			// for rotation. These are applied directly as an additional accel
			// term in the spring equation.
			Vector3 linearInertiaWorld = -newLinearVel * InertiaScale;
			Vector3 angularInertiaWorld = -newAngularVel * RotationalInertiaScale;

			// Stash for next frame.
			_prevSkelOrigin = skelGlobal.Origin;
			_prevSkelRot = skelGlobal.Basis.GetRotationQuaternion();
			_skelLinearVel = newLinearVel;
			_skelAngularVel = newAngularVel;

			foreach (var sb in _bones)
			{
				if (sb.IsRoot || sb.Length < 0.001f) continue;   // root follows body; leaves are 0-length

				int i = sb.Index;
				int parent = sb.ParentIndex;
				if (parent < 0) continue;

				// Current world positions
				Transform3D parentWorldPose = _skel.GetBoneGlobalPose(parent);
				Transform3D selfWorldPose = _skel.GetBoneGlobalPose(i);

				// Parent origin in world (skeleton-global -> world)
				Vector3 parentOriginWorld = skelGlobal * parentWorldPose.Origin;
				// Self origin (= bone's HEAD) in world.
				// Reading from GetBoneGlobalPose is correct for the HEAD because the
				// head is fixed by the parent joint — it always reflects the parent's
				// current animated+spring position regardless of our previous
				// SetBonePoseRotation on this bone.
				Vector3 selfOriginWorld = skelGlobal * selfWorldPose.Origin;

				// Rest TAIL of this bone in world (the spring equilibrium point):
				//   restTailLocal is in PARENT-LOCAL space.
				//   GetBoneGlobalPose returns a pose in SKELETON-LOCAL space, not world space.
				//   To get a world-space direction we must apply skelGlobal.Basis as well:
				//     restTailWorld = parentOriginWorld + skelGlobal.Basis * (parentWorldPose.Basis * restTailLocal)
				//   Without skelGlobal.Basis the direction is in skeleton-local space, which
				//   only coincidentally matches world space when the skeleton has no rotation.
				Vector3 restTailWorld = parentOriginWorld
					+ skelGlobal.Basis * (parentWorldPose.Basis * sb.RestTailLocal);

				// CURRENT TAIL: use the STORED spring tail position (not derived from the
				// skeleton's current bone direction). This is critical because:
				//   1. If the AnimationPlayer resets J_Sec_ bones to rest each frame (before
				//      the modifier runs), GetBoneGlobalPose(i).Basis.Y would be the rest
				//      direction → offset = 0 every frame → no spring accumulation.
				//   2. Even if the skeleton IS correct, reading the tail from the bone
				//      direction constrains it to the sphere of radius sb.Length around the
				//      head, which drifts from the spring's "ideal" tail for large offsets.
				// On the first frame for this bone, initialize from the bone's current direction.
				Basis selfWorldBasis = skelGlobal.Basis * selfWorldPose.Basis;
				if (!sb.TailInitialized)
					sb.CurrentTailWorld = selfOriginWorld + selfWorldBasis.Y * sb.Length;

				Vector3 currentTailWorld = sb.CurrentTailWorld;

				// Offset = how far the tail has deviated from its rest (equilibrium) position
				Vector3 offset = currentTailWorld - restTailWorld;

				// Spring: -k*offset - c*v + gravity + inertia
				// linearInertiaWorld: when the body accelerates, springs lag.
				// angularInertiaWorld: when the body rotates, springs lag the
				// rotation too (hair swings the opposite way when you turn).
				// We scale angular inertia per category — hair reacts more
				// visibly to rotation than the bust does.
				float angularCategoryScale = sb.Category == "hair" ? 1.0f
											: sb.Category == "skirt" ? 0.5f
											: 0.3f;  // bust barely moves on turn
				Vector3 gravity = new Vector3(0, GravityY, 0);
				Vector3 inertiaAccel = linearInertiaWorld + angularInertiaWorld * angularCategoryScale;
				Vector3 springAccel = -offset * sb.Stiffness - sb.Velocity * sb.Damping + gravity + inertiaAccel;
				sb.Velocity += springAccel * dt;
				if (sb.Velocity.Length() > MaxVelocity)
					sb.Velocity = sb.Velocity.Normalized() * MaxVelocity;

				Vector3 newOffset = offset + sb.Velocity * dt;
				// Clamp total deviation
				if (newOffset.Length() > MaxOffset)
					newOffset = newOffset.Normalized() * MaxOffset;

				// New tail in world
				Vector3 newTailWorld = restTailWorld + newOffset;

				// Persist the spring state for the next frame. We do NOT rely on
				// reading it back from GetBoneGlobalPose, which may or may not
				// reflect our previous SetBonePoseRotation depending on Godot
				// internals. The stored world position IS the authoritative tail.
				sb.CurrentTailWorld = newTailWorld;

				// Thigh collision (skirt only): push the spring tail OUT of
				// the thigh capsule so the skirt drapes on top of the
				// thighs when sitting, instead of clipping through them.
				// Thigh capsule = line segment from hip joint (head of
				// J_Bip_{L,R}_UpperLeg) to knee joint (tail of UpperLeg),
				// with radius ThighRadius. We check both thighs and push
				// out of whichever is closer.
				if (ThighCollisionEnabled && sb.Category == "skirt")
				{
					Vector3 pushed = PushOutOfThighCapsules(newTailWorld, skelGlobal);
					if ((pushed - newTailWorld).LengthSquared() > 1e-10f)
					{
						newTailWorld = pushed;
						sb.CurrentTailWorld = pushed;  // keep stored position in sync after collision
					}
				}

				// We want the bone's TAIL to land at newTailWorld. The bone's
				// HEAD is fixed at selfOriginWorld (rotating the bone doesn't
				// move the head). So the bone's WORLD Y axis (which points
				// along its length) should become (newTailWorld - selfOriginWorld).
				Vector3 desiredBoneDir = (newTailWorld - selfOriginWorld);
				if (desiredBoneDir.LengthSquared() < 1e-8f) continue;
				desiredBoneDir = desiredBoneDir.Normalized();

				// The bone's CURRENT world Y axis — must use world basis (skelGlobal.Basis * selfWorldPose.Basis),
				// not the raw skeleton-local selfWorldPose.Basis which we already computed as selfWorldBasis above.
				Vector3 currentBoneDir = selfWorldBasis.Y.Normalized();
				if (currentBoneDir.LengthSquared() < 1e-6f) continue;

				// Swing rotation in WORLD space
				Quaternion swingWorld = FromTo(currentBoneDir, desiredBoneDir);

				// Convert world swing to LOCAL swing (apply to the bone's local pose).
				// The bone's local pose is in the parent's LOCAL frame, so we express
				// swingWorld in parent's local frame: swingLocal = parentInv * swing * parent.
				// parentWorldPose.Basis is skeleton-local — we must apply skelGlobal.Basis to
				// get the true world rotation of the parent bone.
				Quaternion parentWorldRot = (skelGlobal.Basis * parentWorldPose.Basis).GetRotationQuaternion();
				Quaternion parentWorldRotInv = parentWorldRot.Inverse();
				Quaternion swingLocal = parentWorldRotInv * swingWorld * parentWorldRot;
				Quaternion currentLocal = _skel.GetBonePoseRotation(i);
				Quaternion newLocal = (swingLocal * currentLocal).Normalized();
				_skel.SetBonePoseRotation(i, newLocal);
			}
		}

		private static Quaternion FromTo(Vector3 from, Vector3 to)
		{
			from = from.Normalized();
			to = to.Normalized();
			float d = from.Dot(to);
			if (d >= 0.99999f) return Quaternion.Identity;
			if (d <= -0.99999f)
			{
				Vector3 axis = Mathf.Abs(from.X) < 0.9f ? Vector3.Right : Vector3.Up;
				return new Quaternion(axis, Mathf.Pi);
			}
			Vector3 cross = from.Cross(to);
			return new Quaternion(cross.X, cross.Y, cross.Z, 1f + d).Normalized();
		}

		// Cached thigh bone indices. Resolved once in _Ready via the
		// standard Mixamo humanoid rig names. If the rig uses different
		// names the indices stay -1 and thigh collision silently no-ops.
		private int _lUpperLegIdx = -1;
		private int _rUpperLegIdx = -1;

		/// <summary>Given a candidate world-space point (typically a skirt
		/// spring tail), push it OUT of either thigh capsule if it's
		/// inside. Returns the original point if it's clear. Used per
		/// frame to make the skirt drape on the thighs when sitting —
		/// without this the skirt springs would push it straight down
		/// through the legs and look glued.</summary>
		private Vector3 PushOutOfThighCapsules(Vector3 worldPoint, Transform3D skelGlobal)
		{
			float r2 = ThighRadius * ThighRadius;
			Vector3 best = worldPoint;
			float bestDelta = 0f;
			// L thigh
			if (_lUpperLegIdx >= 0) ApplyCapsulePush(ref best, ref bestDelta, worldPoint, _lUpperLegIdx, skelGlobal, r2);
			// R thigh
			if (_rUpperLegIdx >= 0) ApplyCapsulePush(ref best, ref bestDelta, worldPoint, _rUpperLegIdx, skelGlobal, r2);
			return best;
		}

		/// <summary>Segment from bone head to bone tail in world space.
		/// If worldPoint is within radius of the segment, push it out by
		/// (radius - dist) along the contact normal. Update `best` only
		/// if this capsule pushes farther than the previous best
		/// (so the closer capsule wins).</summary>
		private void ApplyCapsulePush(ref Vector3 best, ref float bestDelta, Vector3 worldPoint, int boneIdx, Transform3D skelGlobal, float r2)
		{
			if (boneIdx < 0 || boneIdx >= _skel.GetBoneCount()) return;
			Transform3D boneWorld = _skel.GetBoneGlobalPose(boneIdx);
			Vector3 head = skelGlobal * boneWorld.Origin;
			// The bone's tail in world = head + bone's WORLD Y axis * length.
			// boneWorld.Basis is in skeleton-local space; multiply by skelGlobal.Basis
			// to convert to world space (same fix as in the main spring loop).
			// Length from rest pose keeps the capsule stable regardless of animation.
			float restLen = _skel.GetBoneRest(boneIdx).Origin.Length() > 0f
				? _skel.GetBoneRest(boneIdx).Origin.Length()
				: 0.4f; // safe default for the human thigh
			Vector3 tail = head + skelGlobal.Basis * boneWorld.Basis.Y * restLen;
			Vector3 ab = tail - head;
			float abLen2 = ab.LengthSquared();
			if (abLen2 < 1e-8f) return;
			// Closest point on segment (head, tail) to worldPoint
			float t = Mathf.Clamp((worldPoint - head).Dot(ab) / abLen2, 0f, 1f);
			Vector3 closest = head + ab * t;
			Vector3 delta = worldPoint - closest;
			float d2 = delta.LengthSquared();
			if (d2 >= r2) return;  // outside this capsule, no push
			float d = Mathf.Sqrt(d2);
			float push = ThighRadius - d;
			if (push <= bestDelta) return;  // a closer capsule already pushed farther
			// Normal: prefer the radial direction (delta), fall back to bone-Y if degenerate.
			Vector3 normal = d > 1e-4f ? delta / d : boneWorld.Basis.Y;
			best = worldPoint + normal * push;
			bestDelta = push;
		}

		/// <summary>Dump the imported mesh's actual per-vertex bone/weight arrays
		/// and report how many vertices are DOMINANTLY (max-weight) bound to a
		/// J_Sec_* skeleton bone. This is the ground-truth check that the source
		/// rig (40% dominant J_Sec_) survived Godot's import and binds to the
		/// right skeleton bones. Maps each vertex's dominant bone-palette slot
		/// through the mesh's Skin (or the skeleton's default skin) to a real
		/// skeleton bone name.</summary>
		private void DumpImportedWeights(MeshInstance3D mi)
		{
			if (mi.Mesh is not ArrayMesh am) { GD.Print($"[SpringBone] WEIGHTDIAG '{mi.Name}': mesh is not ArrayMesh ({mi.Mesh?.GetType().Name ?? "null"})"); return; }
			var skin = mi.Skin;
			int bindCount = skin?.GetBindCount() ?? 0;

			// Resolve a bone-palette slot -> skeleton bone name. With a Skin, the
			// mesh's bone indices index into the Skin's binds; without one, they
			// index skeleton bones directly.
			string SlotToBone(int slot)
			{
				if (skin == null)
					return (slot >= 0 && slot < _skel.GetBoneCount()) ? _skel.GetBoneName(slot).ToString() : $"#{slot}";
				if (slot < 0 || slot >= bindCount) return $"bind#{slot}";
				int b = skin.GetBindBone(slot);
				if (b < 0) b = _skel.FindBone(skin.GetBindName(slot));
				return (b >= 0 && b < _skel.GetBoneCount()) ? _skel.GetBoneName(b).ToString() : skin.GetBindName(slot).ToString();
			}

			for (int s = 0; s < am.GetSurfaceCount(); s++)
			{
				var arrays = am.SurfaceGetArrays(s);
				var verts = arrays[(int)Mesh.ArrayType.Vertex].As<Vector3[]>();
				var bones = arrays[(int)Mesh.ArrayType.Bones].As<int[]>();
				var weights = arrays[(int)Mesh.ArrayType.Weights].As<float[]>();
				if (verts == null || bones == null || weights == null || verts.Length == 0)
				{
					GD.Print($"[SpringBone] WEIGHTDIAG '{mi.Name}' surf{s}: missing arrays (v={verts?.Length},b={bones?.Length},w={weights?.Length})");
					continue;
				}
				int infl = bones.Length / verts.Length;   // 4 or 8
				int domJSec = 0, anyJSec = 0;
				for (int v = 0; v < verts.Length; v++)
				{
					int baseI = v * infl;
					float jsecSum = 0f, maxW = -1f; int maxSlot = -1;
					for (int c = 0; c < infl; c++)
					{
						float w = weights[baseI + c];
						int slot = bones[baseI + c];
						if (w > maxW) { maxW = w; maxSlot = slot; }
						if (w > 0.01f && SlotToBone(slot).StartsWith("J_Sec_")) jsecSum += w;
					}
					if (jsecSum > 0.01f) anyJSec++;
					if (maxSlot >= 0 && SlotToBone(maxSlot).StartsWith("J_Sec_")) domJSec++;
				}
				GD.Print($"[SpringBone] WEIGHTDIAG '{mi.Name}' surf{s}: verts={verts.Length} infl={infl} " +
						 $"anyJSec={anyJSec} ({100f * anyJSec / verts.Length:F0}%) domJSec={domJSec} ({100f * domJSec / verts.Length:F0}%) " +
						 $"[source rig had ~53% any / ~40% dominant]");
			}
		}

		/// <summary>Recursively collect MeshInstance3D nodes under a root (for the
		/// skin-binding diagnostic).</summary>
		private static void CollectMeshes(Node n, List<MeshInstance3D> outList)
		{
			if (n is MeshInstance3D mi) outList.Add(mi);
			foreach (var c in n.GetChildren()) CollectMeshes(c, outList);
		}

		/// <summary>Find the first child bone of `parentIdx` whose name starts with
		/// "J_Sec_". Returns -1 if none (terminal spring bone — use default tip).</summary>
		private int FindFirstJSecChild(int parentIdx)
		{
			int n = _skel.GetBoneCount();
			for (int i = 0; i < n; i++)
			{
				if (_skel.GetBoneParent(i) == parentIdx &&
					_skel.GetBoneName(i).ToString().StartsWith("J_Sec_"))
					return i;
			}
			return -1;
		}
	}
}
