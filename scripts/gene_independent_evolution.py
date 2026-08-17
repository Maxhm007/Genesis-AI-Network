from __future__ import annotations

import json
from pathlib import Path

from genesis.independent_evolution import EvolutionProfile, IndependentGeneEvolution
from genesis.providers import ProviderRegistry


ROOT = Path(__file__).resolve().parents[1]

PROFILES = (
    EvolutionProfile("gene-node-2", "explorer_researcher", "breadth_first_exploration", "Find a high-leverage improvement to Gene's capabilities or development velocity."),
    EvolutionProfile("gene-node-3", "engineer_challenger", "skeptical_engineering_failure_first", "Find and fix a reliability, validation, repair, or implementation bottleneck in Gene."),
    EvolutionProfile("gene-node-4", "replicated_gene_worker", "novel_alternative_search", "Independently seek an alternative improvement path that Nodes 2 and 3 may overlook."),
    EvolutionProfile("gene-node-5", "replicated_gene_worker", "efficiency_and_simplification", "Independently seek a simpler or more resource-efficient way to improve Gene."),
)


def main() -> None:
    providers = ProviderRegistry()
    summaries = []
    for profile in PROFILES:
        node = IndependentGeneEvolution(ROOT, profile, providers=providers)
        record = node.run_cycle()
        packet = node.share_result(record)
        summaries.append(
            {
                "logical_id": profile.logical_id,
                "node_id": record["node_id"],
                "development_mode": record["development_mode"],
                "peer_packets_considered": record["peer_packets_considered"],
                "knowledge_packet_id": packet["packet_id"],
            }
        )
    print(json.dumps({"independent_gene_cycles": summaries}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
