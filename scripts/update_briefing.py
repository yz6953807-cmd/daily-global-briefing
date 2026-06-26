#!/usr/bin/env python3
"""Generate the daily briefing page for GitHub Pages.

This script is intentionally dependency-free so GitHub Actions can run it
reliably. If ARK_API_KEY is configured as a GitHub Secret, it asks Doubao/Ark
to synthesize a more professional bilingual report from fetched public items.
If the model is unavailable, it still updates the page from public feeds.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import textwrap
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")
RUN_STARTED_AT = datetime.now(TZ)
TODAY = RUN_STARTED_AT.date()
DATE_STR = TODAY.isoformat()
USER_AGENT = "daily-global-briefing/1.0 (+https://yz6953807-cmd.github.io/daily-global-briefing/)"
ARK_ENDPOINT = os.environ.get("ARK_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
ARK_MODEL = os.environ.get("ARK_MODEL") or "doubao-seed-1-6-250615"
RECENT_DATES = {TODAY, TODAY - timedelta(days=1)}
MAX_ARTICLES = 8
MAX_SOURCE_ITEMS = 2
MAX_GROUP_ITEMS = 4


def run_metadata(article_count: int | None = None, source_count: int | None = None) -> dict[str, object]:
    """Small status payload committed with every successful scheduled run."""
    status: dict[str, object] = {
        "date": DATE_STR,
        "generatedAt": RUN_STARTED_AT.isoformat(timespec="seconds"),
        "timezone": "Asia/Shanghai",
        "trigger": os.environ.get("DAILY_BRIEFING_TRIGGER", "local"),
        "runId": os.environ.get("DAILY_BRIEFING_RUN_ID", ""),
        "runAttempt": os.environ.get("DAILY_BRIEFING_RUN_ATTEMPT", ""),
        "reason": os.environ.get("DAILY_BRIEFING_REASON", ""),
    }
    if article_count is not None:
        status["articleCount"] = article_count
    if source_count is not None:
        status["sourceItemCount"] = source_count
    return status


def status_line_cn() -> str:
    run_id = os.environ.get("DAILY_BRIEFING_RUN_ID", "").strip()
    run_text = f" · GitHub Actions run {run_id}" if run_id else ""
    return f"云端更新时间：{RUN_STARTED_AT.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai{run_text}"


def status_line_en() -> str:
    run_id = os.environ.get("DAILY_BRIEFING_RUN_ID", "").strip()
    run_text = f" · GitHub Actions run {run_id}" if run_id else ""
    return f"Cloud refresh: {RUN_STARTED_AT.strftime('%Y-%m-%d %H:%M:%S')} Asia/Shanghai{run_text}"


FEEDS = [
    ("Financial Times", "https://www.ft.com/rss/home", "财经"),
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "财经"),
    ("WSJ Technology", "https://feeds.a.dj.com/rss/RSSWSJD.xml", "科技"),
    ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "财经"),
    ("CNBC World News", "https://www.cnbc.com/id/100727362/device/rss/rss.html", "政策"),
    ("CNBC Technology", "https://www.cnbc.com/id/19854910/device/rss/rss.html", "科技"),
    ("Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar", "财经"),
    ("The Guardian Business", "https://www.theguardian.com/business/rss", "财经"),
    ("The Guardian Technology", "https://www.theguardian.com/technology/rss", "科技"),
    ("The Guardian Environment", "https://www.theguardian.com/environment/rss", "能源"),
    ("The Guardian Science", "https://www.theguardian.com/science/rss", "科技"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "财经"),
    ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "科技"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "政策"),
    ("TechCrunch", "https://techcrunch.com/feed/", "科技"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "科技"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "科技"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "科技"),
    ("OpenAI News", "https://openai.com/news/rss.xml", "AI"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "政策"),
    ("DW News", "https://rss.dw.com/rdf/rss-en-all", "政策"),
    ("France 24", "https://www.france24.com/en/rss", "政策"),
    ("Euronews", "https://www.euronews.com/rss?level=theme&name=news", "政策"),
    ("SEC Press Releases", "https://www.sec.gov/news/pressreleases.rss", "财经"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "政策"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "财经"),
    ("ECB", "https://www.ecb.europa.eu/rss/press.html", "财经"),
    ("IMF", "https://www.imf.org/en/News/RSS", "财经"),
    ("Nature", "https://www.nature.com/nature.rss", "科技"),
    ("STAT News", "https://www.statnews.com/feed/", "科技"),
    ("NASA News", "https://www.nasa.gov/news-release/feed/", "科技"),
    ("arXiv AI", "https://rss.arxiv.org/rss/cs.AI", "AI"),
    ("arXiv Machine Learning", "https://rss.arxiv.org/rss/cs.LG", "AI"),
]


KEYWORDS = {
    "财经": [
        "market", "markets", "inflation", "growth", "rate", "fed", "ecb", "debt",
        "bond", "oil", "bank", "trade", "tariff", "currency", "finance", "gdp",
        "earnings", "stock", "risk", "recession", "central bank", "ipo", "listing",
        "merger", "acquisition", "m&a", "buyout", "valuation", "bankruptcy",
        "default", "profit", "revenue", "layoff", "jobs", "funding", "venture",
        "private equity", "sec", "fraud", "fine", "settlement", "probe",
    ],
    "科技": [
        "technology", "chip", "semiconductor", "data center", "cloud", "cyber",
        "quantum", "space", "science", "battery", "robot", "software",
        "startup", "apple", "google", "microsoft", "amazon", "meta", "tesla",
        "nvidia", "openai", "anthropic", "cyberattack", "breach", "hack",
        "satellite", "biotech", "drug", "trial", "launch",
    ],
    "政策": [
        "policy", "government", "regulation", "sanction", "security", "war",
        "election", "minister", "white house", "eu", "china", "tariff",
        "investigation", "antitrust", "lawsuit", "court", "ban", "export control",
        "corruption", "scandal", "whistleblower", "parliament", "congress",
        "geopolitical", "military", "defense", "nato", "russia", "iran",
    ],
    "能源": [
        "energy", "oil", "gas", "lng", "power", "grid", "climate", "shipping",
        "strait", "opec", "renewable", "electricity", "nuclear", "coal",
        "pipeline", "refinery", "blackout", "supply crunch",
    ],
    "AI": [
        "ai", "artificial intelligence", "model", "openai", "anthropic", "nvidia",
        "gpu", "machine learning", "llm", "compute", "chip", "frontier model",
        "agent", "inference", "training", "datacenter", "data center",
    ],
}


IMPACT_KEYWORDS = [
    "ipo", "listing", "market debut", "files to go public", "merger", "acquisition",
    "m&a", "buyout", "takeover", "valuation", "funding round", "bankruptcy",
    "default", "debt crisis", "earnings", "profit warning", "layoff", "job cuts",
    "fraud", "scandal", "investigation", "probe", "antitrust", "lawsuit",
    "charged", "settlement", "fine", "penalty", "sanction", "export control",
    "tariff", "ban", "security breach", "data breach", "cyberattack", "hack",
    "chip", "semiconductor", "ai", "artificial intelligence", "data center",
    "nuclear", "oil", "gas", "lng", "blackout", "supply crunch", "central bank",
    "inflation", "interest rate", "war", "military", "geopolitical", "crisis",
]


SOFT_NEWS_KEYWORDS = [
    "football", "world cup", "podcast", "celebrity", "recipe", "fashion",
    "australia politics live", "live:", "sport", "tennis", "cricket", "movie",
    "music", "duck off", "career spotlight", "travel", "restaurant", "garden",
    "wellness", "ageing", "aging", "lifestyle", "horoscope", "quiz", "tv",
    "book review", "theatre", "theater", "dating", "royal", "weather forecast",
    "editor's letter", "editors letter", "photo essay", "week in review",
    "all challenges big and small",
]


SOURCE_CN = {
    "Financial Times": "金融时报",
    "WSJ Markets": "华尔街日报市场频道",
    "WSJ Technology": "华尔街日报科技频道",
    "CNBC Top News": "CNBC 头条新闻",
    "CNBC World News": "CNBC 世界新闻",
    "CNBC Technology": "CNBC 科技频道",
    "Nikkei Asia": "日经亚洲",
    "The Guardian Business": "卫报商业频道",
    "The Guardian Technology": "卫报科技频道",
    "The Guardian Environment": "卫报环境频道",
    "The Guardian Science": "卫报科学频道",
    "BBC Business": "BBC 商业频道",
    "BBC Technology": "BBC 科技频道",
    "BBC World": "BBC 世界新闻",
    "TechCrunch": "TechCrunch 科技媒体",
    "MIT Technology Review": "MIT 科技评论",
    "The Verge": "The Verge 科技媒体",
    "Ars Technica": "Ars Technica 科技媒体",
    "OpenAI News": "OpenAI 官方新闻",
    "Al Jazeera": "半岛电视台",
    "DW News": "德国之声",
    "France 24": "法国 24",
    "Euronews": "欧洲新闻台",
    "SEC Press Releases": "美国证券交易委员会",
    "UN News": "联合国新闻",
    "Federal Reserve": "美联储",
    "ECB": "欧洲央行",
    "IMF": "国际货币基金组织",
    "Nature": "Nature 期刊",
    "STAT News": "STAT 医药科技新闻",
    "NASA News": "NASA 官方新闻",
    "arXiv AI": "arXiv AI 论文库",
    "arXiv Machine Learning": "arXiv 机器学习论文库",
}


SOURCE_GROUP = {
    "Financial Times": "global-financial-media",
    "WSJ Markets": "global-financial-media",
    "WSJ Technology": "global-financial-media",
    "CNBC Top News": "global-financial-media",
    "CNBC World News": "global-financial-media",
    "CNBC Technology": "global-financial-media",
    "Nikkei Asia": "asia-media",
    "The Guardian Business": "uk-europe-media",
    "The Guardian Technology": "uk-europe-media",
    "The Guardian Environment": "uk-europe-media",
    "The Guardian Science": "uk-europe-media",
    "BBC Business": "uk-europe-media",
    "BBC Technology": "uk-europe-media",
    "BBC World": "uk-europe-media",
    "Al Jazeera": "global-world-media",
    "DW News": "uk-europe-media",
    "France 24": "uk-europe-media",
    "Euronews": "uk-europe-media",
    "TechCrunch": "tech-media",
    "MIT Technology Review": "tech-media",
    "The Verge": "tech-media",
    "Ars Technica": "tech-media",
    "OpenAI News": "official-institutions",
    "SEC Press Releases": "official-institutions",
    "UN News": "official-institutions",
    "Federal Reserve": "official-institutions",
    "ECB": "official-institutions",
    "IMF": "official-institutions",
    "NASA News": "official-institutions",
    "Nature": "science-research",
    "STAT News": "science-research",
    "arXiv AI": "science-research",
    "arXiv Machine Learning": "science-research",
}


@dataclass
class FeedItem:
    title: str
    link: str
    source: str
    category: str
    summary: str
    published: datetime
    score: float = 0.0


def log(message: str) -> None:
    print(f"[daily-briefing] {message}", flush=True)


def clean_text(value: str, limit: int | None = None) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def fetch_url(url: str, timeout: int = 18) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def first_text(node: ET.Element, names: list[str]) -> str:
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text
        for child in node.iter():
            if child.tag.endswith(name.strip("{}")) and child.text:
                return child.text
    return ""


def first_link(node: ET.Element) -> str:
    link = first_text(node, ["link"])
    if link:
        return link.strip()
    for child in node.iter():
        if child.tag.endswith("link"):
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def parse_feed(source: str, url: str, category: str) -> list[FeedItem]:
    try:
        raw = fetch_url(url)
        root = ET.fromstring(raw)
    except Exception as exc:
        log(f"feed failed: {source}: {exc}")
        return []

    nodes = root.findall(".//item") or [n for n in root.iter() if n.tag.endswith("entry")]
    items: list[FeedItem] = []
    for node in nodes[:24]:
        title = clean_text(first_text(node, ["title"]), 180)
        link = first_link(node)
        summary = clean_text(first_text(node, ["description", "summary", "content", "{http://www.w3.org/2005/Atom}summary"]), 520)
        published = parse_date(first_text(node, ["pubDate", "published", "updated"]))
        if not title or not link:
            continue
        items.append(FeedItem(title=title, link=link, source=source, category=category, summary=summary, published=published))
    return items


def infer_categories(item: FeedItem) -> list[str]:
    text = f"{item.title} {item.summary}".lower()
    cats = {item.category}
    for category, words in KEYWORDS.items():
        if any(word in text for word in words):
            cats.add(category)
    return sorted(cats, key=lambda x: ["财经", "科技", "政策", "能源", "AI"].index(x) if x in ["财经", "科技", "政策", "能源", "AI"] else 99)


def score_item(item: FeedItem) -> float:
    text = f"{item.title} {item.summary}".lower()
    if any(word in text for word in SOFT_NEWS_KEYWORDS):
        return -50
    keyword_hits = 0
    for words in KEYWORDS.values():
        keyword_hits += sum(1 for word in words if word in text)
    impact_hits = sum(1 for word in IMPACT_KEYWORDS if word in text)
    if keyword_hits == 0 and impact_hits == 0 and item.source.startswith(("The Guardian", "BBC", "UN")):
        return -20
    if impact_hits == 0 and item.source in {"BBC World", "UN News"}:
        return -12
    age_hours = max(0.0, (datetime.now(timezone.utc) - item.published).total_seconds() / 3600)
    score = max(0, 72 - age_hours) / 8
    for words in KEYWORDS.values():
        score += sum(1.2 for word in words if word in text)
    score += impact_hits * 3.5
    if any(word in text for word in ["breaking", "tariff", "central bank", "ai", "chip", "oil", "sanction", "inflation", "growth", "ipo", "fraud", "antitrust"]):
        score += 5
    if item.source in {"Federal Reserve", "ECB", "IMF", "SEC Press Releases", "UN News", "OpenAI News", "NASA News", "Nature"}:
        score += 2.5
    if item.source in {"Financial Times", "WSJ Markets", "WSJ Technology", "CNBC Top News", "CNBC World News", "Nikkei Asia"}:
        score += 2.0
    if item.source in {"TechCrunch", "MIT Technology Review", "The Verge", "Ars Technica", "BBC Business", "BBC Technology"}:
        score += 1.5
    return score


def published_local_date(item: FeedItem):
    return item.published.astimezone(TZ).date()


def is_recent_publication(item: FeedItem) -> bool:
    return published_local_date(item) in RECENT_DATES


def source_group(source: str) -> str:
    return SOURCE_GROUP.get(source, "other-authoritative-source")


def source_family(source: str) -> str:
    family_prefixes = {
        "CNBC": "CNBC",
        "WSJ": "Wall Street Journal",
        "The Guardian": "The Guardian",
        "BBC": "BBC",
        "arXiv": "arXiv",
    }
    for prefix, family in family_prefixes.items():
        if source.startswith(prefix):
            return family
    return source


def date_window_cn() -> str:
    return " / ".join(f"{day.month}月{day.day}日" for day in sorted(RECENT_DATES, reverse=True))


def date_window_en() -> str:
    return " / ".join(day.strftime("%b %-d, %Y") if sys.platform != "win32" else day.strftime("%b %d, %Y") for day in sorted(RECENT_DATES, reverse=True))


def diversify_items(candidates: list[FeedItem], limit: int = 12) -> list[FeedItem]:
    family_counts: dict[str, int] = {}
    group_counts: dict[str, int] = {}
    selected: list[FeedItem] = []

    def try_add(item: FeedItem, *, unique_family: bool, relax_group: bool = False) -> bool:
        family = source_family(item.source)
        group = source_group(item.source)
        if item in selected:
            return False
        if unique_family and family_counts.get(family, 0) > 0:
            return False
        if family_counts.get(family, 0) >= MAX_SOURCE_ITEMS:
            return False
        if group_counts.get(group, 0) >= MAX_GROUP_ITEMS:
            if not relax_group:
                return False
        selected.append(item)
        family_counts[family] = family_counts.get(family, 0) + 1
        group_counts[group] = group_counts.get(group, 0) + 1
        return True

    for item in candidates:
        try_add(item, unique_family=True)
        if len(selected) >= limit:
            return selected

    for item in candidates:
        try_add(item, unique_family=False)
        if len(selected) >= limit:
            return selected

    # Keep the same-publisher cap strict, but relax group caps if a quiet news day
    # leaves too few cross-category items.
    for item in candidates:
        try_add(item, unique_family=False, relax_group=True)
        if len(selected) >= limit:
            break

    return selected


def collect_items() -> list[FeedItem]:
    all_items: list[FeedItem] = []
    for source, url, category in FEEDS:
        all_items.extend(parse_feed(source, url, category))
        time.sleep(0.2)

    recent_items = [item for item in all_items if is_recent_publication(item)]
    seen: set[str] = set()
    deduped: list[FeedItem] = []
    for item in recent_items:
        key = topic_key(item)
        if key in seen:
            continue
        seen.add(key)
        item.score = score_item(item)
        if item.score > 6:
            deduped.append(item)

    deduped.sort(key=lambda item: (item.score, item.published), reverse=True)
    selected = diversify_items(deduped, 12)
    log(
        f"collected {len(all_items)} feed items, "
        f"{len(recent_items)} within {date_window_cn()}, selected {len(selected)} "
        f"from {len({source_family(item.source) for item in selected})} source families"
    )
    return selected


def item_payload(items: list[FeedItem]) -> list[dict[str, str]]:
    payload = []
    for item in items:
        payload.append(
            {
                "title": item.title,
                "source": item.source,
                "category": item.category,
                "categories": " · ".join(infer_categories(item)),
                "published": item.published.astimezone(TZ).strftime("%Y-%m-%d %H:%M"),
                "summary": item.summary,
                "url": item.link,
            }
        )
    return payload


def ask_ark(items: list[FeedItem]) -> dict | None:
    api_key = os.environ.get("ARK_API_KEY", "").strip()
    if not api_key:
        return None

    system = (
        "你是专业财经科技政策早报编辑。只输出合法 JSON，不要 markdown。"
        "必须基于给定公开来源条目，不要编造未给出的具体数字。"
    )
    user = {
        "date": DATE_STR,
        "timezone": "Asia/Shanghai",
        "allowed_publication_dates": sorted(day.isoformat() for day in RECENT_DATES),
        "task": (
            "从这些公开来源条目中筛选 8 条最重要新闻，生成中英文网页日报。"
            "只能使用 allowed_publication_dates 内发布或更新的条目；如果不足 8 条，宁可少写，不要使用更早日期。"
            "来源必须多元：同一来源最多 2 条，尽量覆盖全球财经媒体、国际新闻机构、官方机构、科技专业源和研究来源。"
            "优先全球范围内真正重磅的信息：央行和财政政策、市场和通胀冲击、IPO/上市、并购融资、公司丑闻或监管调查、反垄断、重大诉讼、网络安全泄露、AI/芯片/云/数据中心、能源通道、地缘安全和关键科技突破。"
            "剔除无关痛痒的地方政治直播、体育娱乐、生活方式、职业介绍、软性人物故事和泛泛科普。"
            "中文要专业但易懂，每条两段；英文是对应真实英文版本。"
            "如果条目摘要缺少数据，请用来源、时间、机构、影响链条和观察点补足，不要伪造数字。"
            "source 字段必须原样使用 items.source 的英文来源名，url 必须原样使用 items.url。"
        ),
        "required_json_schema": {
            "summary_cn": "一句今日主线，70-120字",
            "summary_en": "English daily thesis, 45-80 words",
            "metrics": [{"value": "短数字", "cn": "中文解释", "en": "English explanation"}],
            "articles": [
                {
                    "title_cn": "含序号中文标题",
                    "title_en": "numbered English title",
                    "tag_cn": "财经 · 科技",
                    "tag_en": "Markets · Technology",
                    "points": [{"value": "数字或关键词", "cn": "中文说明", "en": "English note"}],
                    "readouts": [{"label_cn": "专业读数", "text_cn": "中文", "label_en": "Readout", "text_en": "English"}],
                    "paragraphs_cn": ["中文第一段", "中文第二段"],
                    "paragraphs_en": ["English paragraph 1", "English paragraph 2"],
                    "why_cn": "为什么重要：...",
                    "why_en": "Why it matters: ...",
                    "watch_cn": "继续观察：...",
                    "watch_en": "Watch: ...",
                    "source": "来源名",
                    "url": "来源链接",
                }
            ],
            "footnote_cn": "来源与不确定性说明",
            "footnote_en": "Source and caveat note",
        },
        "items": item_payload(items),
    }

    body = json.dumps(
        {
            "model": ARK_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.35,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        ARK_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S)
        parsed = json.loads(content)
        if len(parsed.get("articles", [])) >= 5:
            log("Ark synthesis succeeded")
            return parsed
    except Exception as exc:
        log(f"Ark synthesis failed, using fallback: {exc}")
    return None


def zh_category(categories: list[str]) -> str:
    return " · ".join(categories[:2]) if categories else "全球"


def en_category(categories: list[str]) -> str:
    mapping = {"财经": "Markets", "科技": "Technology", "政策": "Policy", "能源": "Energy", "AI": "AI"}
    return " · ".join(mapping.get(cat, cat) for cat in categories[:2]) if categories else "Global"


def source_cn_name(source: str) -> str:
    return SOURCE_CN.get(source, source)


def has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def topic_key(item: FeedItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    topic_patterns = [
        ("openai-broadcom-chip", ["openai", "broadcom", "chip"]),
        ("google-play-store-payments", ["google", "play store", "payments"]),
        ("microsoft-quantum-claims", ["microsoft", "quantum", "claims"]),
        ("cerebras-earnings", ["cerebras", "earnings"]),
        ("nvidia-smuggled-chips", ["nvidia", "smuggled", "chips"]),
        ("north-sea-oil-gas", ["north sea", "oil", "gas"]),
        ("oil-price-gouging", ["oil", "price gouging"]),
        ("france-heatwave-infrastructure", ["heatwave", "french infrastructure"]),
        ("micron-ai-chips-profit", ["micron", "profit", "ai", "chips"]),
    ]
    for key, words in topic_patterns:
        if all(word in text for word in words):
            return key
    key = re.sub(r"[^a-z0-9]+", " ", item.title.lower()).strip()
    return " ".join(key.split()[:12])


def fallback_cn_title(index: int, item: FeedItem, categories: list[str]) -> str:
    text = f"{item.title} {item.summary}".lower()
    cases = [
        (["ai stock sell-off", "ai stock sell off"], "AI 科技股抛售扩散，市场重新审视算力投资回报"),
        (["north sea", "oil and gas"], "北海油气开发争议升温，能源安全与就业压力重新摆上台面"),
        (["price gouging", "oil companies"], "美国要求调查油企价格操纵，能源通胀政治压力升温"),
        (["grid operator", "extra power", "supply crunch"], "英国电网高价采购备用电力，极端天气考验能源韧性"),
        (["cerebras", "stock plunges"], "Cerebras 财报后股价大跌，AI 芯片公司盈利预期受审视"),
        (["openai", "custom chip", "broadcom"], "OpenAI 推进自研芯片，AI 算力供应链继续重组"),
        (["chip war", "match act", "export control"], "全球芯片政策博弈升级，半导体供应链继续被安全议程重写"),
        (["nato", "iran war"], "北约与伊朗冲突立场分歧，美国盟友关系承压"),
        (["spacesail", "starlink"], "中国低轨卫星项目受关注，全球卫星互联网竞争升温"),
        (["ebola", "congo"], "刚果埃博拉疫情扩散，公共卫生响应压力上升"),
        (["reinforcement learning", "beneficial models"], "强化学习研究推进，AI 模型安全与长期收益成为焦点"),
        (["micron", "profit", "chips"], "Micron 利润暴增，AI 芯片需求继续推高存储周期"),
        (["ipo", "listing", "go public"], "IPO 与上市动态升温，资本市场风险偏好出现新信号"),
        (["antitrust", "investigation", "probe", "lawsuit"], "监管调查和诉讼风险上升，企业合规压力继续加码"),
        (["cyberattack", "data breach", "hack"], "网络攻击和数据泄露风险升温，数字基础设施安全受考验"),
    ]
    for words, title in cases:
        if has_any(text, words):
            return f"{index}. {title}"

    if "AI" in categories or has_any(text, ["ai", "artificial intelligence", "model", "gpu"]):
        return f"{index}. AI 与算力产业出现新动向，技术路线和商业回报继续受检验"
    if "能源" in categories or has_any(text, ["oil", "gas", "power", "grid", "energy"]):
        return f"{index}. 全球能源供需出现新变化，价格、就业和通胀传导值得关注"
    if "财经" in categories or has_any(text, ["market", "stock", "debt", "rate", "bank", "earnings"]):
        return f"{index}. 全球资本市场出现新信号，投资者重新评估风险和回报"
    if "科技" in categories:
        return f"{index}. 关键科技产业出现新进展，供应链和竞争格局继续变化"
    if "政策" in categories:
        return f"{index}. 重大政策和监管动态更新，全球风险预期可能调整"
    return f"{index}. 今日全球重点消息更新，后续影响仍需跟踪"


def fallback_cn_context(item: FeedItem, categories: list[str]) -> tuple[str, str, str, str]:
    text = f"{item.title} {item.summary}".lower()
    theme = zh_category(categories)
    if has_any(text, ["ai stock sell-off", "ai stock sell off"]):
        return (
            "美国 AI 相关股票抛售继续向全球市场传导，投资者开始从“技术想象空间”转向“资本开支能否兑现回报”的审计逻辑。半导体、云计算、服务器、电力和数据中心链条都会受到估值重估影响。",
            "这类波动不代表 AI 长期趋势结束，而是市场在重新计算投入周期、融资成本和企业端付费速度。接下来真正重要的是云厂商资本开支指引、AI 芯片订单能见度和应用收入转化。",
            "估值重估",
            "AI 交易从叙事驱动转向回报驱动，可能影响全球科技股权重、硬件订单和风险资本退出节奏。",
        )
    if has_any(text, ["north sea", "oil and gas"]):
        return (
            "围绕北海油气资源继续开发的争论升温，背后是能源安全、就业稳定和气候目标之间的拉扯。传统能源项目即使处在长期转型压力下，短期仍会影响地区就业、财政收入和能源供应弹性。",
            "这类新闻的关键不是单一油气田，而是欧洲在高电价、工业竞争力和净零目标之间如何取舍。若政策摇摆加剧，能源企业资本开支和供应预期都会更难判断。",
            "能源安全",
            "能源转型不是线性退出，传统油气资产仍可能在供应安全和就业政治中获得更高权重。",
        )
    if has_any(text, ["price gouging", "oil companies"]):
        return (
            "美国围绕油企价格行为的调查压力上升，说明能源价格已经从市场问题进入政治和监管议程。油价、炼油利润和消费者通胀之间的关系，正在成为政府干预和企业合规的焦点。",
            "如果调查扩大，油企可能面临更高披露压力、监管风险和利润审查。对市场来说，重点要看这是否只是政治表态，还是会演变成实际执法、罚款或行业规则变化。",
            "监管调查",
            "能源通胀一旦进入执法和政治议程，企业利润、油价预期和选民成本感知都会被重新定价。",
        )
    if has_any(text, ["grid operator", "extra power", "supply crunch"]):
        return (
            "英国电网为避免供应紧张而高价采购额外电力，显示极端天气、用电高峰和发电调度正在同时考验电力系统。电网稳定已经从技术问题变成影响通胀、工业生产和民生成本的基础设施问题。",
            "这类事件会让储能、备用容量、需求响应和电网投资重新获得政策优先级。若高温或寒潮频繁出现，电力系统的冗余成本会持续进入企业和家庭账单。",
            "电网压力",
            "电力系统越紧，能源转型和 AI 数据中心扩张的真实约束就越清楚。",
        )
    if has_any(text, ["cerebras", "stock plunges"]):
        return (
            "AI 芯片公司 Cerebras 财报后股价大幅波动，反映市场正在严格审查 AI 硬件公司的利润率、订单质量和增长可持续性。只要估值依赖高增长，任何毛利或收入指引的不确定都会被放大。",
            "这类个股波动有风向标意义：AI 硬件不再只看技术路线，也要看客户集中度、产能安排、价格压力和资本市场融资环境。投资者会继续比较它与 Nvidia、云厂商自研芯片和 ASIC 路线的竞争位置。",
            "财报冲击",
            "AI 芯片赛道正在从“供不应求”叙事进入盈利质量和客户兑现阶段。",
        )
    if has_any(text, ["openai", "custom chip", "broadcom"]):
        return (
            "OpenAI 推进自研芯片并与 Broadcom 等供应链力量绑定，意味着 AI 模型公司正在从买算力转向控制关键算力基础设施。自研芯片不仅是降本问题，也关系到训练、推理、供应保障和议价权。",
            "如果大型模型公司继续向上游延伸，GPU 供应链、云厂商合作关系和芯片设计生态都会被重塑。未来 AI 竞争会越来越像能源和制造业竞争：谁掌握关键基础设施，谁就有更强的长期议价能力。",
            "自研芯片",
            "AI 公司正把算力从外部采购品变成战略资产，芯片供应链会进一步平台化和定制化。",
        )
    if has_any(text, ["chip war", "match act"]) or ("export control" in text and "chip" in text):
        return (
            "欧洲对美国芯片政策的反弹说明半导体已经不只是产业补贴问题，而是盟友之间也会争夺技术规则和供应链主动权。出口管制、补贴、产能落地和本土采购正在交织。",
            "未来芯片战的复杂性在于，各国既需要合作，又想保留本土产业安全边界。企业需要同时面对美国规则、欧洲主权诉求和亚洲制造网络的现实约束。",
            "芯片政策",
            "半导体供应链正在被安全政策重写，跨国企业的合规和产能布局成本会上升。",
        )
    if "nato" in text and "iran" in text:
        return (
            "围绕伊朗冲突的立场分歧正在考验美国与北约盟友的协调能力。安全联盟内部如果在军事行动、情报支持或外交背书上出现裂痕，后续会影响中东风险溢价、能源运输预期和欧洲防务讨论。",
            "这类新闻的重点不是口水仗，而是盟友是否会改变实际行动：包括防务开支、制裁协调、军事部署和能源安全安排。若分歧扩大，市场会重新评估地缘风险的持续时间。",
            "联盟压力",
            "地缘冲突会通过能源价格、防务预算、制裁规则和避险情绪传导到全球市场。",
        )
    if "micron" in text and "profit" in text and ("chip" in text or "ai" in text):
        return (
            "Micron 利润大幅改善，说明 AI 服务器和高带宽存储需求正在把半导体周期重新推向上行。存储芯片过去更容易受价格周期拖累，但 AI 训练和推理需求让高端存储的议价能力变得更重要。",
            "这条新闻的关键数据不只是利润增幅，而是它反映了 AI 基础设施投资正在扩散到 GPU 之外的存储、封装、电力和服务器链条。后续要看数据中心资本开支是否继续支撑订单。",
            "AI 需求",
            "AI 基础设施不是只买 GPU，存储和服务器供应链的利润弹性正在被重新定价。",
        )
    if has_any(text, ["ebola", "congo"]):
        return (
            "刚果埃博拉疫情响应压力上升，公共卫生风险再次提醒市场：低收入地区的医疗资源缺口可能迅速变成区域安全和人道主义问题。疫情若扩散，会影响边境管理、国际援助和当地经济活动。",
            "虽然它未必直接冲击全球市场，但公共卫生事件常常通过人员流动、财政压力和国际组织资源调配产生间接影响。需要关注病例增长、疫苗供应和 WHO/UN 后续行动。",
            "公共卫生",
            "疫情治理能力是国家韧性的一部分，也会影响援助资金、地区稳定和供应链连续性。",
        )
    if has_any(text, ["reinforcement learning", "beneficial models", "graph learning"]):
        return (
            "AI 研究继续围绕强化学习、模型长期收益和复杂图学习推进，说明行业不只在追求更大的模型，也在探索更稳定、更可控、更能适配现实任务的训练方法。",
            "这类研究短期不一定直接改变市场价格，但会影响未来模型安全、企业部署成本和开源生态方向。真正值得跟踪的是这些方法是否能降低训练成本、提升可靠性并进入主流开发框架。",
            "技术路线",
            "AI 竞争不只是参数规模竞争，也包括训练方法、可靠性和落地成本的竞争。",
        )

    if "AI" in categories:
        return (
            f"{source_cn_name(item.source)}更新了一条与 AI 和算力产业相关的重要信息。它被纳入简报，是因为这类变化可能影响模型公司、芯片供应链、云计算资本开支和企业数字化预算。",
            "后续需要关注它是否带来真实订单、成本下降、监管变化或竞争格局调整。AI 新闻最容易被口号放大，判断时要优先看资金流、算力约束和商业化证据。",
            "AI 信号",
            "AI 产业已进入基础设施竞争阶段，模型能力、芯片供给和商业回报需要一起看。",
        )
    if "能源" in categories:
        return (
            f"{source_cn_name(item.source)}更新了一条能源相关信息，涉及供需、价格、电力系统或政策约束。能源新闻的重要性在于，它很容易沿着运输成本、工业成本和居民账单传导。",
            "后续需要关注价格反应、监管表态、企业资本开支和供应链调整。只要能源系统出现紧张，通胀和政策压力往往会重新抬头。",
            "能源传导",
            "能源变化会通过通胀、财政补贴和工业竞争力影响更广泛的经济预期。",
        )
    if "财经" in categories:
        return (
            f"{source_cn_name(item.source)}更新了一条资本市场和企业经营相关信息。它的价值在于可能改变投资者对增长、利润、融资成本或风险偏好的判断。",
            "后续需要看市场价格是否跟随反应，以及企业、监管者或央行是否给出进一步信号。财经新闻不能只看标题，要看它是否改变现金流、利率或风险溢价。",
            "市场信号",
            "如果信息改变盈利、融资或监管预期，资产价格通常会比舆论更快反应。",
        )
    if "科技" in categories:
        return (
            f"{source_cn_name(item.source)}更新了一条关键科技相关信息，可能涉及平台、芯片、网络安全、数据基础设施或科研突破。科技新闻的重点在于它能否改变产业链分工和企业投入节奏。",
            "后续需要关注商业化路径、监管约束、供应链瓶颈和资本开支。真正重要的科技变化通常会同时影响产品路线、成本结构和竞争壁垒。",
            "科技趋势",
            "技术突破只有进入成本、供应链和用户采用，才会变成真正的产业变量。",
        )
    return (
        f"{source_cn_name(item.source)}更新了一条全球政策和风险相关信息，可能影响机构判断、政府决策或市场预期。",
        "后续需要关注官方确认、市场反应和跨境传导。国际新闻的重点不是热闹程度，而是它能否改变规则、成本或风险分布。",
        "全球风险",
        "政策和地缘变化常常通过规则、制裁、贸易和资本流动影响企业与市场。",
    )


def fallback_report(items: list[FeedItem]) -> dict:
    if not items:
        now_label = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
        items = [
            FeedItem(
                title="Public-source collection did not return enough items",
                link="https://yz6953807-cmd.github.io/daily-global-briefing/",
                source="Daily briefing system",
                category="政策",
                summary="The scheduled workflow ran, but public feeds were temporarily unavailable. The page was still refreshed so readers can see the update status.",
                published=datetime.now(timezone.utc),
            )
        ]
        log(f"fallback report has no feed data at {now_label}")

    selected = items[:MAX_ARTICLES]
    source_count = len({source_family(item.source) for item in selected})
    articles = []
    for index, item in enumerate(selected, 1):
        cats = infer_categories(item)
        published = item.published.astimezone(TZ).strftime("%Y-%m-%d %H:%M")
        summary = item.summary or item.title
        title_cn = fallback_cn_title(index, item, cats)
        title_en = f"{index}. {item.title}"
        cn_first, cn_second, readout_label, why_text = fallback_cn_context(item, cats)
        source_cn = source_cn_name(item.source)
        articles.append(
            {
                "title_cn": title_cn,
                "title_en": title_en,
                "tag_cn": zh_category(cats),
                "tag_en": en_category(cats),
                "points": [
                    {"value": source_cn, "value_en": item.source, "cn": "权威公开来源", "en": "public source"},
                    {"value": published.split()[0], "cn": "发布时间", "en": "published date"},
                    {"value": cats[0] if cats else "全球", "cn": "主要主题", "en": "primary theme"},
                ],
                "readouts": [
                    {
                        "label_cn": readout_label,
                        "text_cn": "该条目被选入今日简报，是因为它可能影响市场定价、政策变化、科技基础设施或全球风险传导。",
                        "label_en": "Signal",
                        "text_en": "This item is included because it connects to market pricing, policy change, technology infrastructure, or global risk transmission.",
                    },
                    {
                        "label_cn": "阅读方式",
                        "text_cn": "先看来源、发布时间和影响链条，再判断它是否会改变资产价格、企业决策或政策预期。",
                        "label_en": "How to read it",
                        "text_en": "Read the source, timestamp, and transmission path before judging whether it changes asset prices, corporate decisions, or policy expectations.",
                    },
                ],
                "paragraphs_cn": [
                    f"{source_cn}在 {published} 发布或更新了这条公开信息。{cn_first}",
                    cn_second,
                ],
                "paragraphs_en": [
                    f"{item.source} published or updated this item at {published}: {item.title}. The public summary says: {summary}",
                    "The value of the item is not only the headline, but how it may change expectations. If it touches central banks, fiscal policy, energy, supply chains, AI, chips, or geopolitics, it can still transmit into rates, inflation, corporate capex, trade flows, and risk appetite. Because this is an automated public-source edition, readers should open the original source to verify details and later revisions.",
                ],
                "why_cn": f"为什么重要：{why_text}",
                "why_en": "Why it matters: It may affect market expectations, policy judgment, or supply-chain decisions, especially if it introduces new data, regulatory action, or supply constraints.",
                "watch_cn": "继续观察：原始来源后续更新、相关机构表态、市场价格反应、企业公告和监管细则。",
                "watch_en": "Watch: updates from the original source, official responses, market-price reactions, company disclosures, and regulatory details.",
                "source": source_cn,
                "source_en": item.source,
                "url": item.link,
            }
        )

    return {
        "summary_cn": f"今日简报只纳入发布日期为 {date_window_cn()} 的公开信息，并优先从全球财经媒体、国际新闻机构、官方机构、科技专业源和研究来源中筛选真正可能影响市场、政策和产业方向的重磅消息。",
        "summary_en": f"This briefing only includes public items published or updated on {date_window_en()}, prioritizing globally relevant market, policy, technology, energy, AI, regulatory, and research signals from diverse authoritative sources.",
        "metrics": [
            {"value": str(len(selected)), "cn": "今日入选重点条目", "en": "selected items"},
            {"value": str(source_count), "cn": "覆盖公开来源数量", "en": "public sources covered"},
            {"value": date_window_cn(), "cn": "发布日期硬门槛", "en": "publication-date gate"},
            {"value": "08:30", "cn": "北京时间定时更新", "en": "Beijing scheduled update"},
        ],
        "articles": articles,
        "footnote_cn": f"来源与不确定性：本页由 GitHub Actions 云端任务根据公开 RSS/API 信息自动生成；当前规则只保留 {date_window_cn()} 发布或更新的条目，并对单一来源设置上限。若未配置豆包/方舟密钥，摘要会更偏事实摘录和影响框架。请以原始来源链接和后续官方更新为准。",
        "footnote_en": f"Sources and caveats: This page is generated by a GitHub Actions cloud job from public RSS/API information. The current rule keeps only items published or updated on {date_window_en()} and caps repeated use of a single source. Always verify against original links and later official updates.",
    }


def safe_list(value: list, minimum: int, fallback: list) -> list:
    return value if isinstance(value, list) and len(value) >= minimum else fallback


def normalize_report(report: dict, items: list[FeedItem]) -> dict:
    fallback = fallback_report(items)
    report = report or fallback
    item_by_url = {item.link: item for item in items}
    articles = report.get("articles") if isinstance(report.get("articles"), list) else []
    if item_by_url:
        articles = [article for article in articles if str(article.get("url", "")).strip() in item_by_url]
    if len(articles) < 5:
        return fallback
    report["summary_cn"] = clean_text(report.get("summary_cn") or fallback["summary_cn"], 260)
    report["summary_en"] = clean_text(report.get("summary_en") or fallback["summary_en"], 360)
    report["metrics"] = safe_list(report.get("metrics"), 4, fallback["metrics"])[:4]
    report["articles"] = articles[:MAX_ARTICLES]
    report["footnote_cn"] = clean_text(report.get("footnote_cn") or fallback["footnote_cn"], 500)
    report["footnote_en"] = clean_text(report.get("footnote_en") or fallback["footnote_en"], 700)
    for index, article in enumerate(report["articles"], 1):
        article.setdefault("title_cn", f"{index}. 今日重点")
        article.setdefault("title_en", article["title_cn"])
        if not re.match(r"^\d+\.", str(article["title_cn"])):
            article["title_cn"] = f"{index}. {article['title_cn']}"
        if not re.match(r"^\d+\.", str(article["title_en"])):
            article["title_en"] = f"{index}. {article['title_en']}"
        article["points"] = safe_list(article.get("points"), 1, fallback["articles"][min(index - 1, len(fallback["articles"]) - 1)]["points"])[:3]
        article["readouts"] = safe_list(article.get("readouts"), 1, fallback["articles"][min(index - 1, len(fallback["articles"]) - 1)]["readouts"])[:2]
        article["paragraphs_cn"] = safe_list(article.get("paragraphs_cn"), 1, ["暂无正文。"])[:2]
        article["paragraphs_en"] = safe_list(article.get("paragraphs_en"), 1, article["paragraphs_cn"])[:2]
        article.setdefault("why_cn", "为什么重要：这条信息可能影响政策、市场或产业链预期。")
        article.setdefault("why_en", "Why it matters: This item may affect policy, markets, or supply-chain expectations.")
        article.setdefault("watch_cn", "继续观察：原始来源后续更新和市场反应。")
        article.setdefault("watch_en", "Watch: original-source updates and market reaction.")
        matched_item = item_by_url.get(str(article.get("url", "")).strip())
        raw_source = matched_item.source if matched_item else str(article.get("source") or "Public source")
        article["source_en"] = raw_source
        article["source"] = str(article.get("source_cn") or source_cn_name(raw_source))
        article["url"] = matched_item.link if matched_item else str(article.get("url") or "https://yz6953807-cmd.github.io/daily-global-briefing/")
    return report


def h(text: object) -> str:
    return escape(str(text or ""), quote=True)


def article_html(article: dict) -> str:
    points = "\n".join(
        f'        <div class="point"><b>{h(point.get("value", ""))}</b><span>{h(point.get("cn", ""))}</span></div>'
        for point in article.get("points", [])
    )
    readouts = "\n".join(
        f'        <div><b>{h(readout.get("label_cn", ""))}</b>{h(readout.get("text_cn", ""))}</div>'
        for readout in article.get("readouts", [])
    )
    paragraphs = "\n".join(f"      <p>{h(paragraph)}</p>" for paragraph in article.get("paragraphs_cn", []))
    url = h(article.get("url", ""))
    source = h(article.get("source", "Public source"))
    return f"""    <article>
      <div class="article-top">
        <h2>{h(article.get("title_cn", ""))}</h2>
        <div class="tag">{h(article.get("tag_cn", "全球"))}</div>
      </div>
      <div class="points">
{points}
      </div>
      <div class="readout">
{readouts}
      </div>
{paragraphs}
      <div class="why">{h(article.get("why_cn", ""))}</div>
      <div class="watch"><b>继续观察：</b>{h(str(article.get("watch_cn", "")).replace("继续观察：", ""))}</div>
      <div class="source">来源：<a href="{url}">{source}</a></div>
    </article>"""


def build_body(report: dict) -> str:
    metrics = "\n".join(
        f'      <div class="metric"><strong>{h(metric.get("value", ""))}</strong><span>{h(metric.get("cn", ""))}</span></div>'
        for metric in report["metrics"][:4]
    )
    articles = "\n\n".join(article_html(article) for article in report["articles"])
    count = len(report["articles"])
    return f"""  <header class="wrap">
    <section class="hero">
      <div class="hero-inner">
        <div class="eyebrow">GLOBAL BRIEFING · DAILY INTELLIGENCE</div>
        <h1>今日全球资讯简报</h1>
        <div class="meta">生成日期：{DATE_STR} · 发布时间：仅 {date_window_cn()} 发布或更新</div>
        <div class="summary">{h(report["summary_cn"])}</div>
      </div>
    </section>
    <section class="dashboard" aria-label="今日关键数字">
{metrics}
    </section>
    <section class="briefing-tools" aria-label="简报阅读工具">
      <div class="tool-filter" id="briefingFilters" aria-label="按主题筛选">
        <button type="button" class="is-active" data-filter="all" aria-pressed="true">全部</button>
        <button type="button" data-filter="财经" aria-pressed="false">财经</button>
        <button type="button" data-filter="科技" aria-pressed="false">科技</button>
        <button type="button" data-filter="政策" aria-pressed="false">政策</button>
        <button type="button" data-filter="能源" aria-pressed="false">能源</button>
        <button type="button" data-filter="ai" aria-pressed="false">AI</button>
      </div>
      <div class="font-switch" aria-label="字体模式">
        <button type="button" class="is-active" data-font="cn" aria-pressed="true">中文</button>
        <button type="button" data-font="en" aria-pressed="false">EN</button>
      </div>
      <div class="briefing-count" id="briefingCount" aria-live="polite">{count} 条</div>
    </section>
  </header>

  <main class="wrap">
{articles}
  </main>

  <footer class="wrap">
    <div class="footnote">
      {h(report["footnote_cn"])}
    </div>
    <div class="update-status">{h(status_line_cn())}</div>
  </footer>
"""


def english_copy(report: dict) -> dict:
    return {
        "en": {
            "hero": {
                "eyebrow": "GLOBAL BRIEFING · DAILY INTELLIGENCE",
                "h1": "Daily Global Briefing",
                "meta": f"Generated: {TODAY.strftime('%B %-d, %Y') if sys.platform != 'win32' else TODAY.strftime('%B %d, %Y')} · Publication dates: {date_window_en()} only",
                "summary": report["summary_en"],
            },
            "metrics": [[metric.get("value", ""), metric.get("en", metric.get("cn", ""))] for metric in report["metrics"][:4]],
            "filters": {"all": "All", "财经": "Markets", "科技": "Tech", "政策": "Policy", "能源": "Energy", "ai": "AI"},
            "toggle": {"collapse": "Collapse", "expand": "Expand"},
            "articles": [
                {
                    "title": article.get("title_en", article.get("title_cn", "")),
                    "tag": article.get("tag_en", article.get("tag_cn", "")),
                    "points": [[p.get("value_en", p.get("value", "")), p.get("en", p.get("cn", ""))] for p in article.get("points", [])],
                    "readouts": [[r.get("label_en", r.get("label_cn", "")), r.get("text_en", r.get("text_cn", ""))] for r in article.get("readouts", [])],
                    "paragraphs": article.get("paragraphs_en", article.get("paragraphs_cn", [])),
                    "why": article.get("why_en", article.get("why_cn", "")),
                    "watch": article.get("watch_en", article.get("watch_cn", "")),
                    "source": article.get("source_en", article.get("source", "")),
                    "url": article.get("url", ""),
                }
                for article in report["articles"]
            ],
            "footnote": report["footnote_en"],
            "status": status_line_en(),
        }
    }


def replace_body(html: str, body: str) -> str:
    body_tag = '<body data-font-mode="cn">'
    start = html.index(body_tag) + len(body_tag)
    anchor = '  <div class="briefing-bunny"'
    end = html.index(anchor, start)
    return html[:start] + "\n" + body + html[end:]


def replace_english_copy(html: str, report: dict) -> str:
    start = html.index("      const briefingCopy = ")
    end = html.index("\n\n      function rememberHtml", start)
    js = json.dumps(english_copy(report), ensure_ascii=False, indent=8)
    js = textwrap.indent(js, "      ").lstrip()
    return html[:start] + "      const briefingCopy = " + js + ";\n" + html[end:]


def write_outputs(report: dict, items: list[FeedItem]) -> None:
    index_path = ROOT / "index.html"
    html = index_path.read_text(encoding="utf-8")
    html = replace_body(html, build_body(report))
    html = replace_english_copy(html, report)
    index_path.write_text(html, encoding="utf-8")

    archive_dir = ROOT / "archive"
    archive_dir.mkdir(exist_ok=True)
    (archive_dir / f"{DATE_STR}.html").write_text(html, encoding="utf-8")

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    payload = {
        "generatedAt": RUN_STARTED_AT.isoformat(timespec="seconds"),
        "date": DATE_STR,
        "report": report,
        "sourceItems": item_payload(items),
    }
    (data_dir / "latest-news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / f"{DATE_STR}-news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    status = run_metadata(article_count=len(report["articles"]), source_count=len(items))
    (data_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    images_dir = ROOT / "images"
    today_bg = images_dir / "today-bg.png"
    archive_bg = images_dir / f"{DATE_STR}-bg.png"
    if today_bg.exists() and not archive_bg.exists():
        shutil.copyfile(today_bg, archive_bg)


def main() -> int:
    os.chdir(ROOT)
    items = collect_items()
    report = normalize_report(ask_ark(items), items)
    write_outputs(report, items)
    log(f"briefing updated for {DATE_STR}: {len(report['articles'])} articles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
