"""Test package initialization.

Sets TESTING=1 so the auth dependency bypass is active during tests.
"""

import os

os.environ["TESTING"] = "1"
