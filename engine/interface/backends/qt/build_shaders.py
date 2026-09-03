"""Compile the orb shader(s) to .qsb — the packaging step Qt 6 requires.

Qt 6 dropped inline GLSL: `ShaderEffect` loads a pre-compiled `.qsb` bundle
(SPIR-V + reflection + MSL/HLSL/GLSL translations). The `qsb` tool ships in the
PySide6 wheel as `pyside6-qsb` (and as `qsb` in a full Qt SDK). This script
finds whichever is present and runs it, so a plain `uv`/`pip` install can build
the shaders with no Qt developer environment.

    python -m engine.interface.backends.qt.build_shaders          # build all
    python -m engine.interface.backends.qt.build_shaders --check  # CI: fail if stale
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHADER_DIR = HERE / "shaders"


def _qsb() -> list[str] | None:
    for cand in ("pyside6-qsb", "qsb"):
        p = shutil.which(cand)
        if p:
            return [p]
    try:  # module form, if the console script is not on PATH
        import PySide6  # noqa: F401
        return [sys.executable, "-m", "PySide6.scripts.qsb"]
    except Exception:
        return None


def build(check: bool = False) -> int:
    qsb = _qsb()
    sources = sorted(SHADER_DIR.glob("*.frag")) + sorted(SHADER_DIR.glob("*.vert"))
    if not sources:
        print(f"no shader sources in {SHADER_DIR}", file=sys.stderr)
        return 1
    if qsb is None:
        print("qsb not found (install PySide6 or a Qt SDK). Shaders NOT built.",
              file=sys.stderr)
        return 2

    rc = 0
    for src in sources:
        out = src.with_suffix(src.suffix + ".qsb")
        if check:
            if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
                print(f"STALE: {out.name}", file=sys.stderr)
                rc = 1
            continue
        # --glsl 300es,120 --hlsl 50 --msl 12 covers the three RHI backends
        cmd = qsb + ["--glsl", "300es,120", "--hlsl", "50", "--msl", "12",
                     "-o", str(out), str(src)]
        print(" ".join(cmd))
        r = subprocess.run(cmd)
        rc = rc or r.returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(build(check="--check" in sys.argv[1:]))
