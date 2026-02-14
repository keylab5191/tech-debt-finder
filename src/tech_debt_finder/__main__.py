"""Allow running as: python -m tech_debt_finder"""

import sys

from .cli import main

sys.exit(main())
