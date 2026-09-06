#!/usr/bin/env python3
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

RSS_PATH = Path(__file__).with_name("rss.xml")
NS = "https://beninwebtv.bj/rss/radar"
ET.register_namespace("bwtv", NS)

CATEGORY_RULES = {
    "Faits divers": ["accident", "incendie", "meurtre", "assassinat", "arrestation", "braquage", "drame", "explosion", "crash", "police"],
    "Justice": ["justice", "tribunal", "procès", "condamné", "prison", "juge", "parquet"],
    "People": ["people", "célébrité", "star", "influenceur", "rappeur", "chanteur", "acteur", "actrice", "mariage", "divorce"],
    "Sport": ["football", "fifa", "caf", "ligue", "championnat", "match", "but", "transfert", "nba", "tennis"],
    "Politique": ["président", "gouvernement", "ministre", "élection", "parlement", "député", "politique", "diplomatie"],
    "Économie": ["économie", "banque", "inflation", "croissance", "finance", "marché", "entreprise", "pib", "dette", "commerce"],
    "Technologie": ["technologie", "intelligence artificielle", "openai", "google", "apple", "microsoft", "meta", "smartphone", "cyber"],
    "Culture": ["musique", "cinéma", "film", "album", "concert", "festival", "série", "artiste"],
    "Insolite": ["insolite", "étrange", "surprenant", "buzz", "viral"],
}

ZONE_RULES = {
    "Bénin": ["bénin", "benin", "cotonou", "porto-novo", "parakou"],
    "Nigeria": ["nigeria", "abuja", "lagos"],
    "Niger": ["niger", "niamey"],
    "Burkina Faso": ["burkina", "ouagadougou"],
    "Mali": ["mali", "bamako"],
    "Togo": ["togo", "lomé", "lome"],
    "Côte d’Ivoire": ["côte d'ivoire", "cote d'ivoire", "abidjan"],
    "Sénégal": ["sénégal", "senegal", "dakar"],
    "France": ["france", "paris", "macron"],
    "États-Unis": ["états-unis", "etats-unis", "washington", "trump"],
    "Russie": ["russie", "moscou", "poutine", "putin"],
    "Ukraine": ["ukraine", "kyiv", "kiev", "zelensky"],
    "Chine": ["chine", "pékin", "pekin", "beijing"],
    "Israël": ["israël", "israel", "netanyahu"],
}

STOPWORDS = {"avec", "dans", "pour", "mais", "plus", "sur", "une", "des", "les", "aux", "est", "sont", "après", "avant", "chez", "contre", "entre", "sans", "selon", "vers", "leur", "leurs", "cette", "ces", "qui", "que", "dont", "comme", "tout", "tous", "son", "ses", "par", "pas", "news", "google"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def infer_category(title, current):
    hay = norm(title + " " + current)
    for category, terms in CATEGORY_RULES.items():
        if any(norm(term) in hay for term in terms):
            return category
    if "google trends" in hay:
        return "Tendance"
    return current or "Actualité"


def infer_zone(title, source):
    hay = norm(title + " " + source)
    for zone, terms in ZONE_RULES.items():
        if any(norm(term) in hay for term in terms):
            return zone
    if any(x in hay for x in ["afrique", "sahel"]):
        return "Afrique"
    return "International"


def keywords(title, category, zone):
    words = re.findall(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9'’-]{2,}", title)
    out, seen = [], set()
    for word in words:
        key = norm(word).strip("'-’")
        if len(key) < 3 or key in STOPWORDS or key in seen or key.isdigit():
            continue
        seen.add(key)
        out.append(word.strip("'’-"))
        if len(out) >= 6:
            break
    for extra in (category, zone):
        if norm(extra) not in seen:
            out.append(extra)
    return ", ".join(out[:8])


def angle(title, category, zone):
    if category == "People":
        return f"Expliquer ce qui fait réagir autour de « {title} », avec les faits confirmés et le contexte de la personnalité concernée."
    if category == "Faits divers":
        return f"Présenter les faits vérifiés autour de « {title} », le bilan disponible et l’état de l’enquête, sans spéculation."
    if category == "Sport":
        return f"Donner l’information clé sur « {title} », puis expliquer les conséquences sportives et ce qu’il faut suivre ensuite."
    if category == "Politique":
        return f"Résumer « {title} », identifier les acteurs et expliquer les conséquences possibles pour {zone}."
    if category == "Économie":
        return f"Expliquer l’impact potentiel de « {title} » sur les ménages, entreprises ou marchés de {zone}."
    if category == "Technologie":
        return f"Expliquer simplement « {title} », ce qui change pour les utilisateurs et l’intérêt pour le public africain."
    return f"Traiter « {title} » sous un angle factuel et rapide, avec contexte, sources et conséquences à retenir pour {zone}."


def extract_score(description):
    m = re.search(r"Score radar:\s*(\d{1,3})/100", description or "")
    return min(100, int(m.group(1))) if m else 60


def set_child(item, tag, value):
    node = item.find(f"{{{NS}}}{tag}")
    if node is None:
        node = ET.SubElement(item, f"{{{NS}}}{tag}")
    node.text = str(value)


def main():
    tree = ET.parse(RSS_PATH)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise SystemExit("RSS channel not found")

    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        current_cat = (item.findtext("category") or "").strip()
        description = (item.findtext("description") or "").strip()
        category = infer_category(title, current_cat)
        zone = infer_zone(title, source)
        score = extract_score(description)
        seo = keywords(title, category, zone)
        editorial = angle(title, category, zone)

        cat_node = item.find("category")
        if cat_node is None:
            cat_node = ET.SubElement(item, "category")
        cat_node.text = category

        set_child(item, "score", score)
        set_child(item, "zone", zone)
        set_child(item, "editorialAngle", editorial)
        set_child(item, "seoKeywords", seo)

    tree.write(RSS_PATH, encoding="utf-8", xml_declaration=True)
    print("Enriched RSS metadata")


if __name__ == "__main__":
    main()
