const industryInput = document.querySelector("#industryInput");
const competitorsInput = document.querySelector("#competitorsInput");
const liveSourcesInput = document.querySelector("#liveSourcesInput");
const llmInput = document.querySelector("#llmInput");
const analyzeButton = document.querySelector("#analyzeButton");
const demoButton = document.querySelector("#demoButton");
const statusText = document.querySelector("#statusText");
const dagEl = document.querySelector("#dag");
const profilesEl = document.querySelector("#profiles");
const reportEl = document.querySelector("#report");
const evidenceEl = document.querySelector("#evidence");
const tracesEl = document.querySelector("#traces");
const qualityBadge = document.querySelector("#qualityBadge");
const llmNotice = document.querySelector("#llmNotice");

async function analyze(useDemo = false) {
  statusText.textContent = "Agent 正在协作分析...";
  analyzeButton.disabled = true;
  demoButton.disabled = true;

  try {
    const response = useDemo
      ? await fetch("/api/demo")
      : await fetch("/api/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            industry: industryInput.value,
            competitors: competitorsInput.value
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            use_live_sources: liveSourcesInput.checked,
            use_llm: llmInput.checked,
          }),
        });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "分析失败");
    }
    renderResult(result);
    statusText.textContent = `完成：${result.run_id}`;
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    analyzeButton.disabled = false;
    demoButton.disabled = false;
  }
}

function renderResult(result) {
  dagEl.innerHTML = result.workflow_dag
    .map(
      (node) => `
        <div class="dag-node">
          <strong>${node.label}</strong>
          <span>${node.depends_on.length ? `依赖 ${node.depends_on.join(", ")}` : "起点"}</span>
        </div>
      `,
    )
    .join("");

  qualityBadge.textContent = result.quality.status === "pass" ? "质检通过" : "需要复核";
  qualityBadge.className = `badge ${result.quality.status}`;

  profilesEl.innerHTML = result.profiles
    .map(
      (profile) => `
        <article class="profile-card">
          <h3>${profile.name}</h3>
          <p><strong>定位：</strong>${profile.positioning}</p>
          <p><strong>用户：</strong>${profile.target_users.join("、")}</p>
          <p><strong>功能：</strong>${profile.core_features.join("、")}</p>
          <p><strong>风险：</strong>${profile.risks.join("、")}</p>
        </article>
      `,
    )
    .join("");

  renderLlmNotice(result);

  reportEl.textContent = result.report;

  evidenceEl.innerHTML = result.evidence
    .map((item) => {
      const source = item.url ? `<a href="${item.url}" target="_blank" rel="noreferrer">${item.title}</a>` : item.title;
      return `
        <article class="evidence-item">
          <p><strong>[${item.id}] ${item.competitor}</strong></p>
          <p>${source}</p>
          <p>${item.excerpt}</p>
          <p>类型：${item.source_type}｜置信度：${item.confidence.toFixed(2)}</p>
        </article>
      `;
    })
    .join("");

  tracesEl.innerHTML = result.traces
    .map(
      (trace) => `
        <article class="trace-item">
          <p><strong>${trace.agent}</strong>｜${trace.status}</p>
          <p>输入：${trace.input_summary}</p>
          <p>输出：${trace.output_summary}</p>
        </article>
      `,
    )
    .join("");
}

function renderLlmNotice(result) {
  const analysisTrace = result.traces.find((trace) => trace.agent === "分析 Agent");
  const reportTrace = result.traces.find((trace) => trace.agent === "报告撰写 Agent");
  const analysisArtifacts = analysisTrace?.artifacts || {};
  const reportArtifacts = reportTrace?.artifacts || {};
  const llmUsed = Boolean(analysisArtifacts.llm_used || reportArtifacts.llm_used);
  const llmEnabled = Boolean(analysisArtifacts.llm_enabled || reportArtifacts.llm_enabled || result.use_llm);
  const errors = [analysisArtifacts.llm_error, reportArtifacts.llm_error].filter(Boolean);

  if (llmUsed) {
    const model = analysisArtifacts.model || reportArtifacts.model || "已配置模型";
    llmNotice.className = "llm-notice ok";
    llmNotice.textContent = `大模型已生效：${model}`;
    return;
  }

  if (llmEnabled) {
    llmNotice.className = "llm-notice warn";
    llmNotice.textContent = `大模型未生效，当前使用规则兜底。原因：${errors.join("；") || "未配置 LLM_API_URL"}`;
    return;
  }

  llmNotice.className = "llm-notice";
  llmNotice.textContent = "当前使用规则分析，未启用大模型。";
}

analyzeButton.addEventListener("click", () => analyze(false));
demoButton.addEventListener("click", () => analyze(true));
analyze(true);
