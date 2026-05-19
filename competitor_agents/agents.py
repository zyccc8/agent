from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .models import AgentTrace, CompetitorProfile, Evidence
from .web_research import WebResearchClient, infer_source_type, page_to_excerpt


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data" / "demo_sources.json"


class CollectionAgent:
    name = "采集 Agent"

    def __init__(self, web_client: WebResearchClient | None = None) -> None:
        self.web_client = web_client or WebResearchClient()

    def run(
        self,
        industry: str,
        competitors: List[str],
        use_live_sources: bool = False,
    ) -> Tuple[List[Evidence], AgentTrace]:
        source_data = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
        records = source_data.get("sources", [])
        evidence: List[Evidence] = []
        live_pages = 0
        live_errors = []

        for competitor in competitors:
            competitor_evidence: List[Evidence] = []
            if use_live_sources:
                try:
                    pages = self.web_client.research_competitor(industry, competitor)
                    live_pages += len(pages)
                    for index, page in enumerate(pages, start=1):
                        excerpt = page_to_excerpt(page.text, competitor)
                        if not excerpt:
                            continue
                        competitor_evidence.append(
                            Evidence(
                                id=f"live-{slugify(competitor)}-{index}",
                                competitor=competitor,
                                source_type=infer_source_type(page.url, page.title, page.text),
                                title=page.title,
                                url=page.url,
                                excerpt=excerpt,
                                confidence=0.76,
                            )
                        )
                except Exception as exc:
                    live_errors.append(f"{competitor}: {exc.__class__.__name__}")

            matched = [
                item for item in records if item["competitor"].lower() == competitor.lower()
            ]
            if competitor_evidence:
                evidence.extend(competitor_evidence)
                continue

            if not matched:
                evidence.append(
                    Evidence(
                        id=f"missing-{slugify(competitor)}",
                        competitor=competitor,
                        source_type="missing",
                        title="待补充公开来源",
                        url="",
                        excerpt=f"没有在演示源库中找到 {competitor} 的公开信息，需要补充官网、定价页或新闻来源。",
                        confidence=0.1,
                    )
                )
                continue

            for index, item in enumerate(matched, start=1):
                evidence.append(
                    Evidence(
                        id=f"{slugify(competitor)}-{index}",
                        competitor=competitor,
                        source_type=item["source_type"],
                        title=item["title"],
                        url=item["url"],
                        excerpt=item["excerpt"],
                        confidence=float(item["confidence"]),
                    )
                )

        missing_count = sum(1 for e in evidence if e.source_type == "missing")
        mode = "实时网页搜索 + 演示数据降级" if use_live_sources else "演示数据"
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"行业：{industry}；竞品：{', '.join(competitors)}；模式：{mode}",
            output_summary=f"采集到 {len(evidence)} 条证据，其中 {missing_count} 条待补充，实时网页 {live_pages} 页。",
            artifacts={
                "evidence_count": len(evidence),
                "live_pages": live_pages,
                "live_errors": live_errors,
                "mode": mode,
            },
        )
        return evidence, trace


class CleaningAgent:
    name = "清洗 Agent"

    def run(self, evidence: List[Evidence]) -> Tuple[List[Evidence], AgentTrace]:
        seen = set()
        cleaned: List[Evidence] = []
        for item in evidence:
            key = (item.competitor.lower(), item.title.lower(), item.excerpt.lower())
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(item)

        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"原始证据 {len(evidence)} 条",
            output_summary=f"去重并规范化后保留 {len(cleaned)} 条证据。",
            artifacts={"removed_duplicates": len(evidence) - len(cleaned)},
        )
        return cleaned, trace


class AnalysisAgent:
    name = "分析 Agent"

    def run(self, industry: str, competitors: List[str], evidence: List[Evidence]) -> Tuple[List[CompetitorProfile], Dict[str, List[str]], AgentTrace]:
        grouped: Dict[str, List[Evidence]] = defaultdict(list)
        for item in evidence:
            grouped[item.competitor].append(item)

        profiles: List[CompetitorProfile] = []
        for competitor in competitors:
            items = grouped.get(competitor, [])
            text = " ".join(item.excerpt for item in items).lower()
            profiles.append(
                CompetitorProfile(
                    name=competitor,
                    company=infer_company(competitor),
                    positioning=infer_positioning(industry, text),
                    target_users=infer_target_users(text),
                    core_features=infer_features(text),
                    pricing=infer_pricing(text),
                    differentiators=infer_differentiators(text),
                    risks=infer_risks(items, text),
                    evidence_ids=[item.id for item in items],
                )
            )

        comparison = {
            "common_patterns": common_patterns(profiles),
            "opportunities": opportunity_points(profiles),
            "risks": shared_risks(profiles),
        }
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"输入 {len(evidence)} 条清洗证据",
            output_summary=f"生成 {len(profiles)} 个竞品画像和 {sum(len(v) for v in comparison.values())} 条比较洞察。",
            artifacts={"profile_count": len(profiles), "comparison": comparison},
        )
        return profiles, comparison, trace


class ReportAgent:
    name = "报告撰写 Agent"

    def run(self, industry: str, profiles: List[CompetitorProfile], comparison: Dict[str, List[str]], evidence: List[Evidence]) -> Tuple[str, AgentTrace]:
        evidence_map = {item.id: item for item in evidence}
        lines = [
            f"# {industry}竞品分析报告",
            "",
            "## 执行摘要",
            f"本次分析覆盖 {len(profiles)} 个竞品，围绕定位、功能、用户、价格、差异化和风险进行结构化比较。",
            "",
            "## 竞品画像",
        ]

        for profile in profiles:
            evidence_refs = ", ".join(f"[{item}]" for item in profile.evidence_ids)
            lines.extend(
                [
                    "",
                    f"### {profile.name}",
                    f"- 公司/产品：{profile.company}",
                    f"- 定位：{profile.positioning}",
                    f"- 目标用户：{', '.join(profile.target_users)}",
                    f"- 核心功能：{', '.join(profile.core_features)}",
                    f"- 价格策略：{profile.pricing}",
                    f"- 差异化：{', '.join(profile.differentiators)}",
                    f"- 风险：{', '.join(profile.risks)}",
                    f"- 证据：{evidence_refs or '暂无'}",
                ]
            )

        lines.extend(["", "## 横向洞察"])
        for title, items in [
            ("共同趋势", comparison["common_patterns"]),
            ("机会点", comparison["opportunities"]),
            ("主要风险", comparison["risks"]),
        ]:
            lines.append(f"### {title}")
            for item in items:
                lines.append(f"- {item}")

        lines.extend(["", "## 证据索引"])
        for item in evidence:
            source = item.url or "待补充"
            lines.append(f"- [{item.id}] {item.competitor}｜{item.source_type}｜{item.title}｜{source}｜置信度 {item.confidence:.2f}")
            lines.append(f"  - 摘录：{item.excerpt}")

        report = "\n".join(lines)
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"输入 {len(profiles)} 个画像和 {len(evidence)} 条证据",
            output_summary=f"生成 Markdown 报告，约 {len(report)} 个字符。",
            artifacts={"report_chars": len(report)},
        )
        return report, trace


class QAAgent:
    name = "质检/溯源 Agent"

    def run(self, profiles: List[CompetitorProfile], evidence: List[Evidence], report: str) -> Tuple[Dict[str, object], AgentTrace]:
        evidence_ids = {item.id for item in evidence}
        issues = []

        for profile in profiles:
            if not profile.evidence_ids:
                issues.append(f"{profile.name} 缺少证据引用。")
            missing_refs = [item for item in profile.evidence_ids if item not in evidence_ids]
            if missing_refs:
                issues.append(f"{profile.name} 引用了不存在的证据：{', '.join(missing_refs)}。")
            low_confidence = [
                item for item in evidence
                if item.competitor == profile.name and item.confidence < 0.5
            ]
            if low_confidence:
                issues.append(f"{profile.name} 存在低置信度或待补充来源。")

        insight_lines = []
        in_insights = False
        for line in report.splitlines():
            if line == "## 横向洞察":
                in_insights = True
                continue
            if in_insights and line == "## 证据索引":
                break
            if in_insights and line.startswith("-"):
                insight_lines.append(line)
        duplicate_lines = [
            line for line, count in Counter(insight_lines).items()
            if count > 1
        ]
        if duplicate_lines:
            issues.append("报告中存在重复要点，建议人工复核。")

        quality = {
            "status": "pass" if not issues else "needs_review",
            "issues": issues,
            "traceability_score": round(traceability_score(profiles, evidence), 2),
            "evidence_count": len(evidence),
            "source_types": sorted({item.source_type for item in evidence}),
        }
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"检查 {len(profiles)} 个画像、{len(evidence)} 条证据和报告文本",
            output_summary=f"质检状态：{quality['status']}；发现 {len(issues)} 个问题。",
            artifacts=quality,
        )
        return quality, trace


def slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def infer_company(name: str) -> str:
    company_map = {
        "Notion AI": "Notion",
        "Mem": "Mem Labs",
        "Reflect": "Reflect Notes",
        "Evernote AI": "Evernote",
    }
    return company_map.get(name, name)


def infer_positioning(industry: str, text: str) -> str:
    category = industry if industry.endswith(("产品", "工具", "平台", "系统", "服务")) else f"{industry}产品"
    if "workspace" in text or "wiki" in text:
        return f"面向团队知识库和协作文档的 {category}"
    if "networked" in text or "backlinks" in text:
        return f"面向个人知识网络和深度思考的 {category}"
    if "capture" in text or "search" in text:
        return f"强调快速捕获与智能检索的 {category}"
    return f"面向通用知识管理场景的 {category}"


def infer_target_users(text: str) -> List[str]:
    users = []
    if "team" in text or "workspace" in text:
        users.append("产品/运营/研发团队")
    if "personal" in text or "individual" in text:
        users.append("个人知识工作者")
    if "meeting" in text or "project" in text:
        users.append("项目协作者")
    if not users:
        users.append("知识管理用户")
    return users


def infer_features(text: str) -> List[str]:
    candidates = [
        ("search", "智能搜索"),
        ("summary", "内容总结"),
        ("summarize", "内容总结"),
        ("generate", "AI 生成"),
        ("autofill", "自动填充"),
        ("write", "AI 写作"),
        ("docs", "文档协作"),
        ("meeting", "会议记录"),
        ("backlinks", "双向链接"),
        ("wiki", "知识库"),
        ("capture", "快速捕获"),
        ("task", "任务管理"),
    ]
    features = [label for keyword, label in candidates if keyword in text]
    return features or ["笔记管理", "知识整理", "信息检索"]


def infer_pricing(text: str) -> str:
    if "free" in text and "paid" in text:
        return "免费层 + 付费高级功能"
    if "free" in text and ("plans" in text or "pricing" in text):
        return "免费层 + 多档订阅套餐"
    if "per seat" in text or "per user" in text:
        return "按席位订阅"
    if "subscription" in text:
        return "订阅制"
    if "pricing" in text or "plans" in text:
        return "公开定价页，可按计划/套餐订阅"
    return "公开信息不足，需要补充定价页"


def infer_differentiators(text: str) -> List[str]:
    points = []
    if "workspace" in text:
        points.append("与团队工作流结合紧密")
    if "networked" in text or "backlinks" in text:
        points.append("知识网络结构更突出")
    if "search" in text:
        points.append("检索和召回体验突出")
    if "legacy" in text:
        points.append("存量用户和多端同步基础较强")
    return points or ["定位清晰但差异化证据仍需补充"]


def infer_risks(items: Iterable[Evidence], text: str) -> List[str]:
    risks = []
    if any(item.source_type == "missing" for item in items):
        risks.append("公开来源不足，结论置信度较低")
    if "privacy" in text:
        risks.append("需要处理隐私和数据安全顾虑")
    if "crowded" in text:
        risks.append("赛道竞争密集，同质化风险较高")
    if not risks:
        risks.append("需要持续验证用户留存和付费转化")
    return risks


def common_patterns(profiles: List[CompetitorProfile]) -> List[str]:
    feature_counter = Counter(feature for profile in profiles for feature in profile.core_features)
    common = [feature for feature, count in feature_counter.items() if count >= 2]
    if common:
        return [f"多数产品都在强化{', '.join(common[:3])}。"]
    return ["AI 能力主要围绕写作、总结、搜索和知识组织展开。"]


def opportunity_points(profiles: List[CompetitorProfile]) -> List[str]:
    return [
        "用可追溯证据链降低 AI 结论不可信的问题。",
        "将竞品分析流程产品化，而不只是生成一次性文本。",
        "为团队用户提供可复用的行业 Schema 和报告模板。",
    ]


def shared_risks(profiles: List[CompetitorProfile]) -> List[str]:
    risk_counter = Counter(risk for profile in profiles for risk in profile.risks)
    return [risk for risk, _ in risk_counter.most_common(3)]


def traceability_score(profiles: List[CompetitorProfile], evidence: List[Evidence]) -> float:
    if not profiles:
        return 0.0
    evidence_ids = {item.id for item in evidence if item.source_type != "missing"}
    covered = sum(1 for profile in profiles if any(item in evidence_ids for item in profile.evidence_ids))
    return covered / len(profiles)
