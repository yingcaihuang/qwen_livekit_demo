"""Azure OpenAI configuration for the Azure OpenAI Testing Platform.

Centralizes data-storage related configuration so that values are read from the
environment (with sensible defaults) rather than being hardcoded at call sites.
Follows the same module-level constant style as ``database.py`` (values read via
``os.environ.get`` with defaults).

Azure OpenAI URLs use the ``/openai/v1`` (OpenAI-compatible) surface, so no
``api-version`` configuration is required.
"""

import os
from pathlib import Path

# Root directory for persisted data. Defaults to the same location used by the
# SQLite database (see ``DB_PATH`` in ``database.py``) so generated image files
# live alongside the existing data (Requirements 9.5).
DATA_DIR = os.environ.get("DATA_DIR", "./data")

# Sub-directory (under DATA_DIR) that holds generated image files.
IMAGES_DIR_NAME = os.environ.get("IMAGES_DIR_NAME", "images")

# Defensive upper bound on the size of an uploaded reference image.
MAX_REFERENCE_IMAGE_BYTES = int(
    os.environ.get("MAX_REFERENCE_IMAGE_BYTES", str(50 * 1024 * 1024))
)  # 50MB

# Computed absolute-ish path to the images root directory (DATA_DIR / IMAGES_DIR_NAME).
IMAGES_DIR = Path(DATA_DIR) / IMAGES_DIR_NAME
