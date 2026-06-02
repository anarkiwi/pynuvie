"""All source must pass black (formatting) and pylint (incl. unused vars/imports).

These run the real tools as subprocesses so the test enforces exactly what CI does.
Each skips if its tool isn't installed (e.g. a minimal env without the dev extra).
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# black formats everything (research scripts included); pylint/ruff lint only the
# shipped package and its tests (the research scripts are throwaway RE tools).
BLACK_TARGETS = ["src", "tests", "research"]
PYLINT_TARGETS = ["src", "tests"]


def _have(module: str) -> bool:
    return (
        subprocess.run([sys.executable, "-c", f"import {module}"], cwd=ROOT, check=False).returncode
        == 0
    )


@pytest.mark.skipif(not _have("black"), reason="black not installed")
def test_black_clean():
    r = subprocess.run(
        [sys.executable, "-m", "black", "--check", *BLACK_TARGETS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not _have("pylint"), reason="pylint not installed")
def test_pylint_clean():
    r = subprocess.run(
        [sys.executable, "-m", "pylint", *PYLINT_TARGETS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
