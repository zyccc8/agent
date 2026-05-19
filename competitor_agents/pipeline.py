from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import uuid4

from .agents import AnalysisAgent, CleaningAgent, CollectionAgent, QAAgent, ReportAgent
from .models import to_dict


DEFAULT_INDUSTRY = "AI 笔记工具"
DEFAULT_COMPETITORS = ["Notion AI", "Mem", "Reflect", "Evernote AI"]


WORKFLOW_DAG = [
    {"id": "collect", "label": "采集 Agent", "depends_on": []},
    {"id": "clean", "label": "清洗 Agent", "depends_on": ["collect"]},
    {"id": "analyze", "label": "分析 Agent", "depends_on": ["clean"]},
    {"id": "report", "label": "报告撰写 Agent", "depends_on": ["analyze"]},
    {"id": "qa", "label": "质检/溯源 Agent", "depends_on": ["report"]},
]


def run_pipeline(industry: str, competitors: List[str], use_live_sources: bool = False) -> dict:
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    traces = []

    evidence, trace = CollectionAgent().run(industry, competitors, use_live_sources)
    traces.append(trace)

    cleaned_evidence, trace = CleaningAgent().run(evidence)
    traces.append(trace)

    profiles, comparison, trace = AnalysisAgent().run(industry, competitors, cleaned_evidence)
    traces.append(trace)

    report, trace = ReportAgent().run(industry, profiles, comparison, cleaned_evidence)
    traces.append(trace)

    quality, trace = QAAgent().run(profiles, cleaned_evidence, report)
    traces.append(trace)

    return {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "industry": industry,
        "competitors": competitors,
        "use_live_sources": use_live_sources,
        "workflow_dag": WORKFLOW_DAG,
        "evidence": to_dict(cleaned_evidence),
        "profiles": to_dict(profiles),
        "comparison": comparison,
        "report": report,
        "quality": quality,
        "traces": to_dict(traces),
    }
