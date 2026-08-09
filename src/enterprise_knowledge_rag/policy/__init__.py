"""Deterministic access and document-version rules."""

from .access import AccessDecision, can_access, evaluate_access
from .versioning import (
    VersionResolution,
    VersionResolutionStatus,
    resolve_effective_versions,
)

__all__ = [
    "AccessDecision",
    "VersionResolution",
    "VersionResolutionStatus",
    "can_access",
    "evaluate_access",
    "resolve_effective_versions",
]
