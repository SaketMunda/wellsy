"""The automated portability check — `.claude/rebuild/step2-backend-abstraction.md`
Deliverable 3, INVARIANTS #14.

A module under ``engine/`` that imports a platform-exclusive package makes the
core non-portable, and "OS independent" silently becomes "slow (or broken)
everywhere". This check fails the build when that happens. It works by
**AST-walking the source** — not grep, not a review — so a comment mentioning
``mlx`` is fine and ``import mlx`` inside a string is fine, but a real import
node is caught wherever it sits (top level, inside a function, inside a
``try``).

Exempt locations are the **sanctioned backend directories** — the one place per
subsystem where a platform API may be touched (INVARIANTS #14 permits
ScreenCaptureKit "as the macOS backend", MLX "as the macOS backend", …). They
are listed explicitly in ``SANCTIONED_DIRS`` and adding a new one is a
deliberate edit to this file, reviewed like any other — that is the point of a
build-failing gate. Backends still must not import a platform-only package at
module scope; that convention the backends police themselves.

This checker supersedes the step-3 stopgap in
``tests/test_capture_portability.py`` (which scoped the same idea to
``engine/capture/`` "until step 2 builds the full source-tree AST checker").

Run standalone::

    python -m engine.inference.portability        # exits 1 on any violation
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# Import roots banned in the core. INVARIANTS #14's explicit list, plus the
# pyobjc frameworks behind macOS screen/AV capture and the platform-only
# screen-grab packages for Windows and Linux display servers. `mss` is NOT here
# — it is the cross-platform fallback. `torch` is NOT here — it is portable
# (CUDA/MPS/ROCm/CPU from one wheel).
BANNED_ROOTS: frozenset[str] = frozenset(
    {
        # Apple compute
        "mlx", "mlx_lm", "mlx_vlm", "coremltools", "coreml",
        # Apple screen / audio / windowing (pyobjc)
        "ScreenCaptureKit", "AVFoundation", "Quartz", "AppKit", "Cocoa",
        "Foundation", "CoreMedia", "objc",
        # Apple speech
        "speech_swift",
        # Windows-only capture / runtime
        "dxcam", "d3dshot", "win32", "win32api", "win32gui", "winrt",
        "winsdk",
        # Linux display-server-specific (portable path is mss)
        "Xlib", "pipewire",
    }
)

# Sanctioned backend trees, as path tuples relative to the `engine/` root.
# A file is exempt iff its relative path starts with one of these.
SANCTIONED_DIRS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("inference", "backends"),   # this step's LLM/ASR/TTS/VAD backends
        ("capture", "screen"),       # step 3's macOS/Linux/Windows screen backends
    }
)


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    imported: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: banned import {self.imported!r}"


def _root(dotted: str) -> str:
    return dotted.split(".", 1)[0]


def scan_source(src: str, filename: str = "<string>") -> list[Violation]:
    """Return every banned import node in ``src``."""

    out: list[Violation] = []
    tree = ast.parse(src, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _root(alias.name) in BANNED_ROOTS:
                    out.append(Violation(filename, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` (level > 0) is always in-package; ignore.
            if node.level == 0 and node.module and _root(node.module) in BANNED_ROOTS:
                out.append(Violation(filename, node.lineno, node.module))
    return out


def is_exempt(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return any(parts[: len(d)] == d for d in SANCTIONED_DIRS)


def scan_tree(root: Path) -> list[Violation]:
    """AST-walk every ``*.py`` under ``root`` except exempt trees."""

    violations: list[Violation] = []
    for py in sorted(root.rglob("*.py")):
        if is_exempt(py, root):
            continue
        try:
            src = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:  # pragma: no cover
            violations.append(Violation(str(py.relative_to(root)), 0, f"<unreadable: {e}>"))
            continue
        for v in scan_source(src, str(py.relative_to(root))):
            violations.append(v)
    return violations


def engine_root() -> Path:
    return Path(__file__).resolve().parents[1]  # .../engine


def main(argv: list[str] | None = None) -> int:
    root = engine_root()
    violations = scan_tree(root)
    if violations:
        print(f"portability check FAILED — {len(violations)} banned import(s) in {root}:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    exempt = ", ".join("/".join(d) for d in sorted(SANCTIONED_DIRS))
    print(f"portability check OK — no banned imports under {root} (sanctioned backend trees: {exempt})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
