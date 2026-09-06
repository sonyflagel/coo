#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import hashlib
import html
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "BeninWebTV-Radar/1.0 (+https://beninwebtv.bj)"
OUTPUT = Path(__file__).with_name("rss.xml")
MAX_ITEMS = 80

# Tendances Google : Bénin + grands marchés francophones/internationaux.
TREND_GEOS = ["BJ", "FR", "US", "GB", "NG", "ZA"]

# Requêtes Google News ciblant les verticales éditoriales de BeninWebTV.
NEWS_QUERIES = [
    "Bénin",
    "Afrique",
    "Afrique de l'Ouest",
    "Sahel",
    "politique Afrique",
    "économie Afrique",
    "football Afrique",
    "people Afrique",
    "célébrité Afrique",
    "musique Afrique",
    "cinéma Afrique",
    "influenceur Afrique",
    "faits divers Afrique",
    "justice Afrique",
    "accident Afrique",
    "insolite Afrique",
    "breaking news",
    "international",
    "États-Unis",
    "Europe",
    "Moyen-Orient",
    "Asie",
    "technologie",
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read()


def text(node, tag: str) -> str:
    el = node.find(tag)
    return (el.text or "").strip() if el is not None else ""


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def add_items_from_feed(url: str, source_label: str, category: str, out: list[dict]):
    try:
        root = ET.fromstring(fetch(url))
    except Exception as exc:
        print(f"WARN {source_label}: {exc}")
        return

    for item in root.findall(".//item"):
        title = text(item, "title")
        link = text(item, "link")
        description = text(item, "description")
        pub = text(item, "pubDate")
        if not title or not link:
            continue
        out.append({
            "title": title,
            "link": link,
            "description": description,
            "pub": parse_date(pub),
            "source": source_label,
            "category": category,
        })


def google_news_url(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=fr&gl=BJ&ceid=BJ:fr"


def trend_url(geo: str) -> str:
    return f"https://trends.google.com/trending/rss?geo={geo}"


def dedupe_and_rank(items: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    seen = set()
    ranked = []
    for item in sorted(items, key=lambda x: x["pub"], reverse=True):
        key = hashlib.sha1((item["title"].lower().strip() + "|" + item["link"]).encode("utf-8")).hexdigest()
        title_key = " ".join(item["title"].lower().split())
        if key in seen or title_key in seen:
            continue
        seen.add(key)
        seen.add(title_key)
        age_h = max(0.0, (now - item["pub"]).total_seconds() / 3600)
        freshness = max(0, 100 - int(age_h * 3))
        trend_bonus = 15 if item["category"] == "Google Trends" else 0
        benin_bonus = 10 if "bénin" in item["title"].lower() or "benin" in item["title"].lower() else 0
        item["score"] = min(100, freshness + trend_bonus + benin_bonus)
        ranked.append(item)
    ranked.sort(key=lambda x: (x["score"], x["pub"]), reverse=True)
    return ranked[:MAX_ITEMS]


def xml_escape(value: str) -> str:
    return html.escape(value or "", quote=False)


def build_rss(items: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        '<title>BeninWebTV — Radar éditorial</title>',
        '<link>https://beninwebtv.bj/</link>',
        '<description>Radar automatique: Google Trends + Google News/RSS, Bénin, Afrique et international.</description>',
        '<language>fr</language>',
        f'<lastBuildDate>{email.utils.format_datetime(now)}</lastBuildDate>',
        '<generator>BeninWebTV Radar</generator>',
        '<atom:link href="https://raw.githubusercontent.com/sonyflagel/coo/main/beninwebtv-radar/rss.xml" rel="self" type="application/rss+xml" />',
    ]

    for item in items:
        guid = hashlib.sha1(item["link"].encode("utf-8")).hexdigest()
        desc = item["description"] or f"Source: {item['source']} — Score radar: {item['score']}/100"
        parts.extend([
            '<item>',
            f'<title>{xml_escape(item["title"])}</title>',
            f'<link>{xml_escape(item["link"])}</link>',
            f'<guid isPermaLink="false">bwtv-{guid}</guid>',
            f'<pubDate>{email.utils.format_datetime(item["pub"])}</pubDate>',
            f'<category>{xml_escape(item["category"])}</category>',
            f'<source>{xml_escape(item["source"])}</source>',
            f'<description>{xml_escape(desc)} | Score radar: {item["score"]}/100</description>',
            '</item>',
        ])

    parts.extend(['</channel>', '</rss>'])
    return "\n".join(parts) + "\n"


def main():
    items = []

    for geo in TREND_GEOS:
        add_items_from_feed(trend_url(geo), f"Google Trends {geo}", "Google Trends", items)
        time.sleep(0.4)

    for query in NEWS_QUERIES:
        add_items_from_feed(google_news_url(query), f"Google News: {query}", query, items)
        time.sleep(0.25)

    ranked = dedupe_and_rank(items)
    OUTPUT.write_text(build_rss(ranked), encoding="utf-8")
    print(f"Wrote {len(ranked)} items to {OUTPUT}")


if __name__ == "__main__":
    main()
