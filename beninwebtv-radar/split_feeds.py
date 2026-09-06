#!/usr/bin/env python3
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

BASE = Path(__file__).parent
INPUT = BASE / "rss.xml"
NS_BWTV = "https://beninwebtv.bj/rss/radar"
NS_ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("bwtv", NS_BWTV)
ET.register_namespace("atom", NS_ATOM)

FEEDS = {
    "benin.xml": {
        "title": "BeninWebTV — Bénin",
        "description": "Actualités et tendances du Bénin sélectionnées par le radar BeninWebTV.",
        "match": lambda item: zone(item) == "Bénin" or contains(item, ["bénin", "benin", "cotonou", "porto-novo", "parakou"]),
    },
    "international.xml": {
        "title": "BeninWebTV — International",
        "description": "Actualités et tendances internationales sélectionnées par le radar BeninWebTV.",
        "match": lambda item: zone(item) != "Bénin",
    },
    "people.xml": {
        "title": "BeninWebTV — People",
        "description": "People, célébrités, musique, cinéma, influenceurs et divertissement.",
        "match": lambda item: category(item) in {"People", "Culture"} or contains(item, ["people", "célébrité", "star", "influenceur", "rappeur", "chanteur", "acteur", "actrice", "musique", "cinéma"]),
    },
    "faits-divers.xml": {
        "title": "BeninWebTV — Faits divers",
        "description": "Faits divers, justice, accidents, incidents et insolite.",
        "match": lambda item: category(item) in {"Faits divers", "Justice", "Insolite"} or contains(item, ["accident", "incendie", "meurtre", "assassinat", "arrestation", "braquage", "drame", "explosion", "crash", "police", "justice", "tribunal", "procès"]),
    },
    "sport.xml": {
        "title": "BeninWebTV — Sport",
        "description": "Football et autres actualités sportives sélectionnées par le radar BeninWebTV.",
        "match": lambda item: category(item) == "Sport" or contains(item, ["football", "fifa", "caf", "match", "ligue", "championnat", "transfert", "nba", "tennis"]),
    },
}


def text(item, tag):
    return (item.findtext(tag) or "").strip()


def category(item):
    return text(item, "category")


def zone(item):
    return (item.findtext(f"{{{NS_BWTV}}}zone") or "").strip()


def contains(item, terms):
    hay = " ".join([
        text(item, "title"),
        text(item, "description"),
        text(item, "category"),
        zone(item),
    ]).lower()
    return any(term.lower() in hay for term in terms)


def clone_channel_metadata(source_channel, title, description, self_url):
    channel = ET.Element("channel")
    for child in list(source_channel):
        if child.tag == "item":
            continue
        if child.tag == "title":
            node = ET.SubElement(channel, "title")
            node.text = title
        elif child.tag == "description":
            node = ET.SubElement(channel, "description")
            node.text = description
        elif child.tag == f"{{{NS_ATOM}}}link":
            node = ET.SubElement(channel, f"{{{NS_ATOM}}}link")
            node.set("href", self_url)
            node.set("rel", "self")
            node.set("type", "application/rss+xml")
        else:
            channel.append(deepcopy(child))
    return channel


def write_feed(filename, spec, source_channel):
    self_url = f"https://raw.githubusercontent.com/sonyflagel/coo/main/beninwebtv-radar/{filename}"
    rss = ET.Element("rss", {"version": "2.0"})
    channel = clone_channel_metadata(source_channel, spec["title"], spec["description"], self_url)
    rss.append(channel)

    selected = [item for item in source_channel.findall("item") if spec["match"](item)]
    selected.sort(key=lambda item: int((item.findtext(f"{{{NS_BWTV}}}score") or "0").strip() or 0), reverse=True)
    for item in selected[:80]:
        channel.append(deepcopy(item))

    ET.ElementTree(rss).write(BASE / filename, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {len(selected[:80])} items to {filename}")


def main():
    tree = ET.parse(INPUT)
    root = tree.getroot()
    source_channel = root.find("channel")
    if source_channel is None:
        raise SystemExit("RSS channel not found")

    for filename, spec in FEEDS.items():
        write_feed(filename, spec, source_channel)


if __name__ == "__main__":
    main()
