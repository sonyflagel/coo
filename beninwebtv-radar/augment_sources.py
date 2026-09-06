#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import hashlib
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RSS_PATH = Path(__file__).with_name("rss.xml")
USER_AGENT = "BeninWebTV-Radar/1.1 (+https://beninwebtv.bj)"
MAX_ITEMS = 140

DIRECT_FEEDS = [
    ("RFI", "https://www.rfi.fr/fr/rss", "Actualité", "A"),
    ("RFI Bénin", "https://www.rfi.fr/fr/tag/b%C3%A9nin/rss", "Bénin", "A"),
    ("France 24", "https://www.france24.com/fr/rss", "International", "A"),
    ("BBC Afrique", "https://feeds.bbci.co.uk/afrique/rss.xml", "Afrique", "A"),
    ("Deutsche Welle", "https://rss.dw.com/rdf/rss-fre-all", "International", "A"),
    ("Euronews FR", "https://fr.euronews.com/rss?format=xml", "International", "A"),
    ("Banouto", "https://www.banouto.bj/rss-actualites", "Bénin", "B"),
    ("Bénin Intelligent", "https://beninintelligent.bj/feed/", "Bénin", "B"),
    ("DakarActu", "https://www.dakaractu.com/xml/syndication.rss", "Afrique", "B"),
    ("Africa.com", "https://africa.com/feed", "Afrique", "B"),
    ("BellaNaija", "https://www.bellanaija.com/feed/", "People", "B"),
]

EXTRA_TREND_GEOS = [
    "CI", "GH", "SN", "TG", "NE", "BF", "ML", "CM", "KE", "CD",
    "MA", "DZ", "EG", "DE", "CA", "IN", "BR", "AE"
]

TIER_BASE_SCORE = {"A": 88, "B": 80, "C": 74}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read()


def parse_date(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node, names: tuple[str, ...]) -> str:
    wanted = set(n.lower() for n in names)
    for child in list(node):
        if localname(child.tag) in wanted:
            if localname(child.tag) == "link" and child.attrib.get("href"):
                return child.attrib.get("href", "").strip()
            return (child.text or "").strip()
    return ""


def feed_entries(blob: bytes):
    root = ET.fromstring(blob)
    nodes = [n for n in root.iter() if localname(n.tag) in {"item", "entry"}]
    for node in nodes:
        title = child_text(node, ("title",))
        link = child_text(node, ("link", "guid"))
        desc = child_text(node, ("description", "summary", "content", "encoded"))
        pub = child_text(node, ("pubdate", "date", "published", "updated"))
        if title and link:
            yield title, link, desc, parse_date(pub)


def score_for(tier: str, pub: datetime) -> int:
    now = datetime.now(timezone.utc)
    age_h = max(0.0, (now - pub).total_seconds() / 3600)
    freshness_bonus = 8 if age_h <= 6 else 4 if age_h <= 24 else 0
    stale_penalty = min(20, int(max(0.0, age_h - 24) / 12))
    return max(45, min(100, TIER_BASE_SCORE.get(tier, 72) + freshness_bonus - stale_penalty))


def existing_keys(channel):
    keys = set()
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip().lower()
        link = (item.findtext("link") or "").strip().lower()
        if title:
            keys.add("t:" + re.sub(r"\s+", " ", title))
        if link:
            keys.add("l:" + link)
    return keys


def add_item(channel, title, link, desc, pub, source, category, score, quality):
    if "beninwebtv.bj" in link.lower():
        return
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = link
    ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = "bwtv-ext-" + hashlib.sha1(link.encode("utf-8")).hexdigest()
    ET.SubElement(item, "pubDate").text = email.utils.format_datetime(pub)
    ET.SubElement(item, "category").text = category
    ET.SubElement(item, "source").text = source
    description = re.sub(r"\s+", " ", desc or "").strip()
    description = (description[:900] + "…") if len(description) > 900 else description
    meta = f"Source qualité: {quality} | Score radar: {score}/100"
    ET.SubElement(item, "description").text = f"{description} | {meta}" if description else meta


def add_direct_sources(channel, keys):
    added = 0
    for source, url, category, tier in DIRECT_FEEDS:
        try:
            blob = fetch(url)
            count = 0
            for title, link, desc, pub in feed_entries(blob):
                tkey = "t:" + re.sub(r"\s+", " ", title.lower().strip())
                lkey = "l:" + link.lower().strip()
                if tkey in keys or lkey in keys:
                    continue
                add_item(channel, title, link, desc, pub, source, category, score_for(tier, pub), tier)
                keys.add(tkey)
                keys.add(lkey)
                added += 1
                count += 1
                if count >= 12:
                    break
        except Exception as exc:
            print(f"WARN direct feed {source}: {exc}")
        time.sleep(0.2)
    return added


def add_extra_trends(channel, keys):
    added = 0
    for geo in EXTRA_TREND_GEOS:
        url = f"https://trends.google.com/trending/rss?geo={geo}"
        try:
            count = 0
            for title, link, desc, pub in feed_entries(fetch(url)):
                tkey = "t:" + re.sub(r"\s+", " ", title.lower().strip())
                lkey = "l:" + link.lower().strip()
                if tkey in keys or lkey in keys:
                    continue
                add_item(channel, title, link, desc, pub, f"Google Trends {geo}", "Google Trends", 94, "trend")
                keys.add(tkey)
                keys.add(lkey)
                added += 1
                count += 1
                if count >= 8:
                    break
        except Exception as exc:
            print(f"WARN Google Trends {geo}: {exc}")
        time.sleep(0.15)
    return added


def item_rank(item):
    desc = item.findtext("description") or ""
    m = re.search(r"Score radar:\s*(\d{1,3})/100", desc)
    score = int(m.group(1)) if m else 60
    pub = parse_date(item.findtext("pubDate") or "")
    return score, pub.timestamp()


def trim_and_sort(channel):
    items = list(channel.findall("item"))
    items.sort(key=item_rank, reverse=True)
    for item in items:
        channel.remove(item)
    for item in items[:MAX_ITEMS]:
        channel.append(item)


def main():
    tree = ET.parse(RSS_PATH)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise SystemExit("RSS channel not found")

    keys = existing_keys(channel)
    direct = add_direct_sources(channel, keys)
    trends = add_extra_trends(channel, keys)
    trim_and_sort(channel)
    tree.write(RSS_PATH, encoding="utf-8", xml_declaration=True)
    print(f"Added {direct} direct-source items and {trends} extra trend items")


if __name__ == "__main__":
    main()
