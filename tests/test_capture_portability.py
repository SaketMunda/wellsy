"""Invariant #14 guard, scoped to the capture layer: no platform-exclusive
package may be imported anywhere under `engine/capture/` except inside
`engine/capture/screen/` (the sanctioned backend location).

This is a local stopgap — step 2 builds the full source-tree AST checker that
fails the whole build. It is kept here so step 3 does not regress the invariant
in the meantime.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CAPTURE_ROOT = Path(__file__).parents[1] / "engine" / "capture"
SANCTIONED = CAPTURE_ROOT / "screen"

# Platform-exclusive top-level packages. `mss` is deliberately absent — it is
# cross-platform and is the portable fallback.
BANNED_PREFIXES = (
    "Quartz",
    "ScreenCaptureKit",
    "AppKit",
    "Foundation",
    "AVFoundation",
    "Cocoa",
    "CoreMedia",
    "objc",
    "mlx",
    "coremltools",
    "dxcam",
    "win32",
    "winrt",
    "winsdk",
    "Xlib",
    "pipewire",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split(".")[0])
    return mods


@pytest.mark.parametrize(
    "py",
    [p for p in CAPTURE_ROOT.rglob("*.py") if SANCTIONED not in p.parents and p.parent != SANCTIONED],
    ids=lambda p: str(p.relative_to(CAPTURE_ROOT)),
)
def test_no_platform_import_outside_screen_backends(py: Path):
    offending = {m for m in _imports(py) if any(m == b or m.startswith(b) for b in BANNED_PREFIXES)}
    assert not offending, f"{py.relative_to(CAPTURE_ROOT)} imports platform package(s): {offending}"


def test_screen_backends_do_contain_the_platform_code():
    """Sanity: the guard above is only meaningful if the platform imports
    genuinely live under screen/. macos.py must import Quartz."""
    macos_imports = _imports(SANCTIONED / "macos.py")
    assert "Quartz" in macos_imports and "ScreenCaptureKit" in macos_imports
