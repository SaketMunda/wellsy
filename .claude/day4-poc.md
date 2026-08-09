# Day 4 POC — local LLM + local TTS, verified

## The claim being verified

D10 committed to a local LLM and a local TTS engine, no cloud, ever, sized
for mobile. Day 4's job was to actually build and run both behind the
existing `LineGenerator` and `speech.ts` seams, prove the narration sampler
never blocks on either, and verify the "downloaded once, cached, then fully
offline" claim for real — not just typecheck it.

## What works, verified

1. **`src/narration/llmLineGenerator.ts`** — WebLLM (`@mlc-ai/web-llm`),
   model `Qwen2.5-0.5B-Instruct-q4f16_1-MLC`, dynamically imported (never in
   the main bundle). `LineGenerator.prefetch(event)` starts a chat completion
   the moment an event is queued; `generateLine`/`foldLine` stay fully
   synchronous, reading a cache and falling back to the template generator if
   the LLM line isn't ready, was rejected by the character filter, or the
   model never loaded (no WebGPU). See decisions.md D13 for the full design
   rationale.
2. **`src/narration/speech.ts`** — local neural TTS (`kokoro-js`, Kokoro-82M,
   `dtype: "q8"`), dynamically imported, behind the same `speak`/
   `stopSpeaking`/`primeSpeech`/`pickVoice` surface as `speechSynthesis`.
   Playback via Web Audio (`AudioBufferSourceNode`) so `stopSpeaking()`
   actually cuts off in-flight synthesis. `system` (`speechSynthesis`) stays
   the default and the automatic fallback on any local-tts failure.
3. **Config + UI.** `NarratorConfig.line_generator_engine`
   (`template`/`local-llm`) and `.voice_engine` (`system`/`local-tts`), both
   defaulting to the zero-download option. Toggled live from `StatusPanel`,
   which also shows load state/progress and last-inference/last-synth
   latency for whichever engine is active — see "Measured" below for real
   numbers pulled from these exact fields.
4. **Bundle discipline.** `npm run build`: main chunk (`index-*.js`) is
   still ~1.31MB, unchanged from the pre-Day-4 baseline. `@mlc-ai/web-llm`
   (`lib-*.js`, ~6.0MB) and `kokoro-js` (`kokoro-*.js`, ~2.2MB) both land in
   their own chunks, loaded only when their engine is selected.

## Verification method

- **Read** `decisions.md` (D1, D10 binding), `week-roadmap.md`/`tasks.md`
  Day 4 sections, `architecture.md`, `public-notes.md`, and the whole of
  `src/narration/` before writing anything, per the session brief.
- **Package research before committing to a model:** inspected
  `@mlc-ai/web-llm`'s actual prebuilt catalog (`node_modules/@mlc-ai/web-llm/
  lib/index.js`) for real `vram_required_MB` numbers rather than picking a
  model off a README — Qwen2.5-0.5B-Instruct-q4f16_1 (944.62 MB,
  `low_resource_required: true`) is the smallest instruct model WebLLM
  currently ships. Same approach for `kokoro-js` (read its README + type
  defs for the `dtype`/`device` options before choosing `q8`/`wasm`).
- **Unit tests**, fake models only, no real download in CI: 48 tests total
  (up from 23 pre-Day-4). New: `llmLineGenerator.test.ts` (13 tests —
  `sanitizeLlmLine` word-ceiling/banned-word/swear rejection, prefetch
  falling back before it resolves, using the LLM line once it resolves,
  never re-issuing inference for the same event, serializing concurrent
  prefetches to one in-flight call, rejecting an out-of-character reply) and
  `localTts.test.ts` (5 tests — the `createLocalTtsAdapter` factory, driven
  by a fake `loadModel`/`playAudio`/`stopAudio`, covering load-once caching,
  `error` vs `unavailable` status, and `stop()` delegating correctly).
  `narrator.test.ts` (event tracker + template bank) untouched and still
  passing — the async work is fully isolated behind the new files.
- **Static checks:** `npx tsc -b`, `npm run build`, `npx oxlint src/`,
  `npm run test` (48 tests) — all clean.
- **Live run, headless Chrome (Puppeteer) + fake camera device,**
  `--enable-unsafe-webgpu --enable-features=Vulkan --ignore-gpu-blocklist`:
  - Baseline (unchanged from Day 3): camera live, model ready, ~60 FPS,
    ~11ms inference, narration producing template lines normally with
    `line_generator_engine: 'template'` / `voice_engine: 'system'`
    (the defaults) — confirms Day 4 didn't regress Days 1–3.
  - Switched `line_generator_engine` to `local-llm` live via the panel
    button. **Cold load:** `LLM: idle` → `loading 0%` → climbing → `ready`
    at **~45–63s** across two separate runs (network variance), pulling
    real `.bin`/`.wasm` shards from `huggingface.co` and
    `raw.githubusercontent.com` (~945MB per D13). **First inference: 350ms**
    on one run, **567ms** on another. **While the model was still loading,
    the narration log correctly kept producing template lines** — e.g. *"a
    kite appears. no one asked, but here we are."* — never blocking, never
    silent, exactly the generate-ahead contract.
  - Once ready, the log picked up genuine LLM output, e.g.: *"kite flew
    high, its kite spirit soaring. suddenly, the room was lit by
    sunlight,."* — on-topic, within the word ceiling, no banned words or
    leaked swears (the sanitizer's hard rules held), but tonally more
    florid than the authored template bank. Recorded honestly in D13 rather
    than cherry-picking a better line.
  - **Warm-cache reload** (same Puppeteer profile, second launch): LLM
    reached `ready` in **11.1s**, and the response listener confirmed **0
    bytes** were re-fetched from `huggingface.co`/`githubusercontent.com` —
    the model came entirely from the browser's Cache Storage. This is the
    strongest evidence for the "downloaded once, then cached" claim.
  - **True offline test** (CDP `Network.emulateNetworkConditions({offline:
    true})`, tab **kept open**, no reload): watched the narration log for
    15s — it grew from 5 to 7 rows, i.e. **the LLM kept generating new
    lines with the network fully cut**, and exactly **0** network requests
    fired during that window. Inference has no runtime network dependency
    once the weights are resident.
  - **True offline reload** (same CDP offline mode, but a fresh top-level
    navigation instead of keeping the tab open): **failed** —
    `net::ERR_INTERNET_DISCONNECTED` on the document request itself. This
    project has no service worker, so a from-scratch page load genuinely
    needs the network for the HTML/JS shell, independent of whether the
    model weights are cached. Stated plainly because the day4 brief asked
    for exactly this test: the *model* caching claim holds (proven two ways
    above); the *page* is not offline-capable, and was never claimed to be
    — that would be a PWA/service-worker feature, out of scope for Day 4.
  - Local TTS (`voice_engine: 'local-tts'`): model reached `ready` in the
    same run (Kokoro, ~85MB at `q8`), confirmed via network log — but
    synthesis itself threw `Invalid language identifier: "en-us". Should be
    one of: .` from `phonemizer`'s espeak-ng WASM every time it was called.
    Root-caused to missing cross-origin isolation (`SharedArrayBuffer`
    required by the threaded WASM builds `kokoro-js`/`web-llm` both ship);
    added `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy`
    headers to `vite.config.ts`, which fixed the *silent* part (a Worker now
    visibly spins up instead of running degraded) but not the underlying
    error — still open, see decisions.md D13. **The fallback worked exactly
    as designed**: every failed local-tts call logged a warning and spoke
    the line via `speechSynthesis` instead, so voice output was never
    silently dropped, only ever downgraded to the always-available engine.

## What is NOT verified from this session — stated plainly

- **Kokoro TTS has never been heard to actually speak**, in this session or
  any prior one — see decisions.md D13 for the open bug. `system`
  (`speechSynthesis`) is what's actually been exercised end to end.
- **No audio has been heard at all, by anyone, this session.** This
  environment is headless with no speaker — even `speechSynthesis`, which
  the code correctly drives and which reported 191 available voices in this
  Chrome build, cannot be confirmed *audible* from here. Days 1–3 flagged
  the same gap and it is still open: nobody has listened to YAP talk. This
  needs a real browser, on real hardware, with real output, before "it
  sounds good" (or even "it makes a sound") can be claimed on camera.
- **Mobile.** No phone was reachable this session. The model-choice
  rationale (D13) rests entirely on WebLLM's published VRAM figures and
  desktop-measured latency, not an on-device phone measurement. This is the
  single biggest unverified claim in Day 4 and should be the first thing
  checked before the mobile day (Day 7) leans on it.
- **Peak memory** was not measured (no reliable way to sample GPU/WASM heap
  from outside the page in this environment). The two model downloads
  together are ~1GB+ on disk/cache; runtime memory is unmeasured.
- **Spatial language, salience ranking, timing tuning** — explicitly cut per
  the Day 4 scope decision in `tasks.md` ("the LLM and the TTS are the day").

## What can be shown publicly

Both model swaps are real and independently checkable on camera: the network
tab shows genuine multi-hundred-megabyte downloads from Hugging Face the
first time either engine is switched on, the panel shows live load
percentages and post-load per-line/per-synth latency numbers, and a second
reload with the same profile visibly skips the download and reaches `ready`
in ~11s instead of ~50s+. The generate-ahead fallback is demonstrable live:
switch to `local-llm` and immediately narrate something — the log keeps
producing template lines with zero stutter while the model downloads in the
background, then visibly switches to LLM-authored lines once it's ready. The
honest cliffhanger is Kokoro: the download and load are real and provable,
the fallback-not-silence behavior is real and provable, but the voice itself
has a live, named, not-yet-fixed bug — which is exactly the kind of "show
the seams" moment `demo-script.md` already asks for.
