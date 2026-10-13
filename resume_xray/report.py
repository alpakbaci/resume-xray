"""Findings and the parseability verdict (ALGORITHM.md §2)."""

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["critical", "warning", "info"]
Verdict = Literal["OK", "Risky", "Unreadable"]


@dataclass
class Finding:
    check: str
    severity: Severity
    title: str
    detail: str
    fix: str | None = None
    # Reading strategies this problem affects; empty when it does not depend on the reader.
    strategies: tuple[str, ...] = ()
    pages: tuple[int, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass
class Report:
    document: str
    kind: str
    pages: int
    findings: list[Finding]
    # Canonical section name -> heading text as it appears in the resume.
    sections: dict[str, str] = field(default_factory=dict)
    # Contact fields found in the text: email, phone, linkedin.
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def verdict(self) -> Verdict:
        severities = {f.severity for f in self.findings}
        if "critical" in severities:
            return "Unreadable"
        if "warning" in severities:
            return "Risky"
        return "OK"
