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

### Still owed

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
