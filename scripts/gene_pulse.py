from __future__ import annotations

"""Gene Pulse entry point with direct, source-driven learning capability routing.

Research intake is deterministic: Genesis derives a bounded capability proposal
from trusted-source title/summary evidence and routes it to an existing same-domain
target when grounded, otherwise to the learned-capability incubator.  No reasoning
provider is called during research intake or capability mapping.  Development,
review, validation, provenance, and promotion gates remain unchanged.
"""

from dataclasses import asdict, replace

from genesis.evolution_learning import ResearchItem
from scripts import gene_pulse_core as _core


class PulseEvolutionLearningEngine(_core.PulseEvolutionLearningEngine):
    """Allow external research to expand Genesis without a model-gated intake step."""

    EMERGING_CAPABILITY_DOMAIN = "emerging_capability"
    POLICY_REPLAY_META_KEY = "open_ended_new_capability_policy_v1_replayed"
    DIRECT_ROUTING_REPLAY_META_KEY = "direct_research_routing_v2_replayed"
    DIRECT_ROUTING_CONFIDENCE = 0.80

    @classmethod
    def _capability_domains(
        cls,
        text: str,
        *,
        allow_single_strong: bool = True,
        min_hits: int = 2,
    ) -> dict[str, list[str]]:
        """Keep known-domain evidence but never make the known list a hard boundary."""
        domains = dict(
            super()._capability_domains(
                text,
                allow_single_strong=allow_single_strong,
                min_hits=min_hits,
            )
        )
        domains.setdefault(
            cls.EMERGING_CAPABILITY_DOMAIN,
            ["grounded_external_research"],
        )
        return domains

    @classmethod
    def _target_domains(cls, path: str, text: str) -> dict[str, list[str]]:
        """Never use the synthetic emerging domain as evidence for an old target."""
        domains = dict(super()._target_domains(path, text))
        domains.pop(cls.EMERGING_CAPABILITY_DOMAIN, None)
        return domains

    @classmethod
    def _known_research_domains(cls, item: ResearchItem) -> dict[str, list[str]]:
        """Classify only against concrete existing domains, without the synthetic fallback."""
        return _core.PulseEvolutionLearningEngine._capability_domains(
            f"{item.title}\n{item.summary}"
        )

    def _source_driven_lesson(self, item: ResearchItem) -> dict:
        """Build a grounded capability proposal directly from source text.

        The source itself supplies the lesson/evidence boundary.  This deliberately
        avoids asking a language model to summarize or approve the research.
        """
        technical_source = self._technical_excerpt(item)
        if len(technical_source) < 24:
            return {"decision": "skip", "reason": "no_technical_source"}

        evidence, overlap = self._best_exact_anchor(
            str(item.summary or ""),
            [item.title, technical_source[:300]],
            min_overlap=1,
        )
        if not evidence:
            segments = self._exact_segments(str(item.summary or ""))
            evidence = segments[0] if segments else ""
        if not evidence:
            return {"decision": "skip", "reason": "no_exact_source_evidence"}

        known_domains = self._known_research_domains(item)
        capability_domains = sorted(known_domains) or [self.EMERGING_CAPABILITY_DOMAIN]
        topics: list[str] = []
        for domain in sorted(known_domains):
            topics.extend(known_domains[domain][:3])
        if not topics:
            topics = sorted(self._match_tokens(item.title))[:8]

        lesson = (
            f"Research-backed capability candidate from '{item.title}': "
            f"{evidence}"
        )[:1000]
        return {
            "decision": "learn",
            "lesson": lesson,
            "lesson_evidence": evidence[:1200],
            "lesson_evidence_overlap": overlap,
            "topics": topics[:8],
            "confidence_normalized": self.DIRECT_ROUTING_CONFIDENCE,
            "technical_source": technical_source,
            "relevance_hits": [
                f"{domain}:{term}"
                for domain, terms in sorted(known_domains.items())
                for term in terms[:4]
            ][:16],
            "research_domains": sorted(known_domains),
            "capability_domains": capability_domains,
            "routing_mode": "direct_source_evidence",
            "research_title": item.title[:500],
            "research_source": item.source[:500],
            "research_url": item.url[:1000],
        }

    def _extract_lesson(self, item: ResearchItem) -> dict:
        """Compatibility hook: research comprehension is now deterministic."""
        return self._source_driven_lesson(item)

    def _assess(self, item: ResearchItem) -> dict:
        """Route research without any provider call.

        Existing targets are selected only when deterministic domain and code-evidence
        checks support them.  Otherwise the grounded source is routed to the bounded
        learned-capability incubator.
        """
        lesson = self._source_driven_lesson(item)
        if lesson.get("decision") != "learn":
            return lesson

        topics = list(lesson.get("topics") or [])
        capability_domains = list(lesson.get("capability_domains") or [])
        concrete_domains = [
            domain
            for domain in capability_domains
            if domain != self.EMERGING_CAPABILITY_DOMAIN
        ]

        if not concrete_domains:
            return self._new_capability_finding(
                lesson,
                planner_reason="no_existing_capability_domain",
            )

        planning_item = replace(
            item,
            title=item.title[:300],
            summary=(
                f"SOURCE_EVIDENCE: {lesson['lesson_evidence']}\n"
                f"CAPABILITY_DOMAINS: {', '.join(concrete_domains)}"
            )[: self.MAX_PULSE_LEARNING_BYTES],
        )
        catalog = self._catalog_for_domains(planning_item, concrete_domains)
        if not catalog:
            return self._new_capability_finding(
                lesson,
                planner_reason="no_relevant_genesis_target",
            )

        target, target_context = catalog[0]
        target_domains = self._target_domains(target, target_context)
        shared_target_domains = sorted(set(concrete_domains) & set(target_domains))
        target_evidence, target_overlap = self._best_exact_anchor(
            target_context,
            [item.title, lesson["lesson_evidence"], *topics],
            min_overlap=self.MIN_TARGET_EVIDENCE_OVERLAP,
        )

        if not shared_target_domains or not target_evidence:
            return self._new_capability_finding(
                lesson,
                planner_reason="ungrounded_existing_target",
            )

        return {
            "decision": "upgrade",
            "target_path": target,
            "summary": (
                f"Apply the source-backed capability described by '{item.title}' "
                f"to the deterministically ranked Genesis target {target}."
            )[:2400],
            "acceptance": (
                "The target measurably applies the source-backed capability, preserves "
                "all existing security/review/validation/provenance safeguards, adds or "
                "updates focused tests, and the full repository test suite passes."
            ),
            "learning_evidence": lesson["lesson_evidence"][:1200],
            "target_evidence": target_evidence[:1200],
            "confidence_normalized": self.DIRECT_ROUTING_CONFIDENCE,
            "grounded": True,
            "reason": "deterministic_source_routing",
            "lesson": lesson["lesson"],
            "lesson_evidence": lesson["lesson_evidence"],
            "lesson_confidence_normalized": lesson["confidence_normalized"],
            "lesson_topics": topics,
            "capability_domains": concrete_domains,
            "target_capability_domains": sorted(target_domains),
            "shared_capability_domains": shared_target_domains,
            "target_evidence_overlap": target_overlap,
            "routing_mode": "direct_source_evidence",
            "research_title": item.title[:500],
            "research_source": item.source[:500],
            "research_url": item.url[:1000],
        }

    def _replay_evaluated_for_new_capability_policy(self) -> int:
        """Retain the v1 replay marker for backward compatibility."""
        if self.store.meta_get(self.POLICY_REPLAY_META_KEY) == "done":
            return 0

        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """
                SELECT r.fingerprint
                FROM research_items AS r
                WHERE r.status='evaluated'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM upgrade_opportunities AS u
                      WHERE u.research_fingerprint=r.fingerprint
                  )
                ORDER BY r.published_at DESC, r.first_seen_at ASC
                """
            ).fetchall()
            fingerprints = [str(row["fingerprint"]) for row in rows]
            if fingerprints:
                db.execute(
                    """
                    UPDATE research_items
                    SET status='pending',
                        retry_count=0,
                        next_retry_at=NULL,
                        last_error=NULL,
                        processing_started_at=NULL,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE status='evaluated'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM upgrade_opportunities AS u
                          WHERE u.research_fingerprint=research_items.fingerprint
                      )
                    """
                )

        self.store.meta_set(self.POLICY_REPLAY_META_KEY, "done")
        if fingerprints:
            self.store.event(
                event_type="learning_policy_replay",
                status="ok",
                message=(
                    f"Requeued {len(fingerprints)} previously evaluated research items "
                    "for open-ended capability reconsideration."
                ),
                details={
                    "policy": "grounded_lesson_may_create_new_capability",
                    "replayed_count": len(fingerprints),
                    "fingerprints": fingerprints[:100],
                },
            )
        return len(fingerprints)

    def _replay_provider_failures_for_direct_routing(self) -> int:
        """Requeue old model-intake failures once now that intake is model-free."""
        if self.store.meta_get(self.DIRECT_ROUTING_REPLAY_META_KEY) == "done":
            return 0

        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """
                SELECT r.fingerprint
                FROM research_items AS r
                WHERE r.status IN ('evaluated', 'waiting', 'quarantined')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM upgrade_opportunities AS u
                      WHERE u.research_fingerprint=r.fingerprint
                  )
                ORDER BY r.published_at DESC, r.first_seen_at ASC
                """
            ).fetchall()
            fingerprints = [str(row["fingerprint"]) for row in rows]
            if fingerprints:
                placeholders = ",".join("?" for _ in fingerprints)
                db.execute(
                    f"""
                    UPDATE research_items
                    SET status='pending',
                        retry_count=0,
                        next_retry_at=NULL,
                        last_error=NULL,
                        processing_started_at=NULL,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE fingerprint IN ({placeholders})
                    """,
                    fingerprints,
                )

        self.store.meta_set(self.DIRECT_ROUTING_REPLAY_META_KEY, "done")
        if fingerprints:
            self.store.event(
                event_type="learning_policy_replay",
                status="ok",
                message=(
                    f"Requeued {len(fingerprints)} prior learning assessments for "
                    "direct source-driven routing with no reasoning-provider intake."
                ),
                details={
                    "policy": "direct_source_evidence_no_qwen_intake",
                    "replayed_count": len(fingerprints),
                    "fingerprints": fingerprints[:100],
                },
            )
        return len(fingerprints)

    def refresh_sources(self) -> dict:
        result = dict(super().refresh_sources())
        replayed_v1 = self._replay_evaluated_for_new_capability_policy()
        replayed_direct = self._replay_provider_failures_for_direct_routing()
        result["open_capability_policy"] = "enabled"
        result["research_intake_mode"] = "direct_source_evidence"
        result["provider_used_for_research_intake"] = False
        result["policy_replay_count"] = replayed_v1
        result["direct_routing_replay_count"] = replayed_direct
        return result


# The core functions resolve PulseEvolutionLearningEngine from their own module
# globals. Replace that binding before exposing/using the original entry points.
_core.PulseEvolutionLearningEngine = PulseEvolutionLearningEngine

ROOT = _core.ROOT
_run_learning_evolution = _core._run_learning_evolution
main = _core.main


if __name__ == "__main__":
    raise SystemExit(main())
