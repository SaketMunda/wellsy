# Step 6 — results (in progress)

Branch `rebuild/step6-native-interface`. This is the first increment: the
**honesty backbone** (signal bus + state machine + runtime taps + headless
backend + the honesty test) is done and green; the **Qt Quick backend** is
written but needs an on-device validation pass (no GPU / display in the build
session). What is not yet done is called out under "Owed".

---

## Framework decision — verified, then justified (INVARIANTS #8)

**Chosen: PySide6 / Qt Quick.** Pinned `pyside6>=6.11.2,<6.12`.

Verified 2026-09-03 against `pypi.org/pypi/PySide6/json`:

| version | released |
|---|---|
| **6.11.2** (Qt 6.11.2) | **2026-08-18** ← current |
| 6.11.1 | 2026-05-13 |
| 6.11.0 | 2026-03-23 |
| 6.10.3 | 2026-04-02 |

The step doc's numbers held; they were re-checked, not trusted.

### What was rejected, and why (the one-hour survey)

| Option | Why not |
|---|---|
| **Webview over the desktop** (Electron/Tauri/CEF with per-pixel alpha + click-through) | D54. Fragile on all three platforms, heavy at idle, and the "looks cheap" failure the rebuild exists to end. Every good reference orb is WebGL — the *technique* transfers (see the shader), the *runtime* does not. |
| **Slint** (Rust) | Reintroduces a language boundary. The runtime is Python (LangGraph, Pipecat, the inference seam) and D54 requires in-process, no IPC. Slint's Python binding exists but the ecosystem, shader story, and platform-window control are all thinner than Qt's. |
| **egui / Dear ImGui** | Immediate-mode; great for tools, wrong for a always-on translucent creature. No mature frameless/click-through/per-pixel-alpha story, no scene-graph shader effects. |
| **Godot** (as an embedded view) | A whole second runtime and a process/scene boundary. All of Qt's GPU compositing with none of the in-process Python integration. |
| **Toga / wxPython / Tk** | No GPU scene graph, no per-pixel alpha compositing, no shader effects. Non-starter for the visual bar. |
| **Jetpack Compose Multiplatform / Flutter** | Another language + a platform-channel boundary to the Python runtime. D54. |

Decisive factor, as the teardown says: **not looks — the absence of an IPC
bridge** between the UI and the perception/agent runtime. Qt Quick is the only
mature toolkit that is simultaneously in-process for Python, GPU-composited via
RHI (Metal / Vulkan / D3D), and genuinely cross-platform. Licensing: PySide6 is
LGPLv3 — fine, flagged in `pyproject.toml`.

Portability (INVARIANTS #14): PySide6 ships one wheel per platform from one
codebase — it is **not** platform-exclusive, so it is allowed in the core. It is
kept behind the `[interface]` extra only so the headless runtime, CI, and the
humanoid endgame don't pull a GPU toolkit. The banned-import test stays green;
`("interface", "backends")` was added to `SANCTIONED_DIRS` for the two real
platform shims (macOS NSPanel via pyobjc, Linux layer-shell).

---

## The three platform findings — how they resolved

**1. Qt 6 compiles shaders at build time (no runtime GLSL).**
Handled in hour one. `engine/interface/backends/qt/shaders/orb.frag` is
Vulkan-flavoured GLSL 440; `build_shaders.py` finds `pyside6-qsb` (ships in the
PySide6 wheel — no Qt SDK needed) or `qsb`, and compiles to `orb.frag.qsb`
(SPIR-V + MSL/HLSL/GLSL). `ShaderEffect` loads it by relative file URL.
`wellsy orb --build-shaders` / `--check-shaders` (the CI staleness gate). **Not
yet run** — needs PySide6 installed.

**2. Wayland needs `wlr-layer-shell`, and GNOME/mutter does not implement it.**
`engine/interface/capability.probe()` detects platform + session + compositor
and returns a `PresenceCapability` with per-property booleans and a `degraded`
flag. On GNOME/Wayland (or any Wayland compositor without LayerShellQt) it
reports `degraded=True` with the reason and a documented fallback (X11 session,
or a normal managed always-visible window). `wellsy orb --capability` prints it;
the Qt backend also downgrades honestly at runtime if the NSPanel shim or
layer-shell apply fails. **No silent degradation** — acceptance #2's requirement.
`linux_layershell.py` holds the overlay-layer / no-focus / exclusive-zone-0
apply; validated only by code review so far (no Wayland box in the build session).

**3. macOS needs panel semantics, not window semantics.**
`macos_panel.py` (sanctioned dir, pyobjc allowed) promotes the Qt window's
NSWindow to `NSFloatingWindowLevel+1` with
`canJoinAllSpaces | fullScreenAuxiliary | stationary` and the
non-activating-panel style mask, so the orb survives Spaces switches and rides
over fullscreen apps. The Qt flags
(`FramelessWindowHint | WindowStaysOnTopHint | Tool | WindowTransparentForInput`)
get the rest. **Validated by code review only** — needs a run on this Mac to
confirm the Spaces/fullscreen behaviour and that `winId()` maps to the NSView as
assumed.

---

## What is done and green

| Piece | File | Test |
|---|---|---|
| SignalBus — depth-1 latest-wins, staleness, decay-to-default | `engine/interface/signals.py` | `tests/test_interface_signals.py` (6) |
| State machine — pure `derive_state()`, measured-only | `engine/interface/state.py` | `tests/test_interface_state.py` (10) |
| **The honesty test** — mic closed ⇒ no listening anim, amp 0.0; no bus API and no state path fakes a pulse; stale VAD self-cancels; source scan finds no RNG/timer feeding amplitude | — | `tests/test_interface_state.py` |
| Runtime taps — agent `on_event`, intent `on_decision`, Pipecat observer (VAD-gated mic RMS, output PCM RMS) | `engine/interface/taps.py` | covered via signals/state |
| Headless backend — state as JSONL, self-throttling | `engine/interface/backends/headless.py` | smoke |
| Capability probe | `engine/interface/capability.py` | `--capability` |
| Backend selection | `engine/interface/backends/__init__.py` | smoke |
| `wellsy orb` CLI (`--demo`, `--capability`, `--backend`, `--build-shaders`) | `engine/interface/cli.py` | smoke |
| Portability gate still green, new sanctioned dir | `engine/inference/portability.py` | `tests/test_portability.py` |

Full suite: **186 passed**. `wellsy orb --demo --backend headless` walks
asleep→idle→thinking→acting→awaiting_approval→refusing and back; it structurally
**cannot** enter listening/speaking because there is no bus method that fakes a
VAD/PCM frame — the invariant is visible even in the demo.

### The honesty rule, concretely

`derive_state()` has one reactive-amplitude source: `reactive_amplitude` is
`tts_amplitude` when a fresh PCM sample exists, `vad_amplitude` when a fresh VAD
sample exists, and `0.0` otherwise. `vad_amplitude` has exactly one writer,
`SignalBus.push_vad_amplitude(measured)`, called by `VoiceOrbObserver` only
between `UserStartedSpeaking` and `UserStoppedSpeaking` with the RMS of the live
mic frame. The shader's `uTime` drives only a fixed-magnitude "breathing" warp
(hard-capped at `BREATH_MAX = 0.015` of the radius) that represents "the
pipeline is up"; it never scales `uAmplitude`.

---

## Increment 2 (2026-09-03, same day) — PySide6 installed, orb runs

`uv sync --extra interface` → PySide6 **6.11.2** / Qt **6.11.2**, `pyside6-qsb`
and `pyobjc` present. What now works, verified on this Mac:

| Piece | Evidence |
|---|---|
| **Shader compiles** | `wellsy orb --build-shaders` → `orb.frag.qsb` (4 KB, SPIR-V + MSL/HLSL/GLSL). `--check-shaders` is the CI staleness gate. |
| **Orb renders** | `wellsy orb` opens the QQuickView; Qt smoke walks idle→thinking→acting→awaiting_approval→refusing with no QML warnings and clean teardown. The `WELLSY_ORB_PRINT_CAP=1` line confirms the **NSPanel shim applied** (`.floating+1`, `canJoinAllSpaces \| fullScreenAuxiliary \| stationary`, non-activating). |
| **`--orb` co-run** | `engine/interface/session.py` — `OrbSession` runs the asyncio runtime on a worker thread while Qt owns the main thread; all UI mutations cross via a thread-safe queue drained on the main-thread tick. The worker↔UI **approval relay** (`ApprovalRelay`) blocks the graph on a `threading.Event` that the QML Approve/Deny click sets. Tested headless in `tests/test_interface_session.py` (4 tests). |
| **`wellsy agent --orb`** | wired: graph events → `agent_event_sink` → orb state; a gated step opens the approval HUD and blocks there. Live run reached `plan_node` and the orb loop drove correctly; the planner LLM itself timed out (`qwen3:4b-thinking` — the known step-5b blocker, not this step). |
| **`wellsy voice --orb`** | wired: `build_voice_observer(bus)` as a Pipecat observer + `intent_decision_sink` as `on_decision`; orb `Esc` hops to the voice worker's event loop and queues an `InterruptionFrame` (deterministic stop). Not yet run against a live mic. |
| **CPU budget — MET** | `wellsy orb --profile-cpu` (psutil, 250 ms windows, ÷ncpu, p50/p95, first sample dropped): asleep **p95 0.68%** (budget 1%), acting **p95 0.73%** (3%), HUD **p95 1.00%** (6%). All green. Caveat: the 160×200 window on this display; a larger orb and a busier compositor will cost more — re-profile if the orb grows. |

---

## Increment 3 (2026-09-03) — the orb looks like the reference clip

The owner supplied a reference (`original-c74c…mp4`, 1600×1200, 10 s): a 3D
sphere of ~15–20k particles on latitude rings that **unravels into swirling
ribbon-sheets and re-winds**, cyan → violet → magenta along the streams, hot
fold-flares, additive glow — reads as "computing". The increment-2 orb was a 2D
fbm+Fresnel disc: a different, much simpler thing. This increment rebuilds
Deliverable 1's visual to match.

**Framework dead-end, recorded (INVARIANTS #8, #13):** the intended route —
`QtQuick3D` custom-geometry `PrimitiveType.Points` + a `CustomMaterial` vertex
shader — **renders nothing** on the Metal RHI in PySide6 6.11.2. Every point
collapses to one screen pixel, with a built-in `PrincipledMaterial.pointSize`
*and* with a custom unshaded material, at 4k and 20k points, indexed or not.
No shader-compile error; the vertex input assembly for points just doesn't
deliver per-vertex position. Time-boxed the debugging, then pivoted.

**What shipped instead:** `engine/interface/backends/qt/pointcloud.py` — a
`QQuickPaintedItem`. The point cloud (a golden-angle sphere, ~3.2k points) is
rotated, curl-displaced and perspective-projected in **NumPy each frame**
(~1 ms), then drawn back-to-front as **additively-composited radial-gradient
sprites** (`QPainter.CompositionMode_Plus`) — which gives the glow/bloom look
for free. Colour runs cyan→violet→magenta along each ribbon; depth picks the
sprite size bin; `awaiting_approval` freezes the morph (amber), `refusing`
collapses inward (red). Still Qt scene graph, still in-process, no webview.

The `qsb` shader build step (`build_shaders.py`, `orb.frag`, `--build-shaders`)
is **removed** — it was real and proven in increment 2, but nothing in the
shipping orb is a `ShaderEffect` any more, so carrying it was dead weight. If a
working GPU points route is found later it comes back.

**Honesty binding, unchanged:** `PointCloud.amplitude` ← `bridge.reactive
Amplitude` (measured; 0 without a live VAD/PCM frame) is the only reactive
input — it adds turbulence + brightness on top of the time-driven swirl. `tick`
advances the swirl clock. `state` picks a per-state identity, eased in the item.
No RNG; the displacement is deterministic in `t`. `tests/test_interface_state.py`
still green (the honesty test is on the Python signal layer, unaffected).

**CPU re-profiled** (`wellsy orb --profile-cpu`, same method as increment 2),
adaptive repaint (asleep ~4 fps, idle ~11 fps, active ~60 fps):

| state | p95 | budget | |
|---|---|---|---|
| asleep | 0.88 % | 1 % | OK |
| **idle** | **1.36 %** | 1 % | **OVER by ~0.4 %** |
| acting | 2.91 % | 3 % | OK |
| HUD | 2.64 % | 6 % | OK |

The idle miss is real and honest: a continuously-repainting `QQuickPaintedItem`
has a ~1 % fixed floor (Qt event loop + QPainter setup) that point-count and
frame-rate cuts don't get under. Levers, in order: (a) a working GPU point-sprite
path (removes it entirely — the QtQuick3D bug above, or a hand-rolled
`QSGGeometry` + custom `QSGMaterial` with a `qsb` point shader), (b) render the
idle frame once and pause the pump when nothing changes, (c) drop idle to ~6 fps.
Not chased further this increment.

**Evidence:** `wellsy orb` renders the particle sphere; screenshotted in idle /
thinking / acting / awaiting_approval / refusing / speaking (contact sheet in the
session). It reads as the reference *family* — swirling gradient particle sphere
— but is rougher: the curl field lumps vertically rather than forming the
reference's clean concentric ribbon sheets around a round core, and the
`awaiting_approval` amber doesn't fully land. Art-direction polish, not
architecture.

---

## Increment 4 (2026-09-03) — size, corner placement, voice `--orb` fix

Owner: "it's very tiny — make it ~25 % of the screen, and let me tell it to move
to a corner."

- **Size.** The orb window now defaults to **~25 % of the screen width**
  (`round(screen_width * 0.25)`, clamped 300–720 px; on this Mac 358 px), and
  the point projection was widened (`cz 2.9`, `f = min(w,h)*0.60`) so the sphere
  fills ~85 % of that. `--size PX` / `WELLSY_ORB_SIZE` override; `--screen-
  fraction` / `WELLSY_ORB_FRACTION` change the ratio. Sprite dots scale
  sub-linearly with the orb so a big orb stays dense, not speckled. The auto
  size is re-derived every launch (never persisted) so it follows a display
  change and can't be poisoned by a stale value.
- **Corner placement.** `backend.move_to_corner(name)` and the QML-facing
  `bridge.moveToCorner(name)` slot snap the window to `top-left | top-right |
  bottom-left | bottom-right | left | right | center` against
  `QScreen.availableGeometry()` (menu-bar / dock excluded), 24 px margin,
  persisted. `normalize_corner()` parses loose phrasing —
  "left", "the bottom-right corner of the screen", "move it to the right
  corner", "centre", "right-bottom" — so a voice/text command can call it
  directly. `wellsy orb --corner bottom-right` sets it at launch; while the orb
  runs, typing a corner name on stdin moves it (the same hook a spoken command
  lands on). A manual drag clears the corner snap. Verified: all four corners +
  center position correctly on a 1434×944 work area.
- **`wellsy voice --orb` crash fixed.** Pipecat's `WorkerRunner(handle_sigint=
  True)` calls `loop.add_signal_handler`, which raises `set_wakeup_fd only works
  in main thread` when the voice worker runs off the main thread (which it must,
  under `OrbSession`, because Qt owns main). `build()` / `run()` now take
  `handle_sigint` and the orb path passes `False`; the terminal `Esc`/Ctrl-C
  path is unaffected for the normal `wellsy voice`.
- **CPU re-profiled at 358 px** (`--profile-cpu`, adaptive repaint: asleep +
  idle ~2 fps near-static, active ~45 fps): asleep **0.69 %**, idle **0.68 %**,
  acting **2.69 %**, HUD **~2.7 %** — **all within budget** now. The idle miss
  from increment 3 is closed by treating idle like asleep (near-static repaint);
  the trade is that idle no longer visibly drifts — it comes alive the instant
  any real state fires. Honesty test still green.

### Still owed

0. **Orb art pass** — cleaner curl field (concentric ribbons, rounder envelope),
   the dotted-grid density of the reference, stronger per-state tint separation.
   Idle could regain a slow drift if a GPU point path removes the CPU floor.
1. **Screen-record the orb in each state** on this Mac (acceptance #8), and
   eyeball it over a fullscreen app / across Spaces (acceptance #1).
2. **Live `wellsy voice --orb`** — confirm the pulse tracks real VAD/PCM
   amplitude and `Esc` silences output within the §1 budget; re-measure the §1
   voice rows for zero regression (acceptance #6 — the CPU half is done, the
   latency half is not).
3. **HUD from the agent runtime** — feed `plan` / `verify` / provenance views
   into `sess.show_hud(...)` (only the `approval` view is wired). Exercise
   approve **and** deny end to end into the audit log (acceptance #4, #5).
4. **Global hotkey** to summon the HUD — needs a platform shim (macOS
   `RegisterEventHotKey` / event tap; the click-through orb takes no key focus
   so an in-process `QShortcut` won't see it). Structure noted, not built.
5. **Typed text into the agent entry point** from the HUD (acceptance,
   Deliverable 4) — the CLI path exists; the HUD has no text input yet.
6. **Proper shader build hook** — `orb.frag.qsb` is committed so the orb runs
   out of the box; wire `build_shaders` into a `uv`/pip build step so it is
   regenerated on install rather than tracked.
7. Linux/Wayland (KWin/sway + GNOME) and Windows execution — unchanged from
   increment 1.

### Not from step 6

`tests/test_duplex.py::test_self_echo_filter_drops_echo_keeps_user` fails on
this branch **with the step-6 changes stashed** — a pre-existing failure
(`TimeoutError` in the fuzzy self-echo matcher), unrelated to the interface.
Flagged for whoever owns step 4c.

## Honest read

Too early to say whether it "feels like a creature" — the orb has not rendered
yet. What is real: the thing it will render is now *incapable of lying*. The
state a viewer sees is a pure function of measured runtime signal, proven by a
test that fails if any timer or RNG feeds the pulse. The one thing that already
looks cheap: the value-noise `fbm` in the shader is the cheap 4-octave hash kind
— it will band on a large orb. The reference-quality look wants simplex/curl
noise and probably a real sphere mesh with a Fresnel term, not a 2D disc field.
That is a deliberate hold until the orb renders and the CPU budget is known.
