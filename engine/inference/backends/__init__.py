"""Backend implementations of the `engine.inference` protocols.

This directory is the **one place** platform-exclusive imports are allowed
(INVARIANTS #14): the automated portability check
(`engine/inference/portability.py`) skips any path with a ``backends``
component. Even here, a platform-only package (``mlx_lm`` in ``mlx.py``) is
imported lazily inside methods, never at module scope, so that merely importing
the registry on Linux does not blow up.
"""
