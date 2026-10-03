"""Central file locations.

The cleaned dataset is the read-only source of truth produced by
``backend/data_agent.py``. Every mutation (runtime copy + audit log) goes to
``FDE_RUNTIME_DIR`` so tests and E2E runs can point at a throw-away directory
and never touch the demo files in ``outputs/``.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"

CLEANED_FILE = Path(
    os.environ.get(
        "FDE_CLEANED_FILE",
        DEFAULT_OUTPUT_DIR / "FDE_Assignment_Shipment_Dataset_AI_Cleaned.xlsx",
    )
)

RUNTIME_DIR = Path(os.environ.get("FDE_RUNTIME_DIR", DEFAULT_OUTPUT_DIR))

RUNTIME_FILE = RUNTIME_DIR / "FDE_Assignment_Shipment_Runtime.xlsx"

AUDIT_LOG_FILE = RUNTIME_DIR / "agent_audit_log.jsonl"
