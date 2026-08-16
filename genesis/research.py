from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchItem:
    source: str
    title: str
    url: str
    published: str | None
    summary: str
    evidence_status: str = "candidate"


class ResearchEngine:
    """Read-only scientific literature discovery.

    V0.1 uses Europe PMC's public REST API for longevity-related literature.
    Results are metadata/abstract candidates only and must pass later review.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def search_europe_pmc(self, query: str, limit: int = 5) -> list[ResearchItem]:
        params = urllib.parse.urlencode({
            "query": query,
            "format": "json",
            "pageSize": max(1, min(limit, 20)),
        })
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Genesis-AI-Network/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        out: list[ResearchItem] = []
        for item in payload.get("resultList", {}).get("result", []):
            identifier = item.get("pmcid") or item.get("pmid") or item.get("id") or ""
            source_url = f"https://europepmc.org/article/{item.get('source','MED')}/{identifier}" if identifier else url
            out.append(ResearchItem(
                source="Europe PMC",
                title=item.get("title") or "Untitled",
                url=source_url,
                published=item.get("firstPublicationDate") or item.get("pubYear"),
                summary=item.get("authorString") or "",
            ))
        return out

    def longevity_scan(self, limit: int = 5) -> list[ResearchItem]:
        return self.search_europe_pmc(
            '(aging OR ageing OR senescence OR "healthy longevity" OR "regenerative medicine")',
            limit=limit,
        )
