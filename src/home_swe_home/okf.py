"""Load OKF bundles as reviewer standards and verify cited concepts.

The reviewer receives OKF concepts as untrusted data together with their v0.3
trust/lifecycle metadata. Citations in the verdict are evidence (signal), not
authority (D-015), so they are checked against the concepts actually supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mth_components.bridges.okf_loader.trust import (
    is_stale,
    parse_frontmatter,
    trust_tier,
)


@dataclass(frozen=True)
class OkfConcept:
    bundle: str
    concept: str
    type: str
    status: str
    trust: str
    stale: bool
    text: str

    def citation(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle,
            "concept": self.concept,
            "type": self.type,
            "status": self.status,
            "trust": self.trust,
            "stale": self.stale,
        }


def load_okf_bundle(name: str, root: Path) -> list[OkfConcept]:
    """Load every concept in an OKF bundle directory."""
    concepts: list[OkfConcept] = []
    for path in sorted(root.rglob("*.md")):
        if path.name in ("index.md", "log.md") or any(
            part.startswith(".") for part in path.relative_to(root).parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        frontmatter = parse_frontmatter(text)
        if not frontmatter.get("type"):
            continue
        concepts.append(
            OkfConcept(
                bundle=name,
                concept=path.stem,
                type=str(frontmatter["type"]),
                status=str(frontmatter.get("status", "stable")),
                trust=trust_tier(frontmatter),
                stale=is_stale(frontmatter),
                text=text,
            )
        )
    return concepts


def render_okf_standards(concepts: list[OkfConcept]) -> str:
    """Render concepts with a metadata header for the reviewer prompt."""
    blocks: list[str] = []
    for concept in concepts:
        meta = concept.citation()
        header = (
            f"OKF concept: bundle={meta['bundle']} concept={meta['concept']} "
            f"type={meta['type']} status={meta['status']} "
            f"trust={meta['trust']} stale={str(meta['stale']).lower()}"
        )
        blocks.append(f"### {header}\n\n{concept.text.strip()}")
    return "\n\n".join(blocks)


def check_okf_citations(
    citations: list[dict[str, Any]], concepts: list[OkfConcept]
) -> list[dict[str, Any]]:
    """Verify each cited concept exists and its metadata matches the source."""
    known = {(c.bundle, c.concept): c for c in concepts}
    results: list[dict[str, Any]] = []
    for citation in citations:
        bundle = str(citation.get("bundle", ""))
        concept_id = str(citation.get("concept", ""))
        source = known.get((bundle, concept_id))
        if source is None:
            results.append(
                {
                    "bundle": bundle,
                    "concept": concept_id,
                    "status": "unknown-concept",
                    "detail": "cited concept was not supplied as a standard",
                }
            )
            continue
        expected = source.citation()
        mismatches = [
            key
            for key in ("type", "status", "trust", "stale")
            if citation.get(key) != expected[key]
        ]
        results.append(
            {
                "bundle": bundle,
                "concept": concept_id,
                "status": "metadata-mismatch" if mismatches else "ok",
                "detail": ", ".join(mismatches) if mismatches else "",
            }
        )
    return results
