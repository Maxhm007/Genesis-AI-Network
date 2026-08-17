from __future__ import annotations

import html
import json
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from .modules.task_queue import PersistentTaskQueue


@dataclass(frozen=True)
class EmailDeliveryConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str
    use_ssl: bool = True

    @classmethod
    def from_env(cls) -> "EmailDeliveryConfig":
        required = {
            "GENESIS_SMTP_HOST": os.environ.get("GENESIS_SMTP_HOST", "").strip(),
            "GENESIS_SMTP_USERNAME": os.environ.get("GENESIS_SMTP_USERNAME", "").strip(),
            "GENESIS_SMTP_PASSWORD": os.environ.get("GENESIS_SMTP_PASSWORD", "").strip(),
            "GENESIS_EMAIL_TO": os.environ.get("GENESIS_EMAIL_TO", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError("missing Genesis email configuration: " + ", ".join(missing))
        username = required["GENESIS_SMTP_USERNAME"]
        sender = os.environ.get("GENESIS_EMAIL_FROM", "").strip() or f"Genesis AI <{username}>"
        return cls(
            host=required["GENESIS_SMTP_HOST"],
            port=int(os.environ.get("GENESIS_SMTP_PORT", "465")),
            username=username,
            password=required["GENESIS_SMTP_PASSWORD"],
            sender=sender,
            recipient=required["GENESIS_EMAIL_TO"],
            use_ssl=os.environ.get("GENESIS_SMTP_SSL", "true").strip().lower() not in {"0", "false", "no"},
        )


class GenesisEmailReporter:
    """Compose and deliver Genesis-owned operational KPI reports.

    The reporter reads Genesis runtime evidence and never invents missing KPIs.
    Delivery credentials are accepted only through environment variables so
    secrets never need to enter the repository or Genesis memory.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"

    @staticmethod
    def _load_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            return {}

    @staticmethod
    def _score(value: object, maximum: object = 100) -> str:
        if value is None:
            return "Unmeasured"
        try:
            return f"{float(value):g}/{float(maximum):g}"
        except Exception:
            return "Unmeasured"

    def snapshot(self) -> dict:
        scorecard = self._load_json(self.runtime / "system_scorecard.json")
        security = self._load_json(self.runtime / "security_report.json")
        memory = self._load_json(self.runtime / "memory_status.json")
        learning = self._load_json(self.runtime / "self_learning_status.json")
        capability = self._load_json(self.runtime / "capability_growth_sync.json")

        queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        tasks = queue.list(limit=1000)
        open_tasks = sum(1 for item in tasks if item.state in {"new", "assigned", "running", "review"})
        blocked_tasks = sum(1 for item in tasks if item.state == "blocked")

        ai = scorecard.get("ai_capability_score", {})
        efficiency = scorecard.get("efficiency_score", {})
        research = scorecard.get("immortality_research_progress_score", {})

        security_status = str(security.get("status") or "unmeasured").lower()
        security_indicator = "✅" if security_status in {"pass", "healthy", "ok"} else ("⚠️" if security_status == "unmeasured" else "❌")

        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ai_score": self._score(ai.get("score"), ai.get("max_score", 100)),
            "efficiency_score": self._score(efficiency.get("score"), efficiency.get("max_score", 100)),
            "capability_per_compute": efficiency.get("capability_per_compute", "Unmeasured"),
            "efficiency_samples": efficiency.get("samples", "Unmeasured"),
            "research_score": self._score(research.get("score"), research.get("max_score", 100)),
            "research_interpretation": research.get("interpretation", "Evidence-pipeline progress; not percent immortality achieved."),
            "security": f"{security_indicator} {security_status}",
            "memory": memory.get("status", "Unmeasured"),
            "memory_total": memory.get("total", memory.get("memories", "Unmeasured")),
            "self_learning": learning.get("status", "Unmeasured"),
            "open_tasks": open_tasks,
            "blocked_tasks": blocked_tasks,
            "capability_sync": capability.get("status", "Unmeasured"),
            "provider_telemetry": capability.get("providers", capability.get("provider_telemetry", "Unmeasured")),
        }

    def render(self, snapshot: dict) -> tuple[str, str, str]:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subject = f"Genesis Hourly Update — {stamp}"
        rows = [
            ("AI Capability Score", snapshot["ai_score"]),
            ("Efficiency Score", snapshot["efficiency_score"]),
            ("Capability / Compute", snapshot["capability_per_compute"]),
            ("Efficiency Samples", snapshot["efficiency_samples"]),
            ("Immortality Research Progress", snapshot["research_score"]),
            ("Security", snapshot["security"]),
            ("Memory", f"{snapshot['memory']} · {snapshot['memory_total']} records"),
            ("Self-Learning", snapshot["self_learning"]),
            ("Open Tasks", snapshot["open_tasks"]),
            ("Blocked Tasks", snapshot["blocked_tasks"]),
            ("Capability Integration", snapshot["capability_sync"]),
        ]
        text_lines = ["GENESIS AI — HOURLY KPI DASHBOARD", "", f"Generated: {stamp}", ""]
        text_lines.extend(f"{name}: {value}" for name, value in rows)
        text_lines += ["", "Research score note:", str(snapshot["research_interpretation"]), "", "This report was generated and sent by Genesis runtime automation."]
        text = "\n".join(text_lines)

        table_rows = "".join(
            f"<tr><td style='padding:8px;border-bottom:1px solid #ddd'>{html.escape(str(name))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #ddd;font-weight:600'>{html.escape(str(value))}</td></tr>"
            for name, value in rows
        )
        body = f"""<!doctype html><html><body style='font-family:Arial,sans-serif;color:#202124'>
        <div style='max-width:760px;margin:auto'>
          <h2>Genesis AI — Hourly Dashboard</h2>
          <p><strong>{html.escape(stamp)}</strong></p>
          <div style='display:flex;gap:12px;flex-wrap:wrap;margin:16px 0'>
            <div style='padding:14px;border:1px solid #ddd;border-radius:10px'><small>AI Capability</small><br><strong style='font-size:24px'>{html.escape(str(snapshot['ai_score']))}</strong></div>
            <div style='padding:14px;border:1px solid #ddd;border-radius:10px'><small>Efficiency</small><br><strong style='font-size:24px'>{html.escape(str(snapshot['efficiency_score']))}</strong></div>
            <div style='padding:14px;border:1px solid #ddd;border-radius:10px'><small>Research Progress</small><br><strong style='font-size:24px'>{html.escape(str(snapshot['research_score']))}</strong></div>
          </div>
          <table style='width:100%;border-collapse:collapse'>{table_rows}</table>
          <p style='margin-top:18px'><strong>Research score note:</strong> {html.escape(str(snapshot['research_interpretation']))}</p>
          <p style='font-size:12px;color:#666'>Generated and sent directly by Genesis runtime automation.</p>
        </div></body></html>"""
        return subject, text, body

    def send(self, config: EmailDeliveryConfig) -> dict:
        snapshot = self.snapshot()
        subject, text, body = self.render(snapshot)
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = config.sender
        message["To"] = config.recipient
        message.set_content(text)
        message.add_alternative(body, subtype="html")

        if config.use_ssl:
            with smtplib.SMTP_SSL(config.host, config.port, timeout=30) as smtp:
                smtp.login(config.username, config.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(config.username, config.password)
                smtp.send_message(message)
        return {"status": "sent", "recipient": config.recipient, "subject": subject, "snapshot": snapshot}
