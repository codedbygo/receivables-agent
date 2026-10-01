"""US-01-010, US-01-011, US-01-012: the evaluation harness scores real runs and meets its floors."""

import os

import pytest
from sqlalchemy import Engine

from app.core.config import Settings
from app.evaluation import harness

pytestmark = pytest.mark.integration


# TC-0253 (AC-US-01-010-1), TC-0255 (AC-US-01-010-3), TC-0256 (AC-US-01-011-1), TC-0258 (AC-US-01-012-1)
def test_full_evaluation_meets_every_floor(engine: Engine) -> None:
    # US-01-010 (40 labelled replies), US-01-011 (every trajectory scenario), US-01-012 (red team all rejected)
    report = harness.run(
        offline=False, settings=Settings(database_url=os.environ["DATABASE_URL"], llm_mode="replay")
    )

    assert report["replies"]["class"]["total"] == 40
    assert report["scenarios"]["total"] >= 10
    assert report["red_team"]["passed"] == report["red_team"]["total"] > 0
    assert harness.failures(report) == []
