"""python -m app.seed [--reset | --if-empty]: load the demo seed, or reset to the start of the ABC story.
--if-empty seeds a fresh database and leaves a seeded one alone (the compose migrate service runs it on every up)."""

import sys

from app.core.config import get_settings
from app.core.db import make_engine
from app.services.demo import is_seeded, reset_demo, seed


def main(argv: list[str]) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        if "--if-empty" in argv and is_seeded(engine):
            print("seed: database already seeded; left as it is")
        elif "--reset" in argv:
            reset_demo(engine, settings)
            print("reset-demo: data at the start of the ABC story, demo date", settings.demo_today)
        else:
            seed(engine, settings)
            print("seed: 10 customers, 60 invoices, 20 replies loaded")
    except RuntimeError as e:
        print(f"seed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
