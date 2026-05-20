from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .llm_client import CustomLLMClient, LLMError
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

    def __init__(self, llm_client: CustomLLMClient | None = None) -> None:
        self.llm_client = llm_client or CustomLLMClient()

    def run(
        self,
        industry: str,
        competitors: List[str],
        evidence: List[Evidence],
        use_llm: bool = False,
    ) -> Tuple[List[CompetitorProfile], Dict[str, List[str]], AgentTrace]:
        if use_llm and self.llm_client.available:
            try:
                return self._run_with_llm(industry, competitors, evidence)
            except LLMError as exc:
                profiles, comparison = self._run_with_rules(industry, competitors, evidence)
                trace = AgentTrace(
                    agent=self.name,
                    status="completed",
                    input_summary=f"输入 {len(evidence)} 条清洗证据；大模型增强失败后降级",
                    output_summary=f"LLM 调用失败，已使用规则兜底生成 {len(profiles)} 个竞品画像。",
                    artifacts={
                        "profile_count": len(profiles),
                        "comparison": comparison,
                        "llm_enabled": True,
                        "llm_used": False,
                        "llm_error": str(exc),
                    },
                )
                return profiles, comparison, trace

        profiles, comparison = self._run_with_rules(industry, competitors, evidence)
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"输入 {len(evidence)} 条清洗证据；模式：规则分析",
            output_summary=f"生成 {len(profiles)} 个竞品画像和 {sum(len(v) for v in comparison.values())} 条比较洞察。",
            artifacts={
                "profile_count": len(profiles),
                "comparison": comparison,
                "llm_enabled": use_llm,
                "llm_used": False,
                "llm_error": "" if not use_llm else "LLM_API_URL 未配置",
            },
        )
        return profiles, comparison, trace

    def _run_with_rules(
        self,
        industry: str,
        competitors: List[str],
        evidence: List[Evidence],
    ) -> Tuple[List[CompetitorProfile], Dict[str, List[str]]]:
        grouped: Dict[str, List[Evidence]] = defaultdict(list)
        for item in evidence:
            grouped[item.competitor].append(item)

        profiles: List[CompetitorProfile] = []
        for competitor in competitors:
            items = grouped.get(competitor, [])
            text = f"{competitor} " + " ".join(item.excerpt for item in items).lower()
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
            "common_patterns": common_patterns(profiles, industry),
            "opportunities": opportunity_points(profiles, industry),
            "risks": shared_risks(profiles),
        }
        return profiles, comparison

    def _run_with_llm(
        self,
        industry: str,
        competitors: List[str],
        evidence: List[Evidence],
    ) -> Tuple[List[CompetitorProfile], Dict[str, List[str]], AgentTrace]:
        payload = {
            "industry": industry,
            "competitors": competitors,
            "evidence": [
                {
                    "id": item.id,
                    "competitor": item.competitor,
                    "source_type": item.source_type,
                    "title": item.title,
                    "url": item.url,
                    "excerpt": item.excerpt,
                    "confidence": item.confidence,
                }
                for item in evidence
            ],
        }
        instructions = (
            "你是资深产品战略分析师。你要基于用户给出的行业、竞品名称和证据，"
            "生成可追溯的竞品分析结构化 JSON。不要把所有产品硬套成同一类；"
            "如果竞品名称显示是硬件、SaaS、App 或模型产品，要结合真实品类判断。"
            "不要编造不存在的证据 ID。输出必须是 JSON object，不要 Markdown。"
        )
        prompt = (
            "请返回如下 JSON 结构：\n"
            "{\n"
            "  \"profiles\": [\n"
            "    {\"name\":\"\", \"company\":\"\", \"positioning\":\"\", \"target_users\":[\"\"], "
            "\"core_features\":[\"\"], \"pricing\":\"\", \"differentiators\":[\"\"], "
            "\"risks\":[\"\"], \"evidence_ids\":[\"\"]}\n"
            "  ],\n"
            "  \"comparison\": {\"common_patterns\":[\"\"], \"opportunities\":[\"\"], \"risks\":[\"\"]}\n"
            "}\n\n"
            "要求：\n"
            "1. profiles 必须覆盖所有 competitors。\n"
            "2. 每个画像最多 4 个核心功能、3 个差异化、3 个风险。\n"
            "3. positioning 要具体，不能写成泛泛的知识管理工具，除非证据确实如此。\n"
            "4. 对证据不足的内容要写“公开信息不足/需要补充来源”，不要装作确定。\n"
            "5. evidence_ids 只能使用输入 evidence 中对应竞品的 id。\n\n"
            f"输入数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        result = self.llm_client.complete_json(instructions, prompt)
        profiles = profiles_from_llm_result(result, competitors, evidence, industry)
        comparison = comparison_from_llm_result(result, profiles)
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"输入 {len(evidence)} 条清洗证据；模式：大模型增强",
            output_summary=f"LLM 生成 {len(profiles)} 个竞品画像和 {sum(len(v) for v in comparison.values())} 条比较洞察。",
            artifacts={
                "profile_count": len(profiles),
                "comparison": comparison,
                "llm_enabled": True,
                "llm_used": True,
                "model": self.llm_client.model,
            },
        )
        return profiles, comparison, trace


class ReportAgent:
    name = "报告撰写 Agent"

    def __init__(self, llm_client: CustomLLMClient | None = None) -> None:
        self.llm_client = llm_client or CustomLLMClient()

    def run(
        self,
        industry: str,
        profiles: List[CompetitorProfile],
        comparison: Dict[str, List[str]],
        evidence: List[Evidence],
        use_llm: bool = False,
    ) -> Tuple[str, AgentTrace]:
        if use_llm and self.llm_client.available:
            try:
                return self._run_with_llm(industry, profiles, comparison, evidence)
            except LLMError as exc:
                report = self._render_rule_report(industry, profiles, comparison, evidence)
                trace = AgentTrace(
                    agent=self.name,
                    status="completed",
                    input_summary=f"输入 {len(profiles)} 个画像和 {len(evidence)} 条证据；大模型增强失败后降级",
                    output_summary=f"LLM 报告生成失败，已使用模板报告，约 {len(report)} 个字符。",
                    artifacts={"report_chars": len(report), "llm_enabled": True, "llm_used": False, "llm_error": str(exc)},
                )
                return report, trace

        report = self._render_rule_report(industry, profiles, comparison, evidence)
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"输入 {len(profiles)} 个画像和 {len(evidence)} 条证据；模式：模板报告",
            output_summary=f"生成 Markdown 报告，约 {len(report)} 个字符。",
            artifacts={"report_chars": len(report), "llm_enabled": use_llm, "llm_used": False},
        )
        return report, trace

    def _render_rule_report(
        self,
        industry: str,
        profiles: List[CompetitorProfile],
        comparison: Dict[str, List[str]],
        evidence: List[Evidence],
    ) -> str:
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

        return "\n".join(lines)

    def _run_with_llm(
        self,
        industry: str,
        profiles: List[CompetitorProfile],
        comparison: Dict[str, List[str]],
        evidence: List[Evidence],
    ) -> Tuple[str, AgentTrace]:
        payload = {
            "industry": industry,
            "profiles": [profile.__dict__ for profile in profiles],
            "comparison": comparison,
            "evidence": [item.__dict__ for item in evidence],
        }
        instructions = (
            "你是资深咨询顾问，擅长写清晰、可信、可溯源的中文竞品分析报告。"
            "报告必须使用 Markdown，关键判断要引用证据 ID，例如 [live-apple-1]。"
            "不要输出空泛套话，不要把不同品类产品混为一谈。"
        )
        prompt = (
            "请基于以下结构化分析生成一份商业竞品分析报告。结构必须包括："
            "执行摘要、竞品逐项分析、横向对比、机会点、风险与待验证假设、证据索引。\n"
            "要求每个竞品至少有一个具体判断；证据不足时明确写出待补充来源。\n\n"
            f"输入数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        result = self.llm_client.complete_json(
            instructions + " 输出 JSON object，字段为 {\"report\":\"Markdown 文本\"}。",
            prompt,
        )
        report = str(result.get("report") or "").strip()
        if not report:
            raise LLMError("Model report JSON did not include report")
        trace = AgentTrace(
            agent=self.name,
            status="completed",
            input_summary=f"输入 {len(profiles)} 个画像和 {len(evidence)} 条证据；模式：大模型报告",
            output_summary=f"LLM 生成 Markdown 报告，约 {len(report)} 个字符。",
            artifacts={"report_chars": len(report), "llm_enabled": True, "llm_used": True, "model": self.llm_client.model},
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


def profiles_from_llm_result(
    result: Dict[str, object],
    competitors: List[str],
    evidence: List[Evidence],
    industry: str,
) -> List[CompetitorProfile]:
    raw_profiles = result.get("profiles")
    evidence_by_competitor = defaultdict(set)
    for item in evidence:
        evidence_by_competitor[item.competitor].add(item.id)
    raw_by_name = {}
    if isinstance(raw_profiles, list):
        for item in raw_profiles:
            if isinstance(item, dict) and item.get("name"):
                raw_by_name[str(item["name"]).lower()] = item

    profiles = []
    for competitor in competitors:
        item = raw_by_name.get(competitor.lower(), {})
        allowed_evidence = evidence_by_competitor.get(competitor, set())
        evidence_ids = [
            str(value)
            for value in as_list(item.get("evidence_ids"))
            if str(value) in allowed_evidence
        ]
        if not evidence_ids:
            evidence_ids = [ev.id for ev in evidence if ev.competitor == competitor]
        profiles.append(
            CompetitorProfile(
                name=str(item.get("name") or competitor),
                company=str(item.get("company") or infer_company(competitor)),
                positioning=str(item.get("positioning") or infer_positioning(industry, "")),
                target_users=non_empty_list(item.get("target_users"), ["目标用户待验证"]),
                core_features=non_empty_list(item.get("core_features"), ["核心功能待验证"]),
                pricing=str(item.get("pricing") or "公开信息不足，需要补充定价页"),
                differentiators=non_empty_list(item.get("differentiators"), ["差异化待验证"]),
                risks=non_empty_list(item.get("risks"), ["需要补充公开来源验证"]),
                evidence_ids=evidence_ids,
            )
        )
    return profiles


def comparison_from_llm_result(
    result: Dict[str, object],
    profiles: List[CompetitorProfile],
) -> Dict[str, List[str]]:
    raw = result.get("comparison")
    if isinstance(raw, dict):
        return {
            "common_patterns": non_empty_list(raw.get("common_patterns"), common_patterns(profiles, "")),
            "opportunities": non_empty_list(raw.get("opportunities"), opportunity_points(profiles, "")),
            "risks": non_empty_list(raw.get("risks"), shared_risks(profiles)),
        }
    return {
        "common_patterns": common_patterns(profiles, ""),
        "opportunities": opportunity_points(profiles, ""),
        "risks": shared_risks(profiles),
    }


def as_list(value: object) -> List[object]:
    return value if isinstance(value, list) else []


def non_empty_list(value: object, fallback: List[str]) -> List[str]:
    items = [str(item).strip() for item in as_list(value) if str(item).strip()]
    return items or fallback


def infer_positioning(industry: str, text: str) -> str:
    category = industry if industry.endswith(("产品", "工具", "平台", "系统", "服务")) else f"{industry}产品"
    if is_footwear_context(industry, text):
        if any(keyword in text for keyword in ["samba", "阿迪达斯", "adidas"]):
            return f"面向复古潮流、日常穿搭和轻运动场景的 {category}"
        if any(keyword in text for keyword in ["vomero", "nike", "耐克"]):
            return f"面向缓震跑步、通勤和舒适穿着场景的 {category}"
        if any(keyword in text for keyword in ["new balance", "1906", "nb"]):
            return f"面向复古跑鞋、潮流穿搭和日常通勤场景的 {category}"
        if any(keyword in text for keyword in ["xt-quest", "salomon", "萨洛蒙"]):
            return f"面向户外徒步、越野风格和机能穿搭场景的 {category}"
        return f"面向运动、通勤和日常穿搭场景的 {category}"
    if is_laptop_context(industry, text):
        if any(keyword in text for keyword in ["拯救者", "legion", "y7000", "游戏"]):
            return f"面向游戏玩家和高性能需求用户的 {category}"
        if any(keyword in text for keyword in ["macbook", "air", "轻薄"]):
            return f"面向移动办公、学习和创作场景的轻薄型 {category}"
        return f"面向办公、学习和生产力场景的 {category}"
    if "workspace" in text or "wiki" in text:
        return f"面向团队知识库和协作文档的 {category}"
    if "networked" in text or "backlinks" in text:
        return f"面向个人知识网络和深度思考的 {category}"
    if "capture" in text or "search" in text:
        return f"强调快速捕获与智能检索的 {category}"
    return f"面向通用知识管理场景的 {category}"


def infer_target_users(text: str) -> List[str]:
    users = []
    if is_footwear_context("", text):
        if any(keyword in text for keyword in ["salomon", "萨洛蒙", "xt-quest"]):
            return ["户外运动爱好者", "机能风穿搭用户", "轻徒步用户"]
        if any(keyword in text for keyword in ["vomero", "跑"]):
            return ["跑步用户", "重视脚感的通勤用户", "运动休闲用户"]
        if any(keyword in text for keyword in ["samba", "adidas", "阿迪达斯"]):
            return ["潮流穿搭用户", "复古球鞋用户", "日常通勤用户"]
        if any(keyword in text for keyword in ["new balance", "1906", "nb"]):
            return ["复古跑鞋用户", "潮流穿搭用户", "舒适通勤用户"]
        return ["运动休闲用户", "日常通勤用户", "潮流穿搭用户"]
    if any(keyword in text for keyword in ["macbook", "联想", "lenovo", "拯救者", "laptop", "notebook", "笔记本"]):
        if any(keyword in text for keyword in ["拯救者", "legion", "游戏"]):
            return ["游戏玩家", "工程/设计类学生", "高性能移动办公用户"]
        if "macbook" in text:
            return ["学生", "移动办公用户", "内容创作者"]
        return ["学生", "办公用户", "家庭用户"]
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
    if is_footwear_context("", text):
        features = []
        if any(keyword in text for keyword in ["salomon", "萨洛蒙", "xt-quest"]):
            features.extend(["户外抓地", "稳定支撑", "机能外观"])
        if any(keyword in text for keyword in ["vomero", "nike", "耐克"]):
            features.extend(["缓震脚感", "跑步支撑", "日常舒适"])
        if any(keyword in text for keyword in ["samba", "adidas", "阿迪达斯"]):
            features.extend(["复古低帮", "经典外观", "易于搭配"])
        if any(keyword in text for keyword in ["new balance", "1906", "nb"]):
            features.extend(["复古跑鞋设计", "舒适缓震", "通勤穿搭"])
        return features or ["穿着舒适", "运动支撑", "日常搭配"]
    if any(keyword in text for keyword in ["macbook", "联想", "lenovo", "拯救者", "laptop", "notebook", "笔记本"]):
        features = []
        if any(keyword in text for keyword in ["macbook", "air", "轻薄"]):
            features.extend(["轻薄便携", "长续航", "生态协同"])
        if any(keyword in text for keyword in ["拯救者", "legion", "y7000", "游戏"]):
            features.extend(["高性能处理器", "独立显卡", "高刷新率屏幕"])
        return features or ["移动办公", "学习娱乐", "多任务处理"]
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
    if is_footwear_context("", text):
        return "公开价格需以品牌官网、电商平台和发售渠道实时信息为准"
    if any(keyword in text for keyword in ["macbook", "联想", "lenovo", "拯救者", "laptop", "notebook", "笔记本"]):
        return "公开价格需以电商/官网实时信息为准"
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
    if is_footwear_context("", text):
        if any(keyword in text for keyword in ["salomon", "萨洛蒙", "xt-quest"]):
            return ["户外机能属性突出", "越野风格辨识度强"]
        if any(keyword in text for keyword in ["vomero", "nike", "耐克"]):
            return ["缓震舒适度更突出", "兼顾跑步与日常穿着"]
        if any(keyword in text for keyword in ["samba", "adidas", "阿迪达斯"]):
            return ["经典复古造型认知强", "穿搭场景覆盖广"]
        if any(keyword in text for keyword in ["new balance", "1906", "nb"]):
            return ["复古跑鞋风格成熟", "舒适通勤和潮流属性兼具"]
        return ["运动与日常穿搭兼容性较强"]
    if any(keyword in text for keyword in ["macbook", "联想", "lenovo", "拯救者", "laptop", "notebook", "笔记本"]):
        if "macbook" in text:
            return ["轻薄续航和系统生态优势明显", "适合长期移动办公和创作"]
        if any(keyword in text for keyword in ["拯救者", "legion", "y7000", "游戏"]):
            return ["性能释放和游戏场景更突出", "更适合需要独显的重负载任务"]
        return ["品牌渠道和售后覆盖较强"]
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
    if is_footwear_context("", text):
        risks.append("价格、配色、库存和发售渠道变化快，需要补充官网或电商实时来源")
        if any(keyword in text for keyword in ["samba", "adidas", "阿迪达斯"]):
            risks.append("热门款可能存在溢价、断码和同质化穿搭风险")
        return risks
    if any(keyword in text for keyword in ["macbook", "联想", "lenovo", "拯救者", "laptop", "notebook", "笔记本"]):
        risks.append("价格、配置和发布时间强依赖实时来源，需要补充官网或电商证据")
    if "privacy" in text:
        risks.append("需要处理隐私和数据安全顾虑")
    if "crowded" in text:
        risks.append("赛道竞争密集，同质化风险较高")
    if not risks:
        risks.append("需要持续验证用户留存和付费转化")
    return risks


def is_laptop_context(industry: str, text: str) -> bool:
    haystack = f"{industry} {text}".lower()
    return any(
        keyword in haystack
        for keyword in ["笔记本", "电脑", "macbook", "laptop", "notebook", "lenovo", "联想", "拯救者"]
    )


def is_footwear_context(industry: str, text: str) -> bool:
    haystack = f"{industry} {text}".lower()
    return any(
        keyword in haystack
        for keyword in [
            "运动鞋",
            "鞋",
            "球鞋",
            "跑鞋",
            "sneaker",
            "salomon",
            "萨洛蒙",
            "xt-quest",
            "new balance",
            "1906",
            "nike",
            "耐克",
            "vomero",
            "adidas",
            "阿迪达斯",
            "samba",
        ]
    )


def common_patterns(profiles: List[CompetitorProfile], industry: str = "") -> List[str]:
    combined = f"{industry} " + " ".join(
        " ".join(profile.core_features + profile.target_users + [profile.positioning])
        for profile in profiles
    )
    if is_footwear_context(industry, combined):
        return [
            "主要竞品都在运动功能与日常穿搭之间寻找平衡。",
            "舒适脚感、外观辨识度和渠道价格是用户比较时的关键因素。",
        ]
    if is_laptop_context(industry, combined):
        return [
            "主要竞品围绕性能、便携、续航和生态体验形成差异。",
            "配置、价格和发布节奏需要结合实时渠道信息判断。",
        ]
    feature_counter = Counter(feature for profile in profiles for feature in profile.core_features)
    common = [feature for feature, count in feature_counter.items() if count >= 2]
    if common:
        return [f"多数产品都在强化{', '.join(common[:3])}。"]
    return ["AI 能力主要围绕写作、总结、搜索和知识组织展开。"]


def opportunity_points(profiles: List[CompetitorProfile], industry: str = "") -> List[str]:
    combined = f"{industry} " + " ".join(profile.positioning for profile in profiles)
    if is_footwear_context(industry, combined):
        return [
            "补充官网、电商价格、库存和用户评价后，可进一步比较性价比与购买风险。",
            "按使用场景拆分跑步、通勤、潮流穿搭和户外机能，更容易形成清晰推荐。",
            "把配色、尺码、渠道溢价纳入分析，会比单纯功能对比更贴近购买决策。",
        ]
    if is_laptop_context(industry, combined):
        return [
            "补充实时配置、价格和评测数据后，可进一步比较性能释放与性价比。",
            "按学生、游戏、办公、创作等人群拆分，会让推荐结论更可执行。",
            "把售后、系统生态和扩展性纳入分析，可提升购买建议质量。",
        ]
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
