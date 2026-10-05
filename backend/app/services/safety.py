"""AI Safety Center (HACK-003): counts of real rows only. Nothing here is estimated or seeded; a metric with no
events reads 0, and the page says what each count is made of."""

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

AMOUNT_CODES = ("AMOUNT_MISMATCH", "INVENTED_AMOUNT", "TOTAL_MISMATCH", "AMOUNT_UNPARSEABLE")
INJECTION_CODES = ("PROMPT_INJECTION_SUSPECTED",)


class CodeCount(BaseModel):
    check_name: str
    code: str
    count: int


class Safety(BaseModel):
    messages_checked: int
    messages_passed: int
    guardrail_failures: int
    incorrect_amounts_blocked: int
    prompt_attacks_blocked: int
    human_approvals: int
    human_rejections: int
    automatic_approvals: int
    automatic_sends: int
    send_gate_refusals: int
    tool_calls_refused: int
    kill_switch: str
    autonomy_mode: str
    llm_spent_micro_usd: int
    llm_budget_micro_usd: int
    by_code: list[CodeCount]
    sources: dict[str, str]


SOURCES = {
    "messages_checked": "Drafts that went through the guardrail verifier (messages with a guardrail report).",
    "guardrail_failures": "Rows in the guardrail event log: drafts, refused edits, send-gate refusals, "
    "suspected injections, model budget and tool refusals.",
    "incorrect_amounts_blocked": "Guardrail events with an amount or total mismatch, or an invented amount.",
    "prompt_attacks_blocked": "Customer text that matched the injection patterns; the reply was escalated to a human.",
    "human_approvals": "Messages approved by a signed-in person.",
    "automatic_approvals": "Messages approved by the system under Trusted mode's allow-list.",
    "automatic_sends": "Messages sent with no human approval.",
    "send_gate_refusals": "Send attempts the send gate refused (not approved, kill switch, dispute, flag off).",
}


def safety(session: Session) -> Safety:
    r = session.execute(
        text("""SELECT
        (SELECT count(*) FROM messages WHERE guardrail_report IS NOT NULL) AS checked,
        (SELECT count(*) FROM messages WHERE verified_version = version) AS passed,
        (SELECT count(*) FROM guardrail_events) AS failures,
        (SELECT count(*) FROM guardrail_events WHERE code = ANY(CAST(:amt AS text[]))) AS amounts,
        (SELECT count(*) FROM guardrail_events WHERE code = ANY(CAST(:inj AS text[]))) AS injections,
        (SELECT count(*) FROM messages WHERE approved_by IS NOT NULL) AS human,
        (SELECT count(*) FROM messages WHERE status = 'rejected') AS rejected,
        (SELECT count(*) FROM messages WHERE approved_at IS NOT NULL AND approved_by IS NULL) AS auto_approved,
        (SELECT count(*) FROM messages WHERE status = 'sent' AND approved_by IS NULL) AS auto_sent,
        (SELECT count(*) FROM guardrail_events WHERE check_name = 'send_gate') AS gate,
        (SELECT count(*) FROM agent_steps WHERE error_code IS NOT NULL) AS tools_refused,
        s.sending_enabled, s.autonomy_mode, s.llm_budget_micro_usd,
        (SELECT COALESCE(SUM(cost_micro_usd), 0) FROM llm_calls) AS spent
        FROM settings s WHERE s.id = 1"""),
        {"amt": list(AMOUNT_CODES), "inj": list(INJECTION_CODES)},
    ).one()
    by_code = [
        CodeCount(check_name=c.check_name, code=c.code, count=c.n)
        for c in session.execute(
            text("""SELECT check_name, code, count(*) AS n FROM guardrail_events
            GROUP BY check_name, code ORDER BY n DESC, code LIMIT 30""")
        )
    ]
    return Safety(
        messages_checked=r.checked,
        messages_passed=r.passed,
        guardrail_failures=r.failures,
        incorrect_amounts_blocked=r.amounts,
        prompt_attacks_blocked=r.injections,
        human_approvals=r.human,
        human_rejections=r.rejected,
        automatic_approvals=r.auto_approved,
        automatic_sends=r.auto_sent,
        send_gate_refusals=r.gate,
        tool_calls_refused=r.tools_refused,
        kill_switch="READY (sending on)" if r.sending_enabled else "ENGAGED (sending paused)",
        autonomy_mode=r.autonomy_mode,
        llm_spent_micro_usd=int(r.spent),
        llm_budget_micro_usd=r.llm_budget_micro_usd,
        by_code=by_code,
        sources=SOURCES,
    )
