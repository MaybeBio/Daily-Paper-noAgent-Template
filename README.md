<p align="center">
  <img src="assets/banner.svg" width="100%" alt="BioLit Monitor —— 生物医学 × 计算 文献自动推送模板">
</p>

<h1 align="center">BioLit Monitor</h1>

<p align="center">
  <strong>生物医学 × 计算交叉领域的文献自动推送模板</strong><br/>
  用 GitHub Actions 按周期自动追踪 <b>PubMed · arXiv · bioRxiv · medRxiv · chemRxiv</b> 上的最新文献，双份落盘并生成 Issue 周报，配合 Zotero 与 AI 工具完成筛选与精读。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/pyPaperFlow-powered-7C3AED?style=for-the-badge" alt="pyPaperFlow powered">
  <img src="https://img.shields.io/badge/platforms-PubMed%C2%B7arXiv%C2%B7bioRxiv%C2%B7medRxiv%C2%B7chemRxiv-0EA5E9?style=for-the-badge" alt="Supported platforms">
  <img src="https://img.shields.io/badge/schedule-weekly%C2%B7GitHub%20Actions-0D9488?style=for-the-badge" alt="Weekly via GitHub Actions">
  <img src="https://img.shields.io/badge/output-Archive%20JSON%20%2B%20Discovery%20CSV-4F46E5?style=for-the-badge" alt="Outputs">
  <img src="https://img.shields.io/badge/reading-Zotero%20ready-0D9488?style=for-the-badge" alt="Zotero reading">
</p>

<p align="center">
  <a href="#-三步上手">三步上手</a> ·
  <a href="#-设计思路">设计思路</a> ·
  <a href="#-抓取与产出">抓取与产出</a> ·
  <a href="#-平台检索要点">平台检索要点</a> ·
  <a href="#-密钥与仓库配置">密钥与仓库配置</a> ·
  <a href="#-本地运行与调试">本地运行与调试</a> ·
  <a href="#-每周阅读工作流">每周阅读工作流</a>
</p>

> **模板即实例。** 仓库内的 `config.yaml` 已内置一套完整可跑的示例检索式 —— 拿到后你只需改**两处**：`config.yaml`（换成你的研究领域）与 `.github/workflows/monitor.yml`（推送周期）。工具与平台默认面向 **生物医学 × 计算**交叉课题。核心驱动为我们自研的文献检索获取工具 [pyPaperFlow](https://github.com/MaybeBio/pyPaperFlow)。

---

## 🚀 三步上手

| 步骤 | 你要做的 | 具体内容 |
|---|---|---|
| **1 · 换领域** | 编辑 [`config.yaml`](./config.yaml) | 改 `topic` 短名、`window_days` 窗口、各平台 `query` 检索式（示例已按「对象 × 方法」两段式写好，可对照改写） |
| **2 · 设定时与密钥** | 配置 [`workflow`](./.github/workflows/monitor.yml) | 确认 `monitor.yml` 的 cron；在 **Settings → Secrets and variables → Actions → Repository secrets** 添加 `ENTREZ_EMAIL`（必填）与 `NCBI_API_KEY`（可选） |
| **3 · 每周收报** | 等待或手动触发actions | 有新文献时自动开一条 **Issue 周报**，按平台列出标题 / 作者 / 日期 /(摘要太长暂时不在issue落地)，仓库里点开即读 |

> 推送到 `main` 后可用仓库 **Actions** 页的 `workflow_dispatch` 手动跑一次试运行；想先本地验证见「本地运行与调试」。

---

## 💡 设计思路

一句话：

> **每周自动「替你搜一遍研究领域」→ 新文献永久存档、另出一张可筛选清单 → 开一张 Issue 提醒你去看。** 精读、去重、是否入库等判断都留在本地完成。

设计取舍：

- **元数据分发，不碰全文** —— 只抓题录 / 作者 / 摘要 / DOI，轻量合规；要全文时按需走你自己的文献工具，或者继续使用我们自研的pyPaperflow文献工具。
- **双份落盘，职责分离** —— 只增的 `Archive/` 当文献库底账；按周的 `Discovery/` 快照当筛选清单。
- **Issue 即提醒** —— 不额外接邮件推送，有命中才开、零命中不打扰。
- **密钥不入库** —— PubMed 凭据一律走环境变量 / Actions Secret。
- **一个课题一个仓** —— 同一骨架可复制成多个独立仓库，并行追踪多个方向。

---

## 🧬 抓取与产出

**抓什么：** 每周期一次，逐平台用 pyPaperFlow 检索「窗口内新文献」；窗口 = 运行日往前 `window_days` 个自然日（不含当天）。

**落两份：**

| 产物 | 内容 | 归档路径 | 口径 |
|---|---|---|---|
| `Archive/` | 逐篇**完整**元数据 JSON | `Archive/<source>/<year>/<month>/<id>/<id>.json` | 只增不删，按月归档 |
| `Discovery/` | 合并 CSV + `_ids.txt` | `Discovery/<year>/<month>/<topic>_<date>.csv` | 按抓取日归档 |

**CSV 固定 9 列**（`utf-8-sig`，Excel 友好）：

```
source, id, doi, title, authors, journal, published_date, url, abstract
```

`id` 为平台主键（PubMed = PMID，预印本 = DOI）。**`_ids.txt`** 每行一个标识符，供 Zotero「按标识符添加」批量导入：`pmid:xxx` / `arXiv:xxx`（自动去版本号）/ 其余预印本裸 DOI。

**日期口径（entrez date）：** PubMed 的 DP 常残缺且存在标引时滞，故搜索、归档、Issue 三处统一用 `[edat]`（被 PubMed 收录的日期）；真实 DP 仍保存在各 JSON 的 `data.source.pub_date`。预印本用 posting 日期。**不做跨平台去重、不判重**，当周某平台 0 命中时 CSV 仅含表头。

<details>
<summary><b>🗂️ 仓库结构</b></summary>

```
.
├── monitor.py                       # 独立脚本：读 config → 逐平台检索 → 落盘 → 生成 Issue 正文
├── config.yaml                      # 检索配置：topic / window_days / 每平台一条 query
├── assets/banner.svg                # README 头图
├── requirements.txt                 # 依赖：pyPaperFlow
└── .github/workflows/monitor.yml    # 定时任务 + 手动触发；跑完 commit+push 并开 Issue
```

</details>

---

## 🧩 平台检索要点

各平台检索语法差异很大，详细的召回与噪声踩坑结论都写在各 query 正上方的注释里，改写时请务必保持：

- **PubMed** —— `(对象) AND (方法)` 括号两段式；Mesh 受标引时滞影响，周窗召回主要靠 `[tiab]` 精确词；`[edat]` 时间窗由代码自动拼接。
- **arXiv** —— 布尔项须写成 `all:"phrase"` / `all:word`，裸词会被强 AND、OR 失效；建议设 `max_results` 上限，否则会翻整周全部命中导致限速挂起。
- **bioRxiv / medRxiv** —— 同一检索器（Europe PMC + Crossref 超集）。**必须保留括号两段式，不可拍平成无括号 DNF**——Europe PMC（Lucene）会把无括号 AND/OR 混排错乱。
- **chemRxiv** —— 仅 Crossref 收录（Europe PMC 不覆盖），是唯一无严格索引的平台，接受一定噪声，交给 Zotero 兜底。

---

## 🔑 密钥与仓库配置

PubMed 需要邮箱（必填）与 NCBI API key（可选），一律走环境变量，**不写入仓库**：

- 本地：`export ENTREZ_EMAIL=you@example.com`，可选 `export NCBI_API_KEY=...`
- GitHub Actions：**Settings → Secrets and variables → Actions → Repository secrets** 新建 `ENTREZ_EMAIL` 与 `NCBI_API_KEY`，workflow 以 `${{ secrets.* }}` 注入运行环境。

推送周期在 `monitor.yml` 的 `schedule.cron`（默认**周一 09:23 UTC**，避开整点，我们这里推荐cron-job外部定时触发）；workflow 权限为 `contents: write` + `issues: write`：跑完 commit+push 产物，再按是否命中决定开 Issue。

---

## 🖥️ 本地运行与调试

```bash
pip install pyPaperFlow            # 或 pip install -r requirements.txt
export ENTREZ_EMAIL=you@example.com

python monitor.py \
  --config config.yaml \           # 指定检索配置
  --out-dir . \                    # Archive/ 与 Discovery/ 落在仓库根
  --issue-body /tmp/issue.md \     # （可选）生成的 Issue 正文
  --issue-title /tmp/issue.title   # （可选）生成的 Issue 标题
```

| 常用参数 | 作用 |
|---|---|
| `--window-days 1` | 把窗口收窄到 1 天快速试跑，无需改 config |
| `--run-date 2026-09-03` | 固定运行日，便于回测某周 |

窗口默认不含运行当天；单平台失败仅告警，全部失败才非零退出。

---

## 📚 每周阅读工作流

1. 打开仓库 **Issues** 看当周推送报告，按平台粗筛、点标题直达原文；
2. 感兴趣的先入库：用 Zotero 按本次 `Discovery/` 下 `_ids.txt`「按标识符添加」批量导入，去重与精筛在这一层完成；
3. 需要全文或深挖时，用文献工具按 DOI / PMID 二次获取，再走你自己的精读、检索与分析流程 —— 下游工具（Zotero、agent、skill 等）自由接入。

---

<details>
<summary><b>❓ 常见问题</b></summary>

- **为什么按周而不是每日？** 默认 `window_days: 7` + cron 每周一运行；想改频次，改 config 与 cron 两处即可。
- **抓不全 / 有噪声怎么办？** 平台 query 的召回与噪声实测都记录在各 query 上方的注释里，按注释微调；残余噪声由 Zotero 层也就是人工筛掉。
- **能抓全文吗？** 本模板只做**元数据分发**，不抓全文；全文按需走你已有的文献工具获取，或继续使用我们的文献工具pyPaperflow。

</details>

---

> 这是一个刻意保持通用的**模板仓库**：属于你的只有 `config.yaml` 与定时配置，脚本与工作流逻辑基本不必动。把它复制成「一个课题topic = 一个独立仓库」，即可同时追踪多个研究方向。


