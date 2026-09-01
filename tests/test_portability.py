"""The automated portability gate — `.claude/rebuild/step2-backend-abstraction.md`
Deliverable 3, acceptance criterion 4.

Two halves:
  * the whole `engine/` tree is clean right now (the real build gate);
  * the checker actually catches a banned import when one is introduced
    (the negative test the acceptance spec demands — "write that negative
    test").
"""

from __future__ import annotations

import textwrap

import pytest

from engine.inference.portability import (
    BANNED_ROOTS,
    SANCTIONED_DIRS,
    engine_root,
    is_exempt,
    scan_source,
    scan_tree,
)


def test_no_banned_imports_in_core():
    violations = scan_tree(engine_root())
    assert violations == [], "banned imports in engine/:\n" + "\n".join(str(v) for v in violations)


@pytest.mark.parametrize(
    "src",
    [
        "import mlx",
        "import mlx.core as mx",
        "import mlx_lm",
        "from mlx_lm import load, stream_generate",
        "import coremltools as ct",
        "from Quartz import CGWindowListCopyWindowInfo",
        "import ScreenCaptureKit",
        "import dxcam",
        "import Xlib.display",
        textwrap.dedent(
            """
            def loader():
                try:
                    import mlx_lm  # hidden inside a function + try
                except ImportError:
                    mlx_lm = None
            """
        ),
    ],
)
def test_detector_flags_injected_banned_import(src):
    hits = scan_source(src, "injected.py")
    assert hits, f"checker missed a banned import in:\n{src}"
    assert all(h.imported.split(".")[0] in BANNED_ROOTS for h in hits)


def test_clean_source_is_not_flagged():
    src = textwrap.dedent(
        """
        import os
        import numpy as np
        import onnxruntime as ort      # portable — allowed
        import torch                    # portable — allowed
        # the string "import mlx" in a comment is fine
        NOTE = "we do not import mlx here"
        """
    )
    assert scan_source(src, "clean.py") == []


def test_sanctioned_dirs_are_skipped_by_the_tree_scan():
    root = engine_root()
    # every sanctioned dir that exists on disk must be exempt...
    for parts in SANCTIONED_DIRS:
        d = root.joinpath(*parts)
        if d.exists():
            sample = next(d.rglob("*.py"), None)
            if sample is not None:
                assert is_exempt(sample, root)
    # ...and a file just outside one of them is not
    assert not is_exempt(root / "cli.py", root)
