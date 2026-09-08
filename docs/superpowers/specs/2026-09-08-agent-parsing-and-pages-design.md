# IDP-interaction-ai 文献 Agent 解析 + GitHub Pages 网站 — 设计文档

- 日期：2026-09-08
- 状态：待评审
- 课题：无序蛋白/相分离 × 蛋白互作 × AI 方法（idp-interaction-ai）

## 1. 目标

在现有「每周抓取元数据 → 提交仓库 → 建 Issue」流水线之上，新增两块能力：

1. **Agent 解析**：人工检阅之前，由 LLM 逐篇阅读全文（拿不到就降级摘要），产出两份有据可依的深度解析——`nature-paper-card`（16 节 Paper Card）与 `nature-reviewer`（审稿人视角评审），并附「评分 + 一句话」供降噪/排名。
2. **GitHub Pages 网站**：把「本周推荐 + 历史归档 + 逐篇解析」做成漂亮的可浏览静态站，整个仓库即长期存档。

## 2. 现状与关键结论

- 现有 `monitor.py` 每周抓 5 平台（pubmed/arxiv/biorxiv/medrxiv/chemrxiv）元数据，写 `Discovery/*.csv` + `_ids.txt` 与 `Archive/<src>/.../<id>.json`，并生成 Issue。
- **参考仓库（LLM_Pages_refers 下 4 个）没有一个真正取全文**——它们全部只喂 title+abstract 给 LLM。全文解析是本仓库相对它们的真正增量。
- 全文能力现状：`pyPaperFlow` 已含 PubMed `fetch_pmc_full_text`（PMC XML → 文本）；预印本 fetcher 只下 PDF 字节、不含文本。故全文层需**增量补两处轻量获取**（见 §4）。

## 3. 总体数据流

```
monitor.py 抓元数据
  → (新) full-text 补全文       # 增量改 pyPaperFlow，仓库侧调用
  → (新) 顶部评分（轻量）        # 每篇 1 次调用：score + 一句话
  → (新) paper-card 解析（全文）
  → (新) reviewer 评审（全文，单一审稿人）
  → 写 Archive/<src>/.../<id>/ 下 paper-card.md / review.md / analysis.json / fulltext.md
  → (新) build_site.py 生成静态站 site/
  → Issue（朴素：标题|作者|日期|评分|一句话|链接）
  → deploy_pages.yml 部署
```

## 4. 全文获取层（增量改 pyPaperFlow 源码）

不改动现有 search / PDF 下载行为，只**新增**取全文方法（均「有全文拿全文、拿不到回退摘要」）：

| 源 | 新增点 | 取法 |
|---|---|---|
| pubmed | 复用已有 `PubmedFetcher.fetch_pmc_full_text` | PMID→PMCID→PMC XML→文本（无 PMCID 回退摘要） |
| arxiv | `ArxivFetcher` 增 `fetch_full_text()` | GET `https://ar5iv.labs.arxiv.org/html/{id}` → 正文，404 回退摘要 |
| biorxiv / medrxiv | `BioRxivFetcher` 增 `fetch_full_text()`；`europepmc_fetcher.py` 增 fullTextXML 方法 | Europe PMC：DOI→PMCID→`fullTextXML`→段落，失败回退摘要 |
| chemrxiv | 不新增（仅 PDF） | 恒走摘要 |

- 产出：每篇写 `fulltext.md`（带 section 标题），并记录 `has_fulltext` 与 `fulltext_source`。
- **前置依赖**：本仓库 CI 需从修改后的 pyPaperFlow 安装（`pip install git+https://github.com/MaybeBio/pyPaperFlow.git@<tag>`，或本地 `pip install -e /data2/pyPaperFlow`）。pyPaperFlow 的增量改动须先提交/发布，本仓库 CI 才能消费。

## 5. Agent 解析层

统一走 OpenAI 兼容协议（`openai` SDK），`base_url + api_key + model` 全从 env 读（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL=deepseek-chat`）。单篇独立调用，256k 上下文整篇塞得下，仅在极端超长时切分。

每篇共 **3 次调用**：

1. **顶部评分（轻量，喂 title+abstract）** → 产出 2 字段：
   ```json
   { "score": 0, "one_liner_zh": "..." }
   ```
   `score` ∈ 0–10，衡量与课题（无序蛋白/相分离 × 互作 × AI 方法）的相关性，供 Issue 排名与后续 skip。

2. **paper-card（喂全文）** → 忠实 `nature-paper-card`，固定 16 节、不增第 17/18 节：
   01 基本信息 · 02 一句话总结 · 03 研究问题 · 04 背景与发展脉络 · 05 核心痛点(表) · 06 核心思想(表面方法/核心洞察/`[Analysis]` 泛化教训) · 07 方法总览 · 08 核心模块拆解(表) · 09 关键公式符号 · 10 实验设计与证据链(表) · 11 结论正确解读 · 12 作者自认局限(表) · 13 批判性分析(表) · 14 学到什么 · 15 与已有知识连接 · 16 研究想法。
   - 来源约束：区分「作者主张」与 `[Analysis]` 我方分析；证据指针回指原文 section/图/表；拿不到写 `Not assessable / Not applicable`；不编造。

3. **reviewer（喂全文，单一审稿人）** → 忠实 `nature-reviewer` 的**单审稿人**结构（无 3 人，故无跨审稿人综合）：
   - `Review setup`（Input scope / Assessment boundary / Shared manuscript claim summary / Visible evidence base / Missing materials）
   - `Reviewer 1`：Overall assessment · Who would be interested, and why · Major strengths · Major Concerns（每条 `RX-Mn`：Severity·Blocking·Axis·Claim pointer·Evidence pointer·Concern·Why it matters·Resolution test）· Minor Comments（`RX-mn`）· Technical failings that need to be addressed before the case is established · Assessment against Nature-style criteria（originality·scientific importance·interdisciplinary readership·technical soundness·readability）· Recommendation posture
   - `Risk / unsupported claims`

**调用的健壮性**（照搬 daily-paper-reader 的成熟件）：严格 JSON-schema 校验 + 降级；截断自动修复；失败重试（指数退避）；不发明内容。

**自动化适配**（CI 无 Read 工具）：证据指针从「行号」降级为「section/图/表名」；中文为主、技术词保留英文。

## 6. 存储层

每篇目录 `Archive/<src>/<year>/<month>/<id>/`：

```
<id>.json        # 元数据（已有，不变）
fulltext.md      # 全文；无全文则为摘要
paper-card.md    # 顶部评分 + nature-paper-card 16 节
review.md        # nature-reviewer 单审稿人评审
analysis.json    # {score, one_liner_zh, has_fulltext, fulltext_source, paper_card_path, review_path, url, source_url}
```

另生成聚合索引 `site/data/index.json`（本周 + 全历史），供网站与前端搜索。

## 7. 网站层

Python + Jinja2 纯静态（无 Node），`build_site.py` + `templates/`：

- `site/index.html` — 本周推荐（按 score 排序的卡片：标题 + score + 一句话 + 链接到逐篇页）
- `site/archive.html` — 历史归档（按周聚合，点进每周再点进每篇）
- `site/papers/<id>/index.html` — 逐篇解析页（Paper Card 与 Review 两区块）
- `site/data/index.json` — 供前端过滤/搜索
- `site/assets/style.css` — 主题
- 部署：官方 `configure-pages@v5 → upload-pages-artifact@v3 → deploy-pages@v4`

## 8. Issue 层

在现有表模板上扩展列，标题仍链**原文网站**，末尾**单独加一列「链接」**链到我们的网站解析页：

```
| 标题 | 作者 | 日期 | 评分 | 一句话 | 链接 |
```

## 9. GitHub Actions 编排

- **monitor.yml（扩展）**：现有抓取 → full-text → 顶部评分 → paper-card → reviewer → 写 artifacts → build_site → commit+push → open Issue。新增 secrets/env：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- **deploy_pages.yml（新增）**：`workflow_run` 于 monitor 成功后触发，走官方 Pages 三件套。

## 10. 配置与密钥

- 现有：`ENTREZ_EMAIL`、`NCBI_API_KEY`（Repo Secrets）。
- 新增：`LLM_API_KEY`（Secret）、`LLM_BASE_URL`（Secret，校内代理地址）、`LLM_MODEL`（Variable，如 `deepseek-chat`）。
- `config.yaml` 增 `llm:` 块：`model`、`base_url`（默认读 env）、`enable_card`、`enable_reviewer`（默认 true）。

## 11. 成本/时长杠杆（未来开关）

保留为 `config.yaml` 开关，先按「每篇满配」跑一周，按实测再调：

- `score_gate`：仅对 top-K 跑满 card+review，其余只给 score+一句话。
- reviewer 数量可配置（默认 1，本就偏轻）。

## 12. 非目标（YAGNI）

- 不迁移 MinerU / PDF 重解析（chemrxiv 走摘要）。
- 不搬 skill 的 `prepare_paper.py` / `audit_paper_card.py`（依赖 Read 工具与 PDF 页面定位，CI 不可用；其规则已转成 prompt）。
- 不做英文版输出、不做双语对照、不做订阅/推送通知。
- 不在仓库里写死任何 API key。

## 13. 验收标准

1. 每周 CI 全流程通过：抓取 → 全文(或摘要) → 顶部评分 → card + reviewer → 静态站生成 → 提交 → Issue。
2. Issue 表含 6 列，标题链原文、末尾「链接」链网站解析页。
3. 网站含本周、按周归档、逐篇解析（card + review 两区块），可纯静态访问。
4. 每篇 `Archive/<src>/.../<id>/` 下有 `fulltext.md`、`paper-card.md`、`review.md`、`analysis.json`。
5. 无全文时正确回退摘要并标注 `has_fulltext=false`，不因单篇失败中断整周流程。