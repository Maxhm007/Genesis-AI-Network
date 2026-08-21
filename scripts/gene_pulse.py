from __future__ import annotations

"""Gene Pulse entry point with open-ended learning capability routing.

The original bounded Pulse implementation lives in ``gene_pulse_core``.  This
entry point extends only the learning policy: a grounded transferable lesson is
allowed to describe a capability Genesis does not already have.  Existing
security, evidence, review, validation, and promotion gates remain unchanged.
"""

from scripts import gene_pulse_core as _core


class PulseEvolutionLearningEngine(_core.PulseEvolutionLearningEngine):
    """Allow verified external learning to expand Genesis's capability space."""

    EMERGING_CAPABILITY_DOMAIN = "emerging_capability"
    POLICY_REPLAY_META_KEY = "open_ended_new_capability_policy_v1_replayed"

    @classmethod
    def _capability_domains(
        cls,
        text: str,
        *,
        allow_single_strong: bool = True,
        min_hits: int = 2,
    ) -> dict[str, list[str]]:
        """Keep known-domain evidence but never make the known list a hard boundary.

        ``emerging_capability`` is deliberately synthetic.  It means only that a
        grounded transferable lesson may be considered even when Genesis has no
        matching pre-existing capability label.  It is removed from code-target
        classification below, so it cannot manufacture a false existing target.
        """
        domains = dict(
            super()._capability_domains(
                text,
                allow_single_strong=allow_single_strong,
                min_hits=min_hits,
            )
        )
        domains.setdefault(
            cls.EMERGING_CAPABILITY_DOMAIN,
            ["grounded_transferable_external_learning"],
        )
        return domains

    @classmethod
    def _target_domains(cls, path: str, text: str) -> dict[str, list[str]]:
        """Never use the synthetic emerging domain as evidence for an old target."""
        domains = dict(super()._target_domains(path, text))
        domains.pop(cls.EMERGING_CAPABILITY_DOMAIN, None)
        return domains

    def _replay_evaluated_for_new_capability_policy(self) -> int:
        """Reconsider prior evaluated skips once under the open-ended policy.

        Only evaluated research without an upgrade opportunity is replayed.
        Quarantined provider failures are intentionally untouched.  The durable
        meta flag prevents an endless replay loop if an item is still rejected
        for a legitimate reason such as weak evidence or low confidence.
        """
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

    def refresh_sources(self) -> dict:
        result = dict(super().refresh_sources())
        replayed = self._replay_evaluated_for_new_capability_policy()
        result["open_capability_policy"] = "enabled"
        result["policy_replay_count"] = replayed
        return result


# The core functions resolve PulseEvolutionLearningEngine from their own module
# globals.  Replace that binding before exposing/using the original entry points.
_core.PulseEvolutionLearningEngine = PulseEvolutionLearningEngine

ROOT = _core.ROOT
_run_learning_evolution = _core._run_learning_evolution
main = _core.main


if __name__ == "__main__":
    raise SystemExit(main())
