# Step 6 — The native interface: presence, not an app window

**Read first:** `.claude/rebuild/INVARIANTS.md` (**#6, #13, #14** carry this
step), `.claude/stack-teardown.md` §7 and §12.4 (D54),
`spec/phase1-acceptance.md` §1. **Depends on steps 4, 4b, 5.**
Can run in parallel with 5b — different files, no overlap.

## The vision, in the owner's words

> Something that looks like I'm talking to *something* — not an app. A creature
> floating on my monitor. A graphical animated badge or bot, pulsing like Siri
> when it's listening. And when there's something to show, an interface like
> the ones in Iron Man or Spider-Man.

Two modes, and they are not the same product:

| Mode | When | What it is |
|---|---|---|
| **Presence** | always, by default | A small, borderless, click-through, always-on-top orb. No chrome, no title bar, no dock icon, no window. It reacts to voice. It is the only thing on screen 99% of the time. |
| **HUD** | on demand, when there is content | Panels that unfold *from* the orb — the agent's plan, a tool awaiting approval, a captured frame, the audit trail. Cinematic, but every element is real data. |

The transition between them is the design problem. The HUD must feel like the
orb opening, not a second window appearing.

## Non-negotiable: this is not a webview

Decision D54 stands, and the research reinforces it. Every good reference orb in
the wild is WebGL/Three.js — the technique transfers, the runtime does not.
A browser engine composited over the desktop with per-pixel alpha and
click-through is fragile on all three platforms, heavy at idle, and is exactly
the "looks cheap" failure the rebuild exists to end.

**The UI runs in the engine's own process, on the GPU scene graph, with no IPC
to the runtime.**

## Framework — verified current, then justify

`PySide6` on Qt Quick. Current as of this writing: **PySide6 / Qt 6.11.2,
released 2026-08-18**; 6.10.3 was the previous line. Pin what is current when
you start and record the version (invariant #8 — verify, do not trust this
paragraph's numbers).

Why this and not the alternatives: the runtime is Python (LangGraph, Pipecat,
the inference seam), D54 requires **in-process, no IPC**, and Qt Quick is the
only mature option that is simultaneously in-process for Python, GPU-composited
via RHI (Metal on macOS, Vulkan on Linux, D3D on Windows), and genuinely
cross-platform. Rust toolkits (Slint, egui) and Godot all reintroduce a process
boundary or a language boundary for no gain here.

**Before committing, spend one hour checking whether anything has displaced it**
and write down what you rejected and why. If Qt Quick is chosen, it is chosen
on evidence, not because this document said so.

## The three platform findings that will bite you — handle them up front

**1. Qt 6 compiles shaders at build time. There is no runtime GLSL.**
Qt 6 dropped inline shader strings: you write Vulkan-flavoured GLSL, compile it
to a `.qsb` package with the `qsb` tool (SPIR-V + reflection + translations to
MSL/HLSL/GLSL), and `ShaderEffect` loads the `.qsb` by file or `qrc` URL. This
means **a shader build step is part of the packaging**, and it must work from
`uv`/`pip` install without a Qt developer environment. Solve this in the first
hour, not the last.

**2. Wayland cannot do this with standard protocols.**
`xdg-shell` gives an application no control over its own toplevel placement, so
"always on top, click-through, unmanaged" is unreachable through it. The route
is the `wlr-layer-shell` protocol via **LayerShellQt**. Critical caveat:
**GNOME's compositor (mutter) does not implement layer-shell.** Most others
(KWin, sway, Hyprland) do.

So Presence mode has a real portability hole on GNOME/Wayland. Decide and
document the fallback — X11 session, or a degraded always-visible-but-managed
window — and make the app **detect and say so**, rather than silently rendering
an orb that sinks behind other windows. A capability probe reported honestly is
acceptable; a silent degradation is not (invariant #13).

**3. macOS needs panel semantics, not window semantics.**
A plain always-on-top window disappears when the user enters a fullscreen app or
switches Spaces, because window levels order *within* a Space. The orb needs
`NSPanel` behaviour: floating panel, `.floating` level or above, and a
collection behaviour including `canJoinAllSpaces` and `fullScreenAuxiliary`.
Qt's `Qt::Tool | WindowStaysOnTopHint | WA_TranslucentBackground |
WindowTransparentForInput` gets most of the way; the Spaces and fullscreen
behaviour will likely need a small native shim.

**That shim is permitted.** Invariant #14 bans platform-exclusive APIs *in the
core*; this is a platform backend behind a portable interface, exactly like
ScreenCaptureKit in step 3. Same rule: portable interface, per-platform backend,
banned-import test still green.

## Deliverable 1 — the Presence orb

Borderless, translucent (per-pixel alpha), always-on-top, **click-through by
default** so it never steals a click, draggable to a corner via an explicit
grab affordance, position persisted. No dock/taskbar entry.

Visual technique — take it from the WebGL reference work, implement it in Qt:
a sphere or disc displaced by simplex/Perlin noise, a Fresnel rim so the edge
glows, and colour/intensity driven by real signal. Aim for something that reads
as *alive and breathing* at rest, not a spinner.

## Deliverable 2 — the state machine, and the honesty rule that governs it

The common reference implementations use four states. WELLSY has more, and the
extra ones are the point of this project:

| State | Driven by | Reads as |
|---|---|---|
| Asleep | no wake | dim, slow breath |
| Listening | **the real VAD, live** | pulses with actual mic amplitude |
| Thinking | planner running | motion without amplitude |
| Acting | a tool is executing | distinct from thinking — it is doing, not deciding |
| **Awaiting approval** | the policy gate's `interrupt()` | unmistakable, and it must *stop* and wait |
| **Refusing** | a capture failed verification, a tool was denied | visibly different from an answer |
| Speaking | first PCM sample written | tracks output amplitude |

**The honesty rule — this is invariant #6 extended to pixels:**

> The interface renders measured state. It never animates on a timer.

If the orb pulses to a synthetic waveform while the mic is closed, it is lying
about the system's state, and that is the same class of defect as describing a
wallpaper as a screen. Every animated quantity traces to a real value: VAD
amplitude, output PCM amplitude, graph node, gate decision. Prove it in a test —
mic closed must mean no listening animation, and there must be **no code path
that can produce a listening pulse without a live VAD frame**.

## Deliverable 3 — HUD mode

Unfolds from the orb when there is something to show. Content is real:

- the agent's plan, step by step, with each step's policy decision beside it
- **the approval prompt** — the tool, its arguments, its risk level, its
  reversibility, and Approve / Deny. This is the most important screen in the
  product. It is where the user decides whether to trust WELLSY.
- the read-back verification result (invariant #15) — what it claims it did,
  and what an independent read confirms
- a captured frame with its provenance when vision was used
- the audit trail, and the current autonomy level with *why* it is that level

Cinematic is welcome — depth, glow, motion, translucency. Fabricated readouts
are not. No decorative telemetry, no fake scrolling data, no numbers that aren't
numbers. The Iron Man look, earned honestly, is more impressive than the Iron
Man look faked.

## Deliverable 4 — the input surface

Voice is primary and already exists. Add: a global hotkey to summon HUD mode,
`Esc` mapped to the existing deterministic stop path, and typed text into the
same agent entry point the CLI uses. The CLI must keep working — it is the
headless path, and the humanoid endgame has no monitor at all.

## Performance budget — a hard gate

The voice path idles at **1.3% of the machine** with the pipeline awake. An
always-on animated overlay can trivially cost more than the entire AI. So:

| | budget |
|---|---|
| Presence orb, asleep, idle | **< 1% of the machine**, and it must throttle its frame rate when nothing is happening |
| Presence orb, active (listening/speaking) | **< 3%** |
| HUD open | **< 6%** |
| Regression to voice §1 latency rows | **zero** — re-measure and prove it |

Measure it the way everything else here is measured: `--profile-cpu`, p50/p95,
method recorded. On a laptop, an orb that costs battery gets turned off, and an
interface that is turned off has failed.

## Acceptance

1. Orb runs borderless, translucent, always-on-top, click-through on macOS —
   including **over a fullscreen app and across Spaces**.
2. Linux: works under KDE/sway via layer-shell; under GNOME/Wayland it
   **detects the limitation and reports it**, and the fallback is documented.
   Windows path implemented; execution may be deferred with that stated.
3. Every state above is driven by real runtime signal, with a test proving no
   listening animation is possible without a live VAD frame.
4. The approval gate is reachable, readable, and blocking in the UI — approve
   and deny both exercised end to end, both landing in the audit log.
5. A refusal (screen permission revoked) is visibly distinct from an answer.
6. CPU budgets above met and profiled; §1 voice rows re-measured, no regression.
7. The banned-import portability test stays green; any native code sits behind a
   platform backend.
8. `.claude/rebuild/step6-results.md`, with the framework decision and what was
   rejected, the three platform findings as they actually resolved, the CPU
   profile, and screen-recorded evidence of the orb in each state.

## Report back

Whether it feels like a creature or like an app — your honest read, not a
checklist. And the one thing about it that still looks cheap, because there will
be one.
