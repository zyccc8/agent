import unittest

from competitor_agents.pipeline import DEFAULT_COMPETITORS, DEFAULT_INDUSTRY, run_pipeline


class PipelineTest(unittest.TestCase):
    def test_demo_pipeline_generates_traceable_report(self):
        result = run_pipeline(DEFAULT_INDUSTRY, DEFAULT_COMPETITORS[:3])

        self.assertEqual(result["industry"], DEFAULT_INDUSTRY)
        self.assertEqual(len(result["profiles"]), 3)
        self.assertGreaterEqual(len(result["evidence"]), 6)
        self.assertIn("# AI 笔记工具竞品分析报告", result["report"])
        self.assertEqual(len(result["traces"]), 5)
        self.assertGreaterEqual(result["quality"]["traceability_score"], 0.9)

    def test_missing_competitor_degrades_with_quality_issue(self):
        result = run_pipeline(DEFAULT_INDUSTRY, ["Unknown Notes"])

        self.assertEqual(result["profiles"][0]["name"], "Unknown Notes")
        self.assertEqual(result["evidence"][0]["source_type"], "missing")
        self.assertEqual(result["quality"]["status"], "needs_review")
        self.assertTrue(result["quality"]["issues"])

    def test_footwear_fallback_does_not_use_knowledge_management_copy(self):
        result = run_pipeline(
            "运动鞋",
            ["萨洛蒙XT-QUEST", "new balance 1906a", "nike vomero5", "Adidas samba"],
            use_llm=True,
        )
        joined = "\n".join(
            [
                profile["positioning"]
                + " "
                + " ".join(profile["target_users"])
                + " "
                + " ".join(profile["core_features"])
                for profile in result["profiles"]
            ]
        )

        self.assertIn("户外", joined)
        self.assertIn("缓震", joined)
        self.assertIn("复古", joined)
        self.assertNotIn("知识管理", joined)
        self.assertNotIn("笔记管理", joined)


if __name__ == "__main__":
    unittest.main()
