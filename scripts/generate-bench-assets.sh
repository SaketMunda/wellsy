#!/usr/bin/env bash
# Regenerates the fake-camera video files scripts/bench.mjs feeds Chrome via
# --use-file-for-fake-video-capture. Not committed (uncompressed Y4M, ~460MB
# each) — see .gitignore. Run this once before `node scripts/bench.mjs`.
set -euo pipefail
cd "$(dirname "$0")/bench-assets"

# 30fps, not 15 — discovered the hard way (see day7-baseline.md's methodology
# note): Chrome's fake-file-video-capture throttles the *page's whole rAF
# cadence* to match the source video's declared frame rate, not just the
# <video> element's updates. A 15fps source silently caps every rAF-driven
# loop in the app (detection, HUD draw, this bench recorder) at 15Hz — a
# measurement artifact, not a real cost. 30fps matches a plausible webcam and
# was confirmed to let rAF run free at ~60Hz.

# "moving": Chrome's default synthetic test pattern content, used for
# scenarios A-D (an ordinary scene with things happening).
ffmpeg -y -f lavfi -i "testsrc=size=640x480:rate=30:duration=75" -pix_fmt yuv420p moving.y4m

# "still": one flat gray frame held for the whole run — genuinely zero motion,
# for scenario E (the idle-cost measurement).
ffmpeg -y -f lavfi -i "color=c=gray:size=640x480:rate=30:duration=75" -pix_fmt yuv420p still.y4m
