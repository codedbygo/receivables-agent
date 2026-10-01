"""python -m app.evaluation [--offline]"""

import sys

from app.evaluation.harness import main

sys.exit(main(sys.argv[1:]))
