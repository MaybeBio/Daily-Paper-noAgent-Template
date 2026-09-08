# idp-interaction-ai — 无序蛋白互作 × AI

无序蛋白/无序区（IDP/IDR）介导的蛋白质互作，含相分离与凝聚体；方法限定为深度学习、分子动力学与对接。

每周从 PubMed / arXiv / bioRxiv / medRxiv / chemRxiv 抓取最新文献元数据，提交并推送回本仓库，同时创建一条 Issue 汇总。本地用 Zotero 按 `_ids.txt` 批量导入筛选。

## 仓库结构

- `monitor.py` — 读取 `config.yaml`，逐平台检索，规范化后写入 `Discovery/`（合并 CSV + `_ids.txt`）与 `Archive/`（逐篇元数据 JSON），并生成 Issue 正文与标题。
- `config.yaml` — 检索配置：课题短名、时间窗口、每平台一条布尔检索式。PubMed 邮箱与 API key 通过环境变量注入，不写入文件。
- `.github/workflows/monitor.yml` — 每周一 09:23 UTC 自动运行，支持 `workflow_dispatch` 手动触发。

## 产出

```
Archive/                                # 逐篇完整元数据 JSON，只增不删，按年月归档（PubMed 按 entrez date，见「日期口径」）
  {source}/{year}/{month}/{id}/{id}.json
Discovery/                              # 每次运行一份合并 CSV 与 _ids.txt，按抓取日归档
  {year}/{month}/idp-interaction-ai_{date}.csv
  {year}/{month}/idp-interaction-ai_{date}_ids.txt
```

`source` 取值为 `pubmed`、`arxiv`、`biorxiv`、`medrxiv`、`chemrxiv`。

CSV 共 9 列：`source, id, doi, title, authors, journal, published_date, url, abstract`。`id` 为各平台主键（PubMed 为 PMID，预印本为 DOI），`doi` 为跨平台规范标识，`published_date` 统一为 ISO 日期 `YYYY-MM-DD`（PubMed 用 entrez date，预印本用 posting 日期，见「日期口径」）。

`_ids.txt` 每行一个标识符，带类型前缀（`pmid:xxx`、`arXiv:xxx`，DOI 裸写），供 Zotero「按标识符添加」批量导入。

不做跨平台去重，也不判定是否已入库；重复与筛选由 Zotero 处理。当周无命中时，CSV 仅含表头。

## 日期口径（entrez date）

PubMed 的「发表日期」（DP）经常残缺或滞后——ahead-of-print 无日期、只到年月、空值，且文献被 PubMed 收录的时间晚于正式发表（标引时滞）。因此 PubMed 全线改用 **entrez date**（`[edat]`，即文献被 PubMed 收录的日期，形如 `YYYY/MM/DD HH:MM`），搜索、归档、Issue 三处同源：

- **搜索**：查询窗口用 `[edat]` 过滤，抓取「本周新进 PubMed 的文献」。每篇只在被收录那一周出现一次，无需重叠窗口与去重，`window_days: 7` 即可。
- **归档**：`Archive/pubmed/{year}/{month}/{id}/` 按 entrez date 归档，不再因 DP 残缺落进 `unknown/`。
- **Issue**：日期列显示 entrez date（归一为 `YYYY-MM-DD`），并按它升序排序。

真实发表日期并未丢弃——每篇完整元数据（含 DP）仍保留在 `Archive/*.json` 的 `data.source.pub_date` 中，需要时可随时取出。

预印本（arXiv / bioRxiv / medRxiv / chemRxiv）无标引时滞，仍用各自 posting 日期，不受影响。

## 密钥（PubMed）

PubMed 检索需要邮箱（必填）与 NCBI API key（可选），通过环境变量注入，不写入仓库：

- 本地：`export ENTREZ_EMAIL=you@example.com`，可选 `export NCBI_API_KEY=...`
- GitHub Actions：仓库 Settings → Secrets and variables → Actions → New repository secret，添加 `ENTREZ_EMAIL` 与 `NCBI_API_KEY` 两个 secret。

## 本地运行

```bash
pip install pyPaperFlow
export ENTREZ_EMAIL=you@example.com
python monitor.py --config config.yaml --out-dir . --issue-body /tmp/issue.md
```

调整时间窗口：`--window-days 1`，或修改 `config.yaml` 中的 `window_days`。

平台 query 语法与调优记录见母仓 `docs/topics-catalog.md` 与本课题 `topics/idp-interaction-ai/test-notes.md`。
