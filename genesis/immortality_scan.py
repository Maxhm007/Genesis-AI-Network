from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .modules.task_queue import PersistentTaskQueue
from .research import ResearchEngine, ResearchItem


DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "biology_medicine": ("aging", "ageing", "senescence", "cell", "gene", "genome", "protein", "cancer", "disease", "regeneration", "stem cell", "organ", "immune", "metabolism", "brain", "neural", "drug", "therapy"),
    "ai_computing": ("artificial intelligence", " ai ", "model", "robot", "automation", "compute", "algorithm", "software", "semiconductor", "quantum computing"),
    "energy_materials": ("energy", "battery", "fusion", "solar", "material", "manufacturing", "nanotechnology", "sensor", "storage"),
    "space_survival": ("space", "mars", "moon", "radiation", "astronaut", "life support", "closed loop", "habitat", "microgravity"),
    "environment_food": ("climate", "pollution", "air quality", "water", "agriculture", "food", "ecosystem", "pathogen", "pandemic"),
    "physics_foundations": ("physics", "quantum", "thermodynamic", "entropy", "time", "matter", "particle"),
    "society_governance": ("policy", "law", "economy", "education", "security", "privacy", "ethics", "governance", "infrastructure"),
}

DIRECT_TERMS = (
    "immortality", "longevity", "lifespan", "healthspan", "rejuvenation", "anti-aging", "anti ageing",
    "senolytic", "epigenetic reprogramming", "regenerative medicine", "organ replacement", "aging reversal",
)

PATHWAY_HINTS: dict[str, str] = {
    "biology_medicine": "May affect prevention, repair, regeneration, disease control, aging mechanisms, or preservation of cognition/body function.",
    "ai_computing": "May improve discovery speed, scientific reasoning, robotics, automation, diagnostics, simulation, or distributed Genesis capability.",
    "energy_materials": "May improve durable bodies/devices, medical hardware, manufacturing, sensors, power availability, or long-duration autonomous systems.",
    "space_survival": "May reveal human survival limits and technologies for radiation protection, life support, low-gravity health, resilience, and off-world continuity.",
    "environment_food": "May alter disease burden, exposure risk, nutrition, ecosystem stability, or conditions required for long-term healthy human survival.",
    "physics_foundations": "Could eventually constrain or enable energy, matter, measurement, computation, preservation, or other physical mechanisms; relevance may be speculative.",
    "society_governance": "May affect access, safety, research coordination, funding, privacy, consent, infrastructure, or governance of immortality-enabling technologies.",
}


@dataclass(frozen=True)
class ScanItem:
    source: str
    title: str
    url: str
    published: str | None
    summary: str


@dataclass(frozen=True)
class ImmortalityAssessment:
    source: str
    title: str
    url: str
    published: str | None
    relevance_score: int
    relevance: str
    domains: tuple[str, ...]
    pathway: str
    action: str
    evidence_status: str = "candidate"


class ImmortalityScanner:
    """Broad discovery with an explicit physical-human-immortality relevance lens."""

    def __init__(self, root: Path, timeout: float = 12.0) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self.research = ResearchEngine(timeout=timeout)

    @staticmethod
    def _text(item: ScanItem) -> str:
        return f" {item.title} {item.summary} ".lower()

    def assess(self, item: ScanItem) -> ImmortalityAssessment:
        text = self._text(item)
        domains = tuple(name for name, terms in DOMAIN_TERMS.items() if any(term in text for term in terms))
        direct_hits = sum(1 for term in DIRECT_TERMS if term in text)
        score = min(10, direct_hits * 3 + min(6, len(domains) * 2))
        if score >= 8:
            relevance = "direct_or_high"
            action = "create_priority_research_task"
        elif score >= 5:
            relevance = "plausible_indirect"
            action = "queue_for_cross_domain_review"
        elif score >= 2:
            relevance = "speculative_or_weak"
            action = "retain_as_low_priority_signal"
        else:
            relevance = "unknown"
            action = "do_not_force_connection"
        pathway = " ".join(PATHWAY_HINTS[name] for name in domains) if domains else (
            "No defensible pathway to physical human immortality was identified from the available title/summary."
        )
        return ImmortalityAssessment(
            source=item.source,
            title=item.title,
            url=item.url,
            published=item.published,
            relevance_score=score,
            relevance=relevance,
            domains=domains,
            pathway=pathway,
            action=action,
        )

    def _from_research(self, items: Iterable[ResearchItem]) -> list[ScanItem]:
        return [ScanItem(i.source, i.title, i.url, i.published, i.summary) for i in items]

    def fetch_rss(self, source: str, url: str, limit: int = 10) -> list[ScanItem]:
        request = urllib.request.Request(url, headers={"User-Agent": "Genesis-AI-Network/0.3"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            root = ET.fromstring(response.read())
        output: list[ScanItem] = []
        nodes = root.findall(".//item") or root.findall("{http://www.w3.org/2005/Atom}entry")
        for node in nodes[: max(1, min(limit, 30))]:
            def value(*names: str) -> str:
                for name in names:
                    child = node.find(name)
                    if child is not None and child.text:
                        return re.sub(r"\s+", " ", child.text).strip()
                return ""
            title = value("title", "{http://www.w3.org/2005/Atom}title") or "Untitled"
            summary = value("description", "summary", "{http://www.w3.org/2005/Atom}summary")
            published = value("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated") or None
            link = value("link")
            if not link:
                atom_link = node.find("{http://www.w3.org/2005/Atom}link")
                if atom_link is not None:
                    link = atom_link.attrib.get("href", "")
            output.append(ScanItem(source, title, link or url, published, summary))
        return output

    def queue_priority_tasks(self, assessments: list[ImmortalityAssessment]) -> dict[str, int]:
        queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")
        created = 0
        existing = 0
        for item in assessments:
            if item.relevance_score < 5:
                continue
            priority = min(100, 50 + item.relevance_score * 5)
            objective = (
                "Investigate this candidate development for a defensible pathway to continuous physical human immortality: "
                + item.title
            )
            _, was_created = queue.create_unique(
                "immortality-scan:" + item.url,
                objective,
                module_id="genesis.research",
                priority=priority,
                payload={
                    "task_type": "immortality_research",
                    "source": item.source,
                    "title": item.title,
                    "url": item.url,
                    "published": item.published,
                    "relevance_score": item.relevance_score,
                    "relevance": item.relevance,
                    "domains": list(item.domains),
                    "pathway_hypothesis": item.pathway,
                    "evidence_status": "candidate",
                    "required_next_stage": "multi_agent_review",
                },
            )
            created += int(was_created)
            existing += int(not was_created)
        return {"created": created, "already_present": existing}

    def scan(self, per_source: int = 8) -> dict:
        discovered: list[ScanItem] = []
        errors: list[dict[str, str]] = []
        try:
            discovered.extend(self._from_research(self.research.longevity_scan(limit=per_source)))
        except Exception as exc:
            errors.append({"source": "Europe PMC", "error": str(exc)})

        config_path = self.root / "config" / "immortality_sources.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            for feed in config.get("rss", []):
                if not feed.get("enabled", True):
                    continue
                try:
                    discovered.extend(self.fetch_rss(str(feed["name"]), str(feed["url"]), per_source))
                except Exception as exc:
                    errors.append({"source": str(feed.get("name", feed.get("url", "unknown"))), "error": str(exc)})

        return re.sub(r"\s+", " ", child.text).strip()
        assessments.sort(key=lambda item: (-item.relevance_score, item.source, item.title))
        priority = [item for item in assessments if item.relevance_score >= 5][:20]
        task_result = self.queue_priority_tasks(priority)
        created_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "created_at": created_at,
            "mission": "continuous physical human immortality research",
            "principle": "Consider broadly; never force unsupported relevance; validate before knowledge or code promotion.",
            "sources_checked": sorted({item.source for item in discovered}),
            "errors": errors,
            "items": [asdict(item) for item in assessments],
            "priority_items": [asdict(item) for item in priority],
            "persistent_tasks": task_result,
        }
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "immortality_scan.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload
