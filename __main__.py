"""`python -m jarvis` → launch the unified app."""
from __future__ import annotations

import sys

from jarvis.runner import main

if __name__ == "__main__":
    sys.exit(main())
