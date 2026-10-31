"""Plugin port infrastructure (M0/M1)."""

from .claim_contracts import (
    ClaimInput,
    ClaimVerification,
    ClaimVerifierAdapter,
    ClaimVerifierPort,
    EvidenceInput,
)
from .contracts import (
    ManifestError,
    PluginError,
    PluginExecutionError,
    PluginManifest,
    PluginNotFound,
    PluginRun,
    PortContract,
    PortSpec,
)
from .registry import PluginRegistry
from .runner import PluginRunner

__all__ = [
    "ClaimInput",
    "ClaimVerification",
    "ClaimVerifierAdapter",
    "ClaimVerifierPort",
    "EvidenceInput",
    "ManifestError",
    "PluginError",
    "PluginExecutionError",
    "PluginManifest",
    "PluginNotFound",
    "PluginRegistry",
    "PluginRun",
    "PluginRunner",
    "PortContract",
    "PortSpec",
]
