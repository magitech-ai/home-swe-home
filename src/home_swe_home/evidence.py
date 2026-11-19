"""Mechanical validation of a reviewer's cited evidence.

A verdict is a signal, not authority. Shape is already validated strictly; this
module checks the weaker but useful claim that each finding points at something
that exists — a path in the diff, a file in the repository, or a documented rule.
It cannot judge whether the citation *supports* the finding; that remains a job
for the human gate and, later, an independent verifier.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class HasEvidence(Protocol):
    """Structural type so this module does not import the reviewer."""

    evidence: str


PATH_PATTERN = re.compile(r"(?:[\w@-]+/)*[\w@-]+\.[\w-]+(?::\d+(?:-\d+)?)?")
RULE_PREFIXES = ("standard", "acceptance criteria", "documented", "review contract")


@dataclass(frozen=True)
class EvidenceCheck:
    """Where a finding's cited evidence resolved."""

    evidence: str
    status: str  # diff | repo | rule | unverifiable

    def to_dict(self) -> dict[str, str]:
        return {"evidence": self.evidence, "status": self.status}


def _diff_paths(diff: str) -> set[str]:
    paths: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            paths.add(line[6:].strip())
        elif line.startswith("diff --git a/"):
            parts = line.split()
            if len(parts) >= 4:
                paths.add(parts[3].removeprefix("b/"))
    return paths


def check_finding_evidence(
    findings: Sequence[HasEvidence], *, diff: str, root: Path
) -> list[EvidenceCheck]:
    """Resolve each finding's citation against the diff, repo, or rule set."""
    paths = _diff_paths(diff)
    checks: list[EvidenceCheck] = []
    for finding in findings:
        text = finding.evidence.strip()
        lowered = text.lower()
        if any(prefix in lowered for prefix in RULE_PREFIXES):
            checks.append(EvidenceCheck(text, "rule"))
            continue
        match = PATH_PATTERN.search(text)
        if match is None:
            checks.append(EvidenceCheck(text, "unverifiable"))
            continue
        cited = match.group(0).split(":")[0]
        if cited in paths:
            checks.append(EvidenceCheck(text, "diff"))
        elif (root / cited).is_file():
            checks.append(EvidenceCheck(text, "repo"))
        else:
            checks.append(EvidenceCheck(text, "unverifiable"))
    return checks
