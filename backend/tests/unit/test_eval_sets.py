"""US-01-011: the trajectory scenarios cover the cases the brief names."""

import re

import yaml

from app.core.paths import find_up


# TC-0257 (AC-US-01-011-2)
def test_scenarios_include_the_five_required_cases() -> None:
    ids = {
        yaml.safe_load(p.read_text(encoding="utf-8"))["id"]
        for p in (find_up("evals") / "scenarios").glob("*.yaml")
    }
    required = {"s02-abc-promise", "s03-abc-dispute", "s04-injection", "s06-claim-matched", "s09-limit"}
    assert required <= ids, required - ids


# TC-0267 (AC-US-01-015-3): the README's evaluation figures are the generated report's, with the command.
def test_readme_evaluation_numbers_match_the_report() -> None:
    root = find_up("evals").parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    section = readme.split("## 5. Evaluation results", 1)[1].split("\n## ", 1)[0]
    report = (root / "docs" / "evals" / "report.md").read_text(encoding="utf-8")
    figures = re.findall(r"\b\d+/\d+\b", section)
    assert len(figures) >= 7
    assert [f for f in figures if f not in report] == []
    assert "make eval" in section
