# BioLit Monitor — 生物医学文献自动推送模板

> 用 GitHub Actions 定期追踪你研究领域在 **PubMed / arXiv / bioRxiv / medRxiv / chemRxiv** 上的最新文献：抓取**元数据** → 分平台落盘 → 每周生成一条 Issue 周报，配合 Zotero 与 AI 工具完成筛选、精读与二次检索。

本模板基于自研文献检索工具 [pyPaperFlow](https://github.com/MaybeBio/pyPaperFlow)，默认面向**生物医学 × 计算交叉**课题（如组学、互作、结构预测、分子模拟等方向）。抓取的只是题录元数据，不涉及全文版权。拿到即用，你只需要改**两处**：检索课题与推送周期。

## 一、工作流一览

**推送端（仓库自动完成，每周期执行一次）**

1. **读配置** `monitor.py` 解析 `config.yaml`：取 `topic`、`window_days` 与各平台检索式，计算回溯窗口（不含运行当天）。
2. **逐平台检索** 经 pyPaperFlow 分别查询 PubMed / arXiv / bioRxiv / medRxiv / chemRxiv；PubMed 依赖环境变量注入的邮箱与 API key。
3. **双份落盘** 归一化后的元数据写入 `Archive/`（逐篇完整 JSON，只增不删）；当次运行另出 `Discovery/` 合并 CSV 与 `_ids.txt`（按抓取日归档）。
4. **开周报 Issue** 当周有命中时自动创建 GitHub Issue，按平台分组列出标题 / 作者 / 日期。

一句话概括：**每周自动「搜一遍你的领域」→ 新文献永久存档、另出一张可筛选清单 → 开一张 Issue 提醒你去看**。精读、去重、是否入库等判断都留在本地完成。

## 二、核心特性

- **五平台一体**：同一套检索式语义覆盖 PubMed、arXiv、bioRxiv、medRxiv、chemRxiv，CSV 输出列结构完全统一。
- **元数据级抓取**：只抓题录、作者、摘要、DOI 等，轻量、合规、易筛；需要全文时再按需获取。
- **双份落盘，职责清晰**：
  - `Archive/` —— 逐篇**完整**元数据 JSON，只增不删，作为长期文献库底账；
  - `Discovery/` —— 每次运行的**合并快照**（CSV + Zotero 标识符清单），便于当周快速筛选。
- **Issue 周报**：有命中时自动开一条 Issue，按平台分组列出标题 / 作者 / 日期，直接在仓库里点开原文。
- **密钥不入库**：PubMed 邮箱与 NCBI API key 走环境变量 / Actions Secret。
- **模板即实例**：仓库自带的 `config.yaml` 已填好一套完整可跑的示例检索式，既是范本、也可直接当你的起点。

## 三、快速启用：只改两处

**① 检索课题 —— `config.yaml`**

| 字段 | 含义 |
|---|---|
| `topic` | 课题短名，出现在产出文件名与 Issue 标题（如 `protein-dna-ai`） |
| `window_days` | 每次向前回溯的抓取窗口（天），默认 `7`；本地试跑可改 `1` |
| `platforms.<name>.query` | 该平台的布尔检索式（每个平台一条，语法与踩坑见「六」） |

把 `query` 换成你研究领域的检索式即可；仓库内示例已按「**对象 × 方法**」的两段式写好，可直接对照改写。

**② 推送周期 —— `.github/workflows/monitor.yml`**

```yaml
on:
  schedule:
    - cron: "23 9 * * 1"   # 每周一 09:23 UTC；改这里即改周期
  workflow_dispatch: {}     # 保留，便于手动触发补跑
```

在仓库 **Actions** 页可随时手动运行；`--run-date` 参数支持回测指定日期。

> 进阶：每个课题开一个独立仓库复用这套骨架（`monitor.py` + workflow + 各自的 `config.yaml`），即可并行追踪多个方向。

## 四、仓库结构

```
.
├── monitor.py                       # 独立脚本：读 config → 逐平台检索 → 落盘 → 生成 Issue 正文
├── config.yaml                      # 检索配置：topic / window_days / 每平台一条 query
├── requirements.txt                 # 依赖：pyPaperFlow
└── .github/workflows/monitor.yml    # 定时任务 + 手动触发；跑完 commit+push 并开 Issue
```

## 五、产出物说明

### 目录与归档口径

| 产物 | 内容 | 归档路径 | 口径 |
|---|---|---|---|
| `Archive/` | 逐篇完整元数据 JSON | `Archive/<source>/<year>/<month>/<id>/<id>.json` | 只增不删，按月归档 |
| `Discovery/` | 合并 CSV + 标识符清单 | `Discovery/<year>/<month>/<topic>_<date>.csv`（+ `_ids.txt`） | 按抓取日归档 |

`source` 取值：`pubmed`、`arxiv`、`biorxiv`、`medrxiv`、`chemrxiv`。每次运行 `Discovery/` 覆盖当天文件，`Archive/` 只增不删。

### 文件格式

- **CSV 固定 9 列**（`utf-8-sig`，Excel 友好）：
  `source, id, doi, title, authors, journal, published_date, url, abstract`。`id` 为平台主键（PubMed 为 PMID，预印本为 DOI）。
- **`_ids.txt`** 每行一个标识符，供 Zotero「按标识符添加」批量导入：
  - PubMed：`pmid:xxx`
  - arXiv：`arXiv:xxx`（自动去掉 `vN` 版本号）
  - 其余预印本：裸 DOI

### 日期口径（entrez date）

PubMed 的「发表日期 DP」常残缺（ahead-of-print 无日期、只到月）且存在标引时滞，故搜索、归档、Issue **三处统一用 entrez date（`[edat]`，即被 PubMed 收录的日期）**：

- 搜索：用 `[edat]` 过滤窗口，抓「本周新进 PubMed 的文献」，每篇只出现一次，无需重叠窗口与去重；
- 归档：`Archive/pubmed/` 也按 entrez date 归档，不因 DP 残缺落进 `unknown/`；
- 真实发表日期并未丢弃，仍保留在各 `Archive/*.json` 的 `data.source.pub_date` 中。

预印本无标引时滞，直接使用 posting 日期。**不做跨平台去重、不判定是否已入库**——当周某平台 0 命中时 CSV 仅含表头；重复与筛选交给 Zotero。

## 六、各平台检索式要点

各平台检索语法差异较大，均已在 `config.yaml` 对应 query 的正上方以注释记录踩坑结论。改写 query 时请务必保持：

- **PubMed**：`(对象) AND (方法)` 括号两段式。Mesh 受标引时滞影响，周窗召回主要靠 `[tiab]` 精确词，不要只堆 Mesh；`[edat]` 时间窗由代码自动拼接。
- **arXiv**：布尔项须写成字段形式 `all:"phrase"` / `all:word`——无 `:` 的裸词会被强制 AND、OR 失效；建议设 `max_results` 上限，否则会翻整周全部命中导致限速挂起。脚本内置「totalResults 预检」，0 命中周写空 CSV 而非无关噪声。
- **bioRxiv / medRxiv**：同一检索器（Europe PMC + Crossref 超集）。**必须保留括号两段式，不要拍平成无括号的 DNF**——Europe PMC（Lucene）对无括号 AND/OR 混排会错乱。
- **chemRxiv**：仅 Crossref 收录（Europe PMC 不覆盖），是唯一无严格全文索引的平台，接受一定噪声，交给 Zotero 兜底。

## 七、密钥配置（PubMed）

PubMed 需要邮箱（必填）与 NCBI API key（可选），通过**环境变量注入，不写入仓库**：

- 本地：`export ENTREZ_EMAIL=you@example.com`，可选 `export NCBI_API_KEY=...`
- GitHub Actions：仓库 **Settings → Secrets and variables → Actions** 新建 `ENTREZ_EMAIL` 与 `NCBI_API_KEY` 两个 secret，workflow 会经 `${{ secrets.* }}` 注入运行环境。

## 八、本地运行

```bash
pip install pyPaperFlow            # 或 pip install -r requirements.txt
export ENTREZ_EMAIL=you@example.com
python monitor.py \
  --config config.yaml \           # 指定检索配置
  --out-dir . \                    # Archive/ 与 Discovery/ 落在仓库根
  --issue-body /tmp/issue.md \     # 生成的 Issue 正文（可选）
  --issue-title /tmp/issue.title   # 生成的 Issue 标题（可选）
```

常用调试参数：

- `--window-days 1`：把抓取窗口收窄到 1 天快速试跑（不改 config）；
- `--run-date 2026-09-03`：固定运行日做回测。

窗口默认不含运行当天；任一平台失败仅告警（全部失败才非零退出）。

## 九、每周阅读工作流

1. 打开仓库 **Issues** 看当周推送报告，按平台粗筛、点标题直达原文；
2. 对感兴趣的，用 Zotero 按本次 `Discovery/` 下 `_ids.txt`「按标识符添加」批量入库，去重与精筛都在这一层完成；
3. 需要全文或深挖时，用文献工具按 DOI / PMID 二次获取，再按自己的流程精读、检索与分析——下游工具（Zotero、agent、skill 等）可自由接入。

## 常见问题

- **为什么只按周，不做每日？** 模板默认 `window_days: 7` 且 cron 每周一运行；想改频次只动「三」中的两处即可。
- **抓不全 / 有噪声怎么办？** 各平台 query 的召回与噪声实测结论都写在该平台 query 上方的注释里，按注释微调即可；残余噪声靠 Zotero 层筛掉。
- **能抓全文吗？** 本模板定位是**元数据分发**，不抓全文；全文按需走你已有的文献工具获取。
