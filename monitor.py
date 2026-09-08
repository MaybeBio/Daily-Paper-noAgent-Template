#!/usr/bin/env python3
"""Standalone literature monitor.

Fetches metadata only (no PDF / full text) for the configured topic from
multiple platforms via the published `pyPaperFlow` package, and writes two kinds
of artifact under the repo root:

    Archive/    full per-paper metadata JSON (append-only, by publication month)
                Archive/<source>/<year>/<month>/<id>/<id>.json
    Discovery/  per-run merged CSV + _ids.txt for Zotero / human triage (by fetch date)
                Discovery/<year>/<month>/<topic>_<date>.csv (+ _ids.txt)

Also emits a markdown issue body + title (date-range stamped).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

import httpx
import pandas as pd
import yaml

from pyPaperFlow.preprint.arxiv_fetcher import ArxivFetcher
from pyPaperFlow.preprint.biorxiv_fetcher import BioRxivFetcher
from pyPaperFlow.preprint.chemrxiv_fetcher import ChemRxivFetcher
from pyPaperFlow.pubmed.pubmed_fetcher import PubmedFetcher

COLUMNS = ["source", "id", "doi", "title", "authors", "journal", "published_date", "url", "abstract"]
PLATFORMS = ["pubmed", "biorxiv", "arxiv", "chemrxiv", "medrxiv"]

# arXiv's native backend sorts newest-first but pages the ENTIRE week's matches when
# max_results is unset — a rich OR-query hangs. Cap keeps only the freshest records.
ARXIV_MAX_RESULTS = 150

_MONTH_ABBR = {
    m: f"{i:02d}"
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        1,
    )
}


def parse_args():
    p = argparse.ArgumentParser(description="Fetch topic literature metadata and write CSV/ids/issue.")
    p.add_argument("--config", required=True, help="Path to config.yaml")
    p.add_argument("--out-dir", default=".", help="Repo root (Archive/ + Discovery/ land here)")
    p.add_argument("--window-days", type=int, default=None, help="Override config window_days")
    p.add_argument("--run-date", default=None, help="Run date YYYY-MM-DD (default: today)")
    p.add_argument("--issue-body", default=None, help="Write issue markdown body to this path")
    p.add_argument("--issue-title", default=None, help="Write issue title (one line) to this path")
    return p.parse_args()


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("config must be a YAML mapping")
    return cfg


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _strip_version(arxiv_id):
    return re.sub(r"v\d+$", "", (arxiv_id or "").strip())


def _iso_date(value):
    """Normalize a loose publication-date string to an ISO-ish YYYY-MM-DD.

    Handles PubMed DP (e.g. "2026 Sep 2", "2026 Sep"), pre-print ISO
    (e.g. "2026-09-03"), and passes through already-ISO dates. Returns "" on
    empty, or the original string when it cannot be parsed.
    """
    s = (value or "").strip()
    if not s:
        return ""

    m = re.match(r"^\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group(0)

    # Entrez Date 格式 "2026/09/06 05:40" → 只取日期部分
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    m = re.match(r"^(\d{4})\s+([A-Za-z]{3})(?:\s+(\d{1,2}))?", s)
    if m:
        year, mon, day = m.group(1), m.group(2).title(), m.group(3)
        if mon in _MONTH_ABBR:
            return f"{year}-{_MONTH_ABBR[mon]}" + (f"-{int(day):02d}" if day else "")

    m = re.match(r"^([A-Za-z]{3})\s+(\d{4})", s)
    if m and m.group(1).title() in _MONTH_ABBR:
        return f"{m.group(2)}-{_MONTH_ABBR[m.group(1).title()]}"

    return s


def _year_month(value):
    iso = _iso_date(value)
    m = re.match(r"^(\d{4})-(\d{2})", iso or "")
    if m:
        return m.group(1), m.group(2)
    return "unknown", "unknown"


def _safe_id(value):
    text = (value or "").strip().replace("/", "_").replace("\\", "_")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return text or "unknown"


def normalize_source_paper(rec, source):
    return {
        "source": source,
        "id": rec.source_id or "",
        "doi": rec.doi or "",
        "title": rec.title or "",
        "authors": "; ".join(_as_list(getattr(rec, "authors", None))),
        "journal": rec.journal or "",
        "published_date": _iso_date(rec.published_date),
        "url": rec.landing_url or "",
        "abstract": rec.abstract or "",
    }


def normalize_pubmed(paper):
    pmid = paper.identity.pmid or ""
    journal = paper.source.journal_title
    if isinstance(journal, (tuple, list)):
        journal = journal[0] if journal else ""
    return {
        "source": "pubmed",
        "id": pmid,
        "doi": paper.identity.doi or "",
        "title": paper.identity.title or "",
        "authors": "; ".join(_as_list(paper.contributors.medline.get("full_names"))),
        "journal": journal or "",
        "published_date": _iso_date(paper.metadata.entrez_date),
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "abstract": paper.content.abstract or "",
    }


ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_NS = {"o": "http://a9.com/-/spec/opensearch/1.1/"}


def _arxiv_total_results(search_query):
    """Return arXiv's totalResults for a built search_query (0 on error/empty)."""
    try:
        resp = httpx.get(
            ARXIV_API,
            params={"search_query": search_query, "start": 0, "max_results": 1},
            timeout=30,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        el = root.find("o:totalResults", ARXIV_NS)
        return int(el.text) if el is not None and el.text else 0
    except Exception:
        return 0


def fetch_platform(platform, cfg, start, end, root_dir):
    """Return (rows, metas) where rows drives CSV and metas drives Archive JSON."""
    query = cfg["platforms"][platform]["query"]

    if platform == "pubmed":
        email = (os.environ.get("ENTREZ_EMAIL") or "").strip()
        if not email:
            raise ValueError("ENTREZ_EMAIL env var is required for the pubmed platform")
        api_key = os.environ.get("NCBI_API_KEY") or ""
        dated = f'({query}) AND ("{start.replace("-", "/")}"[edat] : "{end.replace("-", "/")}"[edat])'
        fetcher = PubmedFetcher(root_dir=root_dir, entrez_email=email, api_key=api_key)
        meta = fetcher.query_search(dated)
        if meta.get("count", 0) == 0 or "webenv" not in meta:
            return [], []
        pmids = fetcher.get_pubmedIDs_from_query(meta, retmax=500)
        if not pmids:
            return [], []
        papers = fetcher.fetch_from_pmid_list(pmids, output_dir=root_dir)
        rows = [normalize_pubmed(p) for p in papers]
        metas = [
            {
                "source": "pubmed",
                "id": p.identity.pmid or "",
                "published_date": _iso_date(p.metadata.entrez_date),
                "data": p.to_dict(),
            }
            for p in papers
        ]
        return rows, metas

    if platform == "arxiv":
        max_results = cfg["platforms"][platform].get("max_results", ARXIV_MAX_RESULTS)
        # pyPaperFlow falls back to a looser query when the first page is empty; on a
        # genuinely empty week that fallback silently returns unrelated newest preprints.
        # Pre-flight the built query so a 0-hit week writes an empty CSV instead of noise.
        fetcher = ArxivFetcher(root_dir=root_dir)
        search_query = fetcher.build_query(query, start_date=start, end_date=end)
        if _arxiv_total_results(search_query) <= 0:
            records = []
        else:
            records = fetcher.search(query=query, max_results=max_results, start_date=start, end_date=end)
    elif platform in ("biorxiv", "medrxiv"):
        records = BioRxivFetcher(root_dir=root_dir, platform=platform).search(query=query, start_date=start, end_date=end)
    elif platform == "chemrxiv":
        records = ChemRxivFetcher(root_dir=root_dir).search(query=query, start_date=start, end_date=end)
    else:
        raise ValueError(f"unknown platform: {platform}")

    rows = [normalize_source_paper(r, platform) for r in records]
    metas = [
        {
            "source": platform,
            "id": r.source_id or "",
            "published_date": _iso_date(r.published_date),
            "data": r.to_dict(),
        }
        for r in records
    ]
    return rows, metas


def _zotero_id(row):
    source = row["source"]
    if source == "arxiv":
        return f"arXiv:{_strip_version(row['id'])}"
    if source == "pubmed":
        return f"pmid:{row['id']}"
    return row["id"]


def write_discovery(out_dir, topic, date_str, all_rows):
    year, month, _ = date_str.split("-")
    d = os.path.join(out_dir, "Discovery", year, month)
    os.makedirs(d, exist_ok=True)
    stem = f"{topic}_{date_str}"
    csv_path = os.path.join(d, stem + ".csv")
    ids_path = os.path.join(d, stem + "_ids.txt")

    df = pd.DataFrame(all_rows, columns=COLUMNS)
    df.to_csv(csv_path, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")

    ids = [_zotero_id(r) for r in all_rows]
    with open(ids_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ids) + ("\n" if ids else ""))

    return csv_path, ids_path, len(all_rows)


def write_archive(out_dir, metas):
    count = 0
    for m in metas:
        sid = _safe_id(m["id"])
        year, month = _year_month(m["published_date"])
        d = os.path.join(out_dir, "Archive", m["source"], year, month, sid)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, sid + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(m["data"], f, ensure_ascii=False, indent=2, default=str)
        count += 1
    return count


def _short_authors(authors_str, limit=3):
    parts = [a.strip() for a in (authors_str or "").split(";") if a.strip()]
    if not parts:
        return ""
    if len(parts) <= limit:
        return "; ".join(parts)
    return "; ".join(parts[:limit]) + "; et al."


def issue_title(start, end, total):
    return f"📅 {start} ~ {end} 本周文献推送（{total} 篇）"


def build_issue(rows_by_platform, start, end):
    total = sum(len(v) for v in rows_by_platform.values())
    if total == 0:
        return ""
    lines = [f"本周推送 {total} 篇（{start} ~ {end}）", ""]
    for platform in PLATFORMS:
        rows = rows_by_platform.get(platform)
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: (r["published_date"] or "")[:10])
        lines.append(f"## {platform}（{len(rows)}）")
        lines.append("")
        lines.append("| 标题 | 作者 | 日期 |")
        lines.append("|---|---|---|")
        for r in rows:
            title = (r["title"] or "untitled").replace("|", "\\|").replace("\n", " ")
            url = r["url"] or ""
            cell = f"[{title}]({url})" if url else title
            lines.append(f"| {cell} | {_short_authors(r['authors'])} | {(r['published_date'] or '')[:10]} |")
        lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    cfg = load_config(args.config)
    topic = (cfg.get("topic") or "topic").strip()
    window_days = args.window_days if args.window_days is not None else int(cfg.get("window_days", 7))
    run_date = args.run_date or dt.date.today().isoformat()
    # 窗口 = 运行日之前 window_days 个自然日，不含运行当天（当天文献尚未可抓）
    end = (dt.date.fromisoformat(run_date) - dt.timedelta(days=1)).isoformat()
    start = (dt.date.fromisoformat(run_date) - dt.timedelta(days=window_days)).isoformat()

    platforms = [p for p in PLATFORMS if p in cfg.get("platforms", {})]
    if not platforms:
        print("No platforms configured.", file=sys.stderr)
        sys.exit(1)

    tmp = tempfile.mkdtemp(prefix="monitor_")
    rows_by_platform = {}
    all_rows = []
    failures = []
    try:
        for platform in platforms:
            try:
                rows, metas = fetch_platform(platform, cfg, start, end, tmp)
                rows_by_platform[platform] = rows
                all_rows.extend(rows)
                archived = write_archive(args.out_dir, metas)
                print(f"[{platform}] {len(rows)} records (archived {archived})")
            except Exception as e:
                print(f"[{platform}] FAILED: {e}", file=sys.stderr)
                failures.append(platform)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    csv_path, ids_path, n = write_discovery(args.out_dir, topic, run_date, all_rows)
    print(f"[total] {n} records -> {csv_path} + {ids_path}")

    total = sum(len(v) for v in rows_by_platform.values())
    if args.issue_body:
        with open(args.issue_body, "w", encoding="utf-8") as f:
            f.write(build_issue(rows_by_platform, start, end))
    if args.issue_title and total > 0:
        with open(args.issue_title, "w", encoding="utf-8") as f:
            f.write(issue_title(start, end, total) + "\n")

    if failures:
        print(f"Warning: {len(failures)} platform(s) failed: {failures}", file=sys.stderr)
        if len(failures) == len(platforms):
            sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()