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
TODAY = datetime.now(TZ).date()
DATE_STR = TODAY.isoformat()
USER_AGENT = "daily-global-briefing/1.0 (+https://yz6953807-cmd.github.io/daily-global-briefing/)"
ARK_ENDPOINT = os.environ.get("ARK_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
ARK_MODEL = os.environ.get("ARK_MODEL") or "doubao-seed-1-6-250615"


FEEDS = [
    ("The Guardian Business", "https://www.theguardian.com/business/rss", "财经"),
    ("The Guardian Technology", "https://www.theguardian.com/technology/rss", "科技"),
    ("The Guardian Environment", "https://www.theguardian.com/environment/rss", "能源"),
    ("The Guardian Science", "https://www.theguardian.com/science/rss", "科技"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "财经"),
    ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "科技"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "政策"),
    ("TechCrunch", "https://techcrunch.com/feed/", "科技"),
    ("SEC Press Releases", "https://www.sec.gov/news/pressreleases.rss", "财经"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "政策"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "财经"),
    ("ECB", "https://www.ecb.europa.eu/rss/press.html", "财经"),
    ("IMF", "https://www.imf.org/en/News/RSS", "财经"),
    ("Nature", "https://www.nature.com/nature.rss", "科技"),
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
]


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
    if item.source in {"Federal Reserve", "ECB", "IMF", "SEC Press Releases", "Nature"}:
        score += 2.5
    if item.source in {"TechCrunch", "BBC Business", "BBC Technology"}:
        score += 1.5
    return score


def collect_items() -> list[FeedItem]:
    all_items: list[FeedItem] = []
    for source, url, category in FEEDS:
        all_items.extend(parse_feed(source, url, category))
        time.sleep(0.2)

    seen: set[str] = set()
    deduped: list[FeedItem] = []
    for item in all_items:
        key = re.sub(r"[^a-z0-9]+", " ", item.title.lower()).strip()
        key = " ".join(key.split()[:12])
        if key in seen:
            continue
        seen.add(key)
        item.score = score_item(item)
        if item.score > 6:
            deduped.append(item)

    deduped.sort(key=lambda item: (item.score, item.published), reverse=True)
    selected = deduped[:12]
    log(f"collected {len(all_items)} feed items, selected {len(selected)}")
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
        "task": (
            "从这些公开来源条目中筛选 8 条最重要新闻，生成中英文网页日报。"
            "优先全球范围内真正重磅的信息：央行和财政政策、市场和通胀冲击、IPO/上市、并购融资、公司丑闻或监管调查、反垄断、重大诉讼、网络安全泄露、AI/芯片/云/数据中心、能源通道、地缘安全和关键科技突破。"
            "剔除无关痛痒的地方政治直播、体育娱乐、生活方式、职业介绍、软性人物故事和泛泛科普。"
            "中文要专业但易懂，每条两段；英文是对应真实英文版本。"
            "如果条目摘要缺少数据，请用来源、时间、机构、影响链条和观察点补足，不要伪造数字。"
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

    selected = items[:8]
    source_count = len({item.source for item in selected})
    articles = []
    for index, item in enumerate(selected, 1):
        cats = infer_categories(item)
        published = item.published.astimezone(TZ).strftime("%Y-%m-%d %H:%M")
        summary = item.summary or item.title
        title_cn = f"{index}. {item.title}"
        title_en = f"{index}. {item.title}"
        articles.append(
            {
                "title_cn": title_cn,
                "title_en": title_en,
                "tag_cn": zh_category(cats),
                "tag_en": en_category(cats),
                "points": [
                    {"value": item.source, "cn": "权威公开来源", "en": "public source"},
                    {"value": published.split()[0], "cn": "发布时间", "en": "published date"},
                    {"value": cats[0] if cats else "全球", "cn": "主要主题", "en": "primary theme"},
                ],
                "readouts": [
                    {
                        "label_cn": "信息信号",
                        "text_cn": "该条目被选入今日简报，是因为它与市场定价、政策变化、科技基础设施或全球风险传导相关。",
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
                    f"{item.source} 在 {published} 发布或更新了这条信息：{item.title}。公开摘要显示，{summary}",
                    "这条新闻的价值不只在标题，而在它可能改变预期的方式：如果它涉及央行、财政、能源、供应链、AI、芯片或地缘政策，就可能继续传导到利率、通胀、企业资本开支、贸易流向和市场风险偏好。由于这是公开源自动生成版本，后续仍应点击原文核对细节和最新修订。",
                ],
                "paragraphs_en": [
                    f"{item.source} published or updated this item at {published}: {item.title}. The public summary says: {summary}",
                    "The value of the item is not only the headline, but how it may change expectations. If it touches central banks, fiscal policy, energy, supply chains, AI, chips, or geopolitics, it can still transmit into rates, inflation, corporate capex, trade flows, and risk appetite. Because this is an automated public-source edition, readers should open the original source to verify details and later revisions.",
                ],
                "why_cn": "为什么重要：它可能影响市场预期、政策判断或产业链决策，尤其需要关注是否有新的数据、监管动作或供应约束。",
                "why_en": "Why it matters: It may affect market expectations, policy judgment, or supply-chain decisions, especially if it introduces new data, regulatory action, or supply constraints.",
                "watch_cn": "继续观察：原始来源后续更新、相关机构表态、市场价格反应、企业公告和监管细则。",
                "watch_en": "Watch: updates from the original source, official responses, market-price reactions, company disclosures, and regulatory details.",
                "source": item.source,
                "url": item.link,
            }
        )

    return {
        "summary_cn": "今日简报由 GitHub 云端自动任务生成，重点跟踪全球市场、政策、科技、能源和 AI 相关公开信息。当前版本优先保证每天稳定更新；配置豆包密钥后，可进一步提升深度摘要和数据提炼质量。",
        "summary_en": "This briefing was generated by the GitHub cloud scheduler, tracking public updates across markets, policy, technology, energy, and AI. The current edition prioritizes reliable daily publishing; adding a Doubao/Ark secret can improve synthesis depth and data extraction.",
        "metrics": [
            {"value": str(len(selected)), "cn": "今日入选重点条目", "en": "selected items"},
            {"value": str(source_count), "cn": "覆盖公开来源数量", "en": "public sources covered"},
            {"value": DATE_STR, "cn": "云端自动生成日期", "en": "cloud generation date"},
            {"value": "08:30", "cn": "北京时间定时更新", "en": "Beijing scheduled update"},
        ],
        "articles": articles,
        "footnote_cn": "来源与不确定性：本页由 GitHub Actions 云端任务根据公开 RSS/API 信息自动生成；若未配置豆包/方舟密钥，摘要会更偏事实摘录和影响框架。请以原始来源链接和后续官方更新为准。",
        "footnote_en": "Sources and caveats: This page is generated by a GitHub Actions cloud job from public RSS/API information. Without a Doubao/Ark secret, summaries lean more toward factual excerpts and impact framing. Always verify against original links and later official updates.",
    }


def safe_list(value: list, minimum: int, fallback: list) -> list:
    return value if isinstance(value, list) and len(value) >= minimum else fallback


def normalize_report(report: dict, items: list[FeedItem]) -> dict:
    fallback = fallback_report(items)
    report = report or fallback
    articles = report.get("articles") if isinstance(report.get("articles"), list) else []
    if len(articles) < 5:
        return fallback
    report["summary_cn"] = clean_text(report.get("summary_cn") or fallback["summary_cn"], 260)
    report["summary_en"] = clean_text(report.get("summary_en") or fallback["summary_en"], 360)
    report["metrics"] = safe_list(report.get("metrics"), 4, fallback["metrics"])[:4]
    report["articles"] = articles[:8]
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
        article.setdefault("source", "Public source")
        article.setdefault("url", "https://yz6953807-cmd.github.io/daily-global-briefing/")
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
        <div class="meta">生成日期：{DATE_STR} · 覆盖时段：最近 24-72 小时公开信息</div>
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
  </footer>
"""


def english_copy(report: dict) -> dict:
    return {
        "en": {
            "hero": {
                "eyebrow": "GLOBAL BRIEFING · DAILY INTELLIGENCE",
                "h1": "Daily Global Briefing",
                "meta": f"Generated: {TODAY.strftime('%B %-d, %Y') if sys.platform != 'win32' else TODAY.strftime('%B %d, %Y')} · Coverage: public information from the past 24-72 hours",
                "summary": report["summary_en"],
            },
            "metrics": [[metric.get("value", ""), metric.get("en", metric.get("cn", ""))] for metric in report["metrics"][:4]],
            "filters": {"all": "All", "财经": "Markets", "科技": "Tech", "政策": "Policy", "能源": "Energy", "ai": "AI"},
            "toggle": {"collapse": "Collapse", "expand": "Expand"},
            "articles": [
                {
                    "title": article.get("title_en", article.get("title_cn", "")),
                    "tag": article.get("tag_en", article.get("tag_cn", "")),
                    "points": [[p.get("value", ""), p.get("en", p.get("cn", ""))] for p in article.get("points", [])],
                    "readouts": [[r.get("label_en", r.get("label_cn", "")), r.get("text_en", r.get("text_cn", ""))] for r in article.get("readouts", [])],
                    "paragraphs": article.get("paragraphs_en", article.get("paragraphs_cn", [])),
                    "why": article.get("why_en", article.get("why_cn", "")),
                    "watch": article.get("watch_en", article.get("watch_cn", "")),
                }
                for article in report["articles"]
            ],
            "footnote": report["footnote_en"],
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
        "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "date": DATE_STR,
        "report": report,
        "sourceItems": item_payload(items),
    }
    (data_dir / "latest-news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / f"{DATE_STR}-news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

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
