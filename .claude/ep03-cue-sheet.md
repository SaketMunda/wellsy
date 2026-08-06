# Episode 3 — the failure episode

## Before you roll

- Rehearse: `http://localhost:5173/?demo=broken&hud=1` — indicator top-left of the viewport.
- **Film: `http://localhost:5173/?demo=broken`** — no indicator. Check the URL bar before you record.
- A normal viewer on `/` gets today's app. No demo code runs, no key listener is attached.

Tune between takes without a rebuild:
`?demo=broken&lag=8&ghost=15&denial=8` (seconds). Everything else lives in
[src/demo/config.ts](../src/demo/config.ts).

## Hotkeys

| key | does |
|---|---|
| `1` | mislabel — the map in `config.ts`, confidence from the map not the model |
| `2` | lag — narration released `lagSeconds` late, original timestamps, boxes stay live |
| `3` | ghost — departed objects leave their box behind for `ghostSeconds`, confidence ticking down |
| `4` | denial — status lines every `denialIntervalSeconds`, **only while another failure is on** |
| `0` | redemption — everything off, next person renders `person 0.99`, one line, hold 4s |
| `9` | all-off reset — modes, ghosts and buffers dropped, cursors rewound |

Keys are ignored inside inputs and when a modifier is held, so `cmd+1` still switches tabs.

## The 60-second run

| t | key | what should be on screen |
|---|---|---|
| 0:00 | — | clean. real labels, real confidence. |
| 0:08 | `1` | mug → `TOILET 91%`, you → `FURNITURE 51%`. log: *a toilet appears. on the desk. bold.* |
| 0:20 | `3` | move the mug out of frame. its box stays, `91 → 90 → 89…`. log: *the toilet remains. (the toilet does not remain.)* |
| 0:32 | `2` | boxes stay instant, log falls ~7s behind with old timestamps and past tense. |
| 0:40 | `4` | *all systems nominal.* over the top of all of it. |
| 0:55 | `0` | everything dies. one amber box, `PERSON 99%`, one line: **person. 0.99. confirmed.** |
| 0:59 | — | hard cut. |

`0` works from any state — the redemption path clears modes, ghosts and the lag
backlog before it arms. The backlog is **discarded**, not flushed: seven seconds
of stale narration dumping over the cut is the one thing that would ruin the shot.
Manually toggling `2` off does flush, so rehearsal doesn't silently eat lines.

If nobody is in frame when you press `0`, it stays armed and fires the moment a
person appears. The box holds even if you step out mid-shot, so the frame never
blinks.

## Where the seams are

Detection is untouched. `useDetector` writes the real frame; the demo layer takes
a copy at display time.

- [src/demo/controller.ts](../src/demo/controller.ts) — all sabotage state. `tick()` is called by the HUD rAF loop and nothing else.
- [src/demo/brokenTemplates.ts](../src/demo/brokenTemplates.ts) — the broken voice. Never hedges, never suspects itself.
- [src/demo/brokenLine.ts](../src/demo/brokenLine.ts) — cursor-based picking, no randomness. Take 4 reads like take 1.
- Narrator reads `demo.current()`, so a mug mislabelled as a toilet is a toilet in the boxes *and* the log.
