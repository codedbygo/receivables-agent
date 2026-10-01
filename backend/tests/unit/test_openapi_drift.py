"""api/openapi.yaml and the served routes agree (openapi-spec drift = 0). Operations marked x-status planned are
documented ahead of the code and are the only ones allowed to be missing."""

from pathlib import Path

import yaml

from app.api.main import create_app
from app.core.config import Settings
from app.core.paths import find_up

SPEC = yaml.safe_load(
    (find_up("api", Path(__file__).parents[2]) / "openapi.yaml").read_text(encoding="utf-8")
)
PREFIX = "/api/v1"


def served() -> set[tuple[str, str]]:
    """What FastAPI itself would document for the running app (included routers are nested in 0.142)."""
    app = create_app(Settings(database_url="postgresql+psycopg://u@127.0.0.1:1/none"))
    paths: dict[str, dict[str, object]] = app.openapi()["paths"]
    return {(m, p.removeprefix(PREFIX)) for p, ops in paths.items() for m in ops}


def documented(planned: bool) -> set[tuple[str, str]]:
    return {
        (m, p) for p, ops in SPEC["paths"].items() for m, o in ops.items() if ("x-status" in o) == planned
    }


def test_every_served_route_is_in_the_spec() -> None:
    assert served() - documented(False) - documented(True) == set()


def test_every_documented_route_is_served_unless_planned() -> None:
    assert documented(False) - served() == set()
