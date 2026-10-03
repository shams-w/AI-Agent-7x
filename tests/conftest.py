"""Test isolation.

All mutations during tests (runtime dataset + audit log) are redirected to a
temporary directory BEFORE any backend module is imported. A session guard
then asserts that the demo files in ``outputs/`` were not modified.
"""

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"

_TMP_RUNTIME = Path(tempfile.mkdtemp(prefix="fde-test-runtime-"))
os.environ["FDE_RUNTIME_DIR"] = str(_TMP_RUNTIME)
# Tests must never depend on a live LLM / network.
os.environ["FDE_INTENT_LLM"] = "off"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fingerprint():
    result = {}
    if OUTPUTS.exists():
        for path in sorted(OUTPUTS.iterdir()):
            if path.is_file():
                result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


_BEFORE = _fingerprint()


@pytest.fixture(scope="session", autouse=True)
def _demo_files_untouched():
    yield
    after = _fingerprint()
    shutil.rmtree(_TMP_RUNTIME, ignore_errors=True)
    assert after == _BEFORE, "Tests modified files in outputs/ — isolation is broken."
