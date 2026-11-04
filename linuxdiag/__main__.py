"""Enable `python -m linuxdiag`."""
from __future__ import annotations

import sys

from linuxdiag.cli import main

if __name__ == "__main__":
    sys.exit(main())
