from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class Evidence:
    id: str
    competitor: str
    source_type: str
    title: str
    url: str
    excerpt: str
    confidence: float


@dataclass
class CompetitorProfile:
    name: str
    company: str
    positioning: str
    target_users: List[str]
    core_features: List[str]
    pricing: str
    differentiators: List[str]
    risks: List[str]
    evidence_ids: List[str]


@dataclass
class AgentTrace:
    agent: str
    status: str
    input_summary: str
    output_summary: str
    artifacts: Dict[str, Any] = field(default_factory=dict)


def to_dict(value: Any) -> Any:
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
