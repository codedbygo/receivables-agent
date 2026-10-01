"""The evaluation harness (REQ-101 to REQ-104, brief 4.22). Every number is computed from a real run of the
product code over the labelled sets in evals/; nothing in the report is typed by hand.

    offline: 40 labelled replies (classifier + action), red-team drafts, golden drafts. No database.
    full:    offline + the trajectory scenarios, each on a freshly reset demo database; writes the report.
"""

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.agent import replies
from app.agent.classify import Classification, classify
from app.agent.orchestrator import Orchestrator
from app.core.clock import wall_now
from app.core.config import Settings
from app.core.db import make_engine
from app.core.paths import find_up
from app.guardrails.verify import InvoiceFact, VerifyContext, verify
from app.llm.gateway import Gateway
from app.services import collections, payments
from app.services.demo import reset_demo, uid
from app.services.payments import BankCredit
from app.tools.registry import build_registry

EVALS = find_up("evals")
TODAY = date(2026, 9, 30)
# Floors that fail the gate: the rules classifier's measured level minus a margin, and 100% on safety sets.
FLOORS = {"class": 0.85, "amount": 0.85, "date": 0.85}


@dataclass
class Section:
    total: int = 0
    passed: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return round(self.passed / self.total, 3) if self.total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"total": self.total, "passed": self.passed, "rate": self.rate, "failures": self.failures}


def _load_yaml(name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = yaml.safe_load((EVALS / name).read_text(encoding="utf-8"))["cases"]
    return cases


def labelled_replies() -> list[dict[str, Any]]:
    lines = (EVALS / "replies.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def eval_replies(gateway: Gateway | None, threshold: float) -> dict[str, Any]:
    """Class, expected action, amount and date accuracy on the 40 labelled replies."""
    rows = labelled_replies()
    got: list[Classification] = [classify(r["input"]["text"], TODAY, [], gateway) for r in rows]
    scores = {k: Section(total=len(rows)) for k in ("class", "action", "amount", "date")}
    for r, c in zip(rows, got, strict=True):
        exp = r["expected"]
        review = c.injection_suspected or c.confidence < threshold or c.note == "CLASS_INVALID"
        actual = {
            "class": c.klass,
            "action": replies.action_for(c, review),
            "amount": c.amount_paise,
            "date": c.stated_date.isoformat() if c.stated_date else None,
        }
        expected = {
            "class": exp["class"],
            "action": exp["action"],
            "amount": exp["amount_paise"],
            "date": exp["date"],
        }
        for k, sec in scores.items():
            if actual[k] == expected[k]:
                sec.passed += 1
            else:
                sec.failures.append({"id": r["id"], "expected": expected[k], "actual": actual[k]})
    out: dict[str, Any] = {k: s.as_dict() for k, s in scores.items()}
    out["source"] = dict(Counter(c.source for c in got))
    return out


def _facts() -> tuple[dict[str, InvoiceFact], tuple[str, ...]]:
    fix = json.loads((EVALS / "fixture_invoices.json").read_text(encoding="utf-8"))["invoices"]
    facts = {
        n: InvoiceFact(
            number=n, customer=cust, amount_paise=a, remaining_paise=a, due=date.fromisoformat(due)
        )
        for cust, rows in fix.items()
        for n, a, _issued, due in rows
    }
    return facts, tuple(fix)


def eval_drafts() -> tuple[dict[str, Any], dict[str, Any]]:
    """Red team: every draft rejected with its expected code. Golden: every draft passes."""
    facts, names = _facts()

    def ctx(case: dict[str, Any]) -> VerifyContext:
        return VerifyContext(
            customer=case["customer"],
            cited=tuple(case["invoices"]),
            invoices=facts,
            customer_names=names,
            today=TODAY,
            kind=case.get("kind", "reminder"),
        )

    red, gold = Section(), Section()
    for case in _load_yaml("redteam.yaml"):
        red.total += 1
        report = verify(case["text"], ctx(case))
        if not report.ok and case["expect_code"] in report.codes:
            red.passed += 1
        else:
            red.failures.append(
                {"id": case["id"], "expected": case["expect_code"], "actual": sorted(report.codes)}
            )
    for case in _load_yaml("golden.yaml"):
        gold.total += 1
        report = verify(case["text"], ctx(case))
        if report.ok:
            gold.passed += 1
        else:
            gold.failures.append({"id": case["id"], "expected": "pass", "actual": sorted(report.codes)})
    return red.as_dict(), gold.as_dict()


def _scripted(turns: list[dict[str, Any]], customer_id: str, tone: str) -> httpx.MockTransport:
    """A model that answers with the scenario's scripted turns, one per request."""

    def fill(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: fill(x) for k, x in v.items()}
        return {"$customer": customer_id, "$tone": tone}.get(v, v) if isinstance(v, str) else v

    bodies: list[dict[str, Any]] = []
    for i, t in enumerate(turns):
        if "final" in t:
            msg: dict[str, Any] = {"content": t["final"]}
        else:
            fn = {"name": t["tool"], "arguments": json.dumps(fill(t["args"]))}
            msg = {"content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": fn}]}
        bodies.append(
            {"choices": [{"message": msg}], "usage": {"prompt_tokens": 800, "completion_tokens": 60}}
        )
    queue = list(bodies)
    return httpx.MockTransport(
        lambda _r: httpx.Response(
            200, json=queue.pop(0) if queue else {"choices": [{"message": {"content": "done"}}]}
        )
    )


def _run_scenario(engine: Engine, base: Settings, sc: dict[str, Any]) -> dict[str, Any]:
    reset_demo(engine, base)
    inp, exp = sc["input"], sc["expected"]
    cid = uid("customer", inp["customer"])
    _setup(engine, cid, sc.get("setup") or [])
    registry_gw: Gateway
    if sc.get("script"):
        tone = _tone_of(engine, base, cid)
        live = base.model_copy(update={"llm_mode": "live", "openrouter_api_key": "scripted"})
        registry_gw = Gateway(
            live, engine, transport=_scripted(sc["script"], cid, tone), sleep=lambda _s: None
        )
    else:
        registry_gw = Gateway(base, engine)
    orch = Orchestrator(engine, registry_gw, build_registry(engine, registry_gw))
    klass = None
    if inp["trigger"] == "reply":
        rid = _reply_row(engine, cid, inp["reply_id"])
        res = replies.understand(orch, rid)
        run_id, outcome, klass = res.run.id, res.run.outcome, res.classification.klass
    else:
        run = orch.run_collections(cid, inp["trigger"])
        assert run is not None, "a run was already active on a freshly reset database"
        run_id, outcome = run.id, run.outcome
    with engine.connect() as c:
        tools: list[str] = list(
            c.execute(
                text("SELECT tool_name FROM agent_steps WHERE agent_run_id = CAST(:r AS uuid) ORDER BY seq"),
                {"r": run_id},
            ).scalars()
        )
    actual = {"class": klass, "tools": tools, "outcome": outcome}
    expected = {"class": exp["class"], "tools": exp["tools"], "outcome": exp["outcome"]}
    return {"id": sc["id"], "ok": actual == expected, "expected": expected, "actual": actual}


def _setup(engine: Engine, customer_id: str, steps: list[dict[str, Any]]) -> None:
    """Scenario preconditions, applied through the same services the product uses."""
    with engine.begin() as c, Session(bind=c) as s:
        for step in steps:
            if "bank_credit" in step:
                b = step["bank_credit"]
                credit = BankCredit(
                    event_id=f"eval-{b['reference']}",
                    amount_paise=b["amount_paise"],
                    reference=b["reference"],
                )
                payments.receive_credit(s, credit)
            elif "dispute" in step:
                d = step["dispute"]
                collections.log_dispute(s, customer_id, d["invoice"], d["reason"], actor="human")
            else:
                raise ValueError(f"unknown setup step {sorted(step)}")


def _tone_of(engine: Engine, base: Settings, customer_id: str) -> str:
    return Orchestrator(engine, Gateway(base, engine), build_registry(engine))._tone(customer_id)[0]


def _reply_row(engine: Engine, customer_id: str, label_id: str) -> str:
    """Seeded replies keep their label's uuid; ABC's are demo-story beats and are inserted here."""
    rid = uid("reply", label_id)
    body = next(r["input"]["text"] for r in labelled_replies() if r["id"] == label_id)
    with engine.begin() as c:
        c.execute(
            text("""INSERT INTO replies (id, customer_id, body) VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :b)
            ON CONFLICT (id) DO NOTHING"""),
            {"i": rid, "c": customer_id, "b": body},
        )
    return rid


def eval_scenarios(engine: Engine, base: Settings) -> dict[str, Any]:
    sec = Section()
    results = []
    for path in sorted((EVALS / "scenarios").glob("*.yaml")):
        sc = yaml.safe_load(path.read_text(encoding="utf-8"))
        r = _run_scenario(engine, base, sc)
        results.append(r)
        sec.total += 1
        sec.passed += r["ok"]
        if not r["ok"]:
            sec.failures.append(r)
    reset_demo(engine, base)  # leave the database at the start of the demo story
    return {**sec.as_dict(), "results": results}


def run(offline: bool, settings: Settings) -> dict[str, Any]:
    engine = None if offline else make_engine(settings.database_url)
    gateway = Gateway(settings, engine) if engine is not None else None
    red, gold = eval_drafts()
    report: dict[str, Any] = {
        "generated_at": wall_now().isoformat(timespec="seconds"),
        "mode": settings.llm_mode,
        "command": "make eval-replay" if offline else "make eval",
        "replies": eval_replies(gateway, settings.classify_min_confidence),
        "red_team": red,
        "golden": gold,
        "scenarios": eval_scenarios(engine, settings) if engine is not None else None,
    }
    return report


def failures(report: dict[str, Any]) -> list[str]:
    bad = [
        f"replies.{k} {report['replies'][k]['rate']} < {v}"
        for k, v in FLOORS.items()
        if report["replies"][k]["rate"] < v
    ]
    bad += [
        f"{k}: {report[k]['passed']}/{report[k]['total']}"
        for k in ("red_team", "golden")
        if report[k]["rate"] < 1
    ]
    sc = report["scenarios"]
    if sc is not None and sc["rate"] < 1:
        bad.append(f"scenarios: {sc['passed']}/{sc['total']}")
    return bad


def markdown(report: dict[str, Any]) -> str:
    r = report["replies"]

    def pct(s: dict[str, Any]) -> str:
        return f"{s['passed']}/{s['total']} ({s['rate']:.0%})"

    lines = [
        "# Evaluation report",
        "",
        f"Generated {report['generated_at']} by `{report['command']}` with `LLM_MODE={report['mode']}`. "
        "Every figure below is computed by `backend/app/evaluation/harness.py` from a run of the product code; "
        "none is typed by hand. Regenerate with `make eval`.",
        "",
        "## Labelled replies (40)",
        "",
        f"Classifier source: {', '.join(f'{k} {v}' for k, v in r['source'].items())}. "
        "`rules` means no replay fixture existed for the model, so the deterministic classifier answered.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Classification accuracy | {pct(r['class'])} |",
        f"| Expected-action accuracy | {pct(r['action'])} |",
        f"| Amount extraction | {pct(r['amount'])} |",
        f"| Date extraction | {pct(r['date'])} |",
        "",
        "Expected-action labels name two actions differently: `human_review` is what the product calls "
        "`escalate`, and part payments are labelled `verify_payment` where the product runs `check_promise_status` "
        "then `create_followup` (HLD Flow B). The score counts exact matches only and is not adjusted.",
        "",
        "## Guardrails",
        "",
        "| Set | Result |",
        "|---|---|",
        f"| Red-team drafts rejected with the expected code | {pct(report['red_team'])} |",
        f"| Golden drafts passing every check | {pct(report['golden'])} |",
        "",
    ]
    sc = report["scenarios"]
    if sc is not None:
        lines += [
            f"## Trajectory scenarios: {pct(sc)}",
            "",
            "| Scenario | Result | Class | Tools | Outcome |",
            "|---|---|---|---|---|",
        ]
        for x in sc["results"]:
            a = x["actual"]
            lines.append(
                f"| {x['id']} | {'pass' if x['ok'] else 'FAIL'} | {a['class'] or '-'} | "
                f"{', '.join(a['tools']) or '-'} | {a['outcome']} |"
            )
        lines.append("")
    misses = [(k, f) for k in ("class", "action", "amount", "date") for f in r[k]["failures"]]
    if misses:
        lines += ["## Reply misses", "", "| Reply | Metric | Expected | Actual |", "|---|---|---|---|"]
        lines += [f"| {f['id']} | {k} | {f['expected']} | {f['actual']} |" for k, f in misses]
        lines.append("")
    return "\n".join(lines)


def write(report: dict[str, Any], root: Path) -> None:
    (root / "evals" / "report.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (root / "docs" / "evals").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "evals" / "report.md").write_text(markdown(report), encoding="utf-8")


def latest(root: Path | None = None) -> dict[str, Any] | None:
    path = (root or EVALS.parent) / "evals" / "report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main(argv: list[str]) -> int:
    offline = "--offline" in argv
    settings = (
        Settings()
        if offline
        else Settings(database_url=os.environ.get("DATABASE_URL", Settings().database_url))
    )
    report = run(offline, settings)
    if not offline:
        write(report, EVALS.parent)
    bad = failures(report)
    r = report["replies"]
    print(  # noqa: T201  CLI output
        f"eval: replies class {r['class']['rate']:.0%} action {r['action']['rate']:.0%} amount {r['amount']['rate']:.0%} "
        f"date {r['date']['rate']:.0%}; red team {report['red_team']['passed']}/{report['red_team']['total']}; "
        f"golden {report['golden']['passed']}/{report['golden']['total']}"
        + (
            f"; scenarios {report['scenarios']['passed']}/{report['scenarios']['total']}"
            if report["scenarios"]
            else ""
        )
    )
    for b in bad:
        print(f"eval: FAILED {b}")  # noqa: T201  CLI output
    return 1 if bad else 0
