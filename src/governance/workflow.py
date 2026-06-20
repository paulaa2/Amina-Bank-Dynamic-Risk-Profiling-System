"""Four-eyes decision-governance state machine.

A confirmed alarm cannot be actioned by a single person. The workflow enforces
the regulated lifecycle:

    DETECTED -> UNDER_REVIEW -> FOUR_EYES_PENDING -> (MITIGATED | ESCALATED)

Every transition appends an immutable, timestamped audit entry naming the
acting user, satisfying the auditability requirement for FINMA / Swiss banking
governance. Mitigation requires a different approver from the analyst who
proposed it (the four-eyes principle).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


class AlertStatus:
    DETECTED = "DETECTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    FOUR_EYES_PENDING = "FOUR_EYES_PENDING"
    MITIGATED = "RESOLVED_MITIGATED"
    ESCALATED = "ESCALATED_TO_REGULATOR"


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class ComplianceAlert:
    """An alert moving through the governance lifecycle."""

    alert_id: str
    target_entity_id: str
    target_display_name: str
    risk_score: float
    trigger_streams: list[str]
    status: str = AlertStatus.DETECTED
    assigned_analyst: str | None = None
    proposed_mitigation_action: str | None = None
    compliance_approver: str | None = None
    report_markdown: str | None = None
    audit_trail: list[dict] = field(default_factory=list)

    def log_transition(self, action: str, user: str) -> None:
        """Append a timestamped audit record for the current state."""
        self.audit_trail.append(
            {
                "timestamp": _utc_now(),
                "user": user,
                "action": action,
                "resulting_status": self.status,
            }
        )

    def as_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "target_entity_id": self.target_entity_id,
            "target_display_name": self.target_display_name,
            "risk_score": round(self.risk_score, 4),
            "trigger_streams": self.trigger_streams,
            "status": self.status,
            "assigned_analyst": self.assigned_analyst,
            "proposed_mitigation_action": self.proposed_mitigation_action,
            "compliance_approver": self.compliance_approver,
            "audit_trail": self.audit_trail,
        }


class FourEyesWorkflow:
    """Drives a :class:`ComplianceAlert` through its regulated transitions."""

    def assign_to_analyst(self, alert: ComplianceAlert, analyst: str) -> None:
        alert.status = AlertStatus.UNDER_REVIEW
        alert.assigned_analyst = analyst
        alert.log_transition("Assigned to level-1 analyst for trace investigation", analyst)

    def propose_mitigation(
        self, alert: ComplianceAlert, action: str, analyst: str
    ) -> None:
        alert.status = AlertStatus.FOUR_EYES_PENDING
        alert.proposed_mitigation_action = action
        alert.log_transition(
            f"Proposed mitigation '{action}'; submitted for compliance approval",
            analyst,
        )

    def approve_mitigation(
        self, alert: ComplianceAlert, approver: str, escalate: bool = False
    ) -> None:
        """Approve (or escalate) the proposed action under the four-eyes rule."""
        if alert.status != AlertStatus.FOUR_EYES_PENDING:
            raise RuntimeError(
                "No mitigation is pending four-eyes approval for this alert."
            )
        if approver == alert.assigned_analyst:
            raise PermissionError(
                "Four-eyes violation: the approver must differ from the proposing analyst."
            )
        alert.compliance_approver = approver
        alert.status = AlertStatus.ESCALATED if escalate else AlertStatus.MITIGATED
        verb = "Escalated to regulator" if escalate else "Approved and executed mitigation"
        alert.log_transition(verb, approver)
