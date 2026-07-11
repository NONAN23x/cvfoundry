"""Runtime modules for CvFoundry's command-line tools.

The source checkout continues to support direct script execution.  Packaging this
directory also lets the installed console script use the same implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
