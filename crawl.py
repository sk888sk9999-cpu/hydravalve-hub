#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "sources.json"
OUT_FILE = ROOT / "data" / "catalog.json"
USER_AGENT = "HydraValveHub/1.0 (+GitHub Pages catalog indexer; respectful crawler)"
MAX_HTML_BYTES = 3 * 1024 * 1024
MAX_PDF_BYTES = 25 * 1024 * 1024
REQUEST_TIMEOUT = 20
SLEEP_SECONDS = 1.0

VALVE_KEYWORDS = {
    "방향제어": ["directional control valve", "directional valve", "solenoid valve", "4/2", "4/3"],
    "압력제어": ["pressure control valve", "relief valve", "reducing valve", "sequence valve"],
    "유량제어": ["flow control valve", "flow regulator", "throttle valve", "needle valve"],
    "체크": ["check valve", "non-return valve"],
    "카운터밸런스/로드홀딩": ["counterbalance", "load holding", "overcenter", "over-centre"],
    "비례/서보": ["proportional valve", "servo valve", "electro-hydraulic"],
    "카트리지": ["cartridge valve", "screw-in cartridge", "sae cavity"],
    "모듈러": ["modular valve", "sandwich valve"],
}

MODEL_RE = re.compile(r"\b(?=[A-Z0-9][A-Z0-9._/+\-]{2,24}\b)(?=[A-Z0-9._/+\-]*[A-Z])(?=[A-Z0-9._/+\-]*\d)[A-Z0-9][A-Z0-9._/+\-]{2,24}\b")
PRESSURE_RE = re.compile(r"\b(\d{2,4}(?:\.\d+)?)\s*(bar|psi)\b", re.I)
FLOW_RE = re.compile(r"\b(\d{1,4}(?:\.\d+)?)\s*(l\s*/\s*min|lpm|gpm)\b", re.I)
VOLT_RE = re.compile(r"\b(12|24|48|110|120|220|230)\s*v(?:olt)?\s*(dc|ac)?\b", re.I)
SIZE_RE = re.compile(r"\b(?:NG\s?\d{1,2}|CETOP\s?\d{1,2}|D0[2-8]|ISO\s?4401[^,;\n]{0,25})\b", re.I)
PORT_RE = re.compile(r"\b(?:G\s?\d/?\d|M\d{1,2}x\d(?:\.\d+)?|\d{1,2}/\d{1,2}-\d{1,2}\s*UNF|SAE[-\s]?(?:0?\d{1,2})|C-\d{1,2}-\d)\b", re.I)

SEED_DOCS = [
    {
        "brand": "ARGO-HYTOS", "title": "RPR3-04 / RPR3-06 directional control valves", "url": "https://www.argo-hytos.com/products/valves/directional-control-valves.html?v=1.0.23",
        "text": "RPR3-04 4/2 and 4/3 directional control valve Q max 30 l/min P max 320 bar DN04 D02 HA 4018. RPR3-06 Q max 80 l/min P max 350 bar DN06 D03 HA 4004.", "source_type": "official_web"
    },
    {
        "brand": "ARGO-HYTOS", "title": "ST21A-B2 flow control cartridge valve", "url": "https://www.argo-hytos.com/products/valves/flow-control-valves/vso1-04r-1.html",
        "text": "ST21A-B2 needle restrictor flow control cartridge valve Q max 140 l/min P max 350 bar C-10-2 7/8-14 UNF datasheet HA 5134.", "source_type": "official_web"
    },
    {
        "brand": "VALVOLE ITALIA", "title": "Load holding / counterbalance valve catalog", "url": "https://www.valvoleitalia.it/catalogo/",
        "text": "Load Holding Valves Check Valves Relief Valves Sequence Valves Pressure Reducing Valves. Cavities I08 I10 I12 I16 SAE08 SAE10 SAE12 SAE16 SAE20 T11A T17A T19A T21A. Capacity 1.5 Lpm to 480 Lpm. Pilot ratios 1:1 2:1 3:1 4:1 5:1 7.5:1 8:1 10:1 13:1 15:1.", "source_type": "official_web"
    },
    {
        "brand": "Walvoil", "title": "Compact Hydraulics SAE cavity cartridge valves", "url": "https://www.walvoil.com/catalogs-and-documentation-download?idFamDownload=10",
        "text": "SAE CAVITY CARTRIDGES VALVES pressure control valves pressure relief valves MC10MV MC12A MC10M datasheets and catalogs.", "source_type": "official_web"
    },
    {
        "brand": "Walvoil", "title": "Directional valves catalogs", "url": "https://www.walvoil.com/catalogs-and-documentation-download?idFamDownload=60",
        "text": "Directional Valves monoblock valves SDM080 SDM110 SDM081 SD4 SD5 SDM100 SD11 SDM140 DLM140 SD14 SD18 M45 M50 catalogs.", "source_type": "official_web"
    },
    {
        "brand": "Nachi", "title": "NACHI Standard Hydraulic Equipment valve index", "url": "https://www.nachi-fujikoshi.co.jp/eng/web/hydraulic/index.html",
        "text": "NACHI Hydraulic Valves Modular Valves G01 G03 G04 OR ORO ORD OG OGB OGS OQ OCQ OW OY OCY OF OCF OC OCV Solenoid Valve Pressure Control Valve Flow Control Valve Direction Control Valves Electro-hydraulic control Valve Hydro-logic Valve.", "source_type": "official_web"
    },
    {
        "brand": "Parker", "title": "Hydraulic Valve Systems Central catalogs", "url": "https://discover.parker.com/hvscentral-catalogs",
        "text": "Industrial Hydraulic Valves MSG14-2500 Directional Controls Pressure Controls Sandwich Subplates Manifolds. Proportional Directional and Pressure Control Valves Servovalves MSG14-2550. Threaded Cartridge Valve Product Offerings MSG15-3504.", "source_type": "official_web"
    },
    {
        "brand": "Yuken", "title": "Hydraulic Equipment catalogue", "url": "https://www.yuken.co.jp/en/catalog_cad/openpg/opg",
        "text": "Hydraulic Equipment Pressure Controls Flow Controls Directional Controls Modules Logic Valves Proportional Electro-Hydraulic Controls Servo Valves. DSG-005 DSG-007 DSG-01 DSG-03 solenoid directional control valve series including D24 variants, catalog data sheet CAD.", "source_type": "official_web"
    },
    {
        "brand": "Danfoss", "title": "Power Solutions hydraulic valves", "url": "https://powersource.danfoss.com/",
        "text": "Hydraulic valves Cartridge valves Directional control valves Hydraulic integrated circuit HIC Industrial valves Sub-system valves. Search by part number and document finder.", "source_type": "official_web"
    },
    {
        "brand": "HAWE", "title": "HAWE hydraulic valve products", "url": "https://www.hawe.com/en-us/products/",
        "text": "Hydraulic valves high-pressure hydraulics pressure control valves sequence valves check valves flow control valves load-holding valve CLHV product finder data sheets.", "source_type": "official_web"
    },
    {
        "brand": "HYDAC", "title": "HYDAC catalog - valves", "url": "https://catalog.hydac.com/",
        "text": "HYDAC product catalog Valves hydraulic valves search by specification pressure flow cartridge products.", "source_type": "official_web"
    },
    {
        "brand": "Bosch Rexroth", "title": "Bosch Rexroth data sheets and catalogs", "url": "https://www.boschrexroth.com/ko/kr/downloads/data-sheets/",
        "text": "Bosch Rexroth hydraulic data sheets catalogs search by material number product name document edition number hydraulic valves WE6 4WE.", "source_type": "official_web"
    },
    {
        "brand": "Bucher Hydraulics", "title": "Valves and control block solutions", "url": "https://www.bucherhydraulics.com/en/products",
        "text": "Bucher Hydraulics valves and control block solutions hydraulic products pumps motors valves cylinders power units electronics system solutions.", "source_type": "official_web"
    },
    {
        "brand": "Sun Hydraulics", "title": "Sun Hydraulics products", "url": "https://www.sunhydraulics.com/products",
        "text": "Sun Hydraulics hydraulic cartridge valves relief valves sequence valves check valves counterbalance valves flow control directional and proportional valves.", "source_type": "official_web"
    },
    {
        "brand": "Tokyo Keiki", "title": "Tokyo Keiki hydraulic products", "url": "https://www.tokyokeiki.jp/e/products/hyd/",
        "text": "Tokyo Keiki hydraulic valves directional control pressure control flow control proportional valves DG4V.", "source_type": "official_web"
    },
    {
        "brand": "ATOS", "title": "ATOS hydraulic products", "url": "https://www.atos.com/",
        "text": "ATOS hydraulic valves directional proportional servo pressure flow controls electrohydraulics.", "source_type": "official_web"
    }
]


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or " ").strip()


def domain_allowed(url: str, domains):
    host = (urlparse(url).hostname or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)


def looks_relevant(url: str, text: str, keywords):
    hay = (url + " " + text).lower()
    keep = ["valve", "hydraulic", "catalog", "datasheet", "data-sheet", "download", "product", "pdf", "카탈로그"]
    return any(k in hay for k in keep + [k.lower() for k in keywords])


def robots_ok(session, url, cache):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in cache:
        rp = RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
            cache[base] = rp
        except Exception:
            cache[base] = None
    rp = cache[base]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def fetch(session, url):
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        limit = MAX_PDF_BYTES if ("pdf" in ctype or r.url.lower().endswith(".pdf")) else MAX_HTML_BYTES
        chunks, total = [], 0
        for chunk in r.iter_content(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > limit:
                raise ValueError("response too large")
            chunks.append(chunk)
        return r.url, ctype, b"".join(chunks)
    except Exception:
        return None, None, None


def pdf_text(data):
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:250]:
            pages.append(page.extract_text() or "")
        return normalize_space("\n".join(pages))
    except Exception:
        return ""


def html_text_and_links(base_url, data):
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = normalize_space(soup.title.get_text(" ", strip=True) if soup.title else "")
    text = normalize_space(soup.get_text(" ", strip=True))
    links = []
    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(base_url, a["href"]))[0]
        label = normalize_space(a.get_text(" ", strip=True))
        links.append((href, label))
    return title, text, links


def detect_categories(text):
    low = text.lower()
    out = []
    for cat, words in VALVE_KEYWORDS.items():
        if any(w in low for w in words):
            out.append(cat)
    return out or ["기타"]


def unique_matches(regex, text, limit=80):
    vals = []
    for m in regex.finditer(text):
        v = normalize_space(m.group(0)).upper()
        if v not in vals:
            vals.append(v)
        if len(vals) >= limit:
            break
    return vals


def model_candidates(text, limit=150):
    vals = []
    blacklist = {"HTTP", "HTTPS", "PDF", "ISO", "PSI", "LPM", "GPM", "VOLT", "VALVE", "FLOW", "PRESSURE"}
    for m in MODEL_RE.finditer(text.upper()):
        v = m.group(0).strip(".-_/+")
        if len(v) < 3 or v in blacklist or v.isdigit():
            continue
        if v not in vals:
            vals.append(v)
        if len(vals) >= limit:
            break
    return vals


def make_record(brand, title, url, text, source_type):
    clean = normalize_space(text)
    models = model_candidates(clean)
    fields = {
        "pressure": unique_matches(PRESSURE_RE, clean, 20),
        "flow": unique_matches(FLOW_RE, clean, 20),
        "voltage": unique_matches(VOLT_RE, clean, 20),
        "size": unique_matches(SIZE_RE, clean, 20),
        "port": unique_matches(PORT_RE, clean, 20),
    }
    cats = detect_categories(clean + " " + title)
    digest = hashlib.sha1((brand + "|" + url).encode()).hexdigest()[:14]
    search_text = normalize_space(" ".join([brand, title, clean[:60000], " ".join(models), " ".join(sum(fields.values(), [])), " ".join(cats)]))
    return {
        "id": digest,
        "brand": brand,
        "title": title or url.rsplit("/", 1)[-1] or brand,
        "url": url,
        "source_type": source_type,
        "categories": cats,
        "models": models,
        "specs": fields,
        "excerpt": clean[:700],
        "search_text": search_text,
    }


def crawl_brand(session, brand_cfg, max_pages, robots_cache):
    brand = brand_cfg["name"]
    domains = brand_cfg["domains"]
    keywords = brand_cfg.get("keywords", [])
    queue = deque((u, 0) for u in brand_cfg["start_urls"])
    seen, docs = set(), []
    while queue and len(seen) < max_pages:
        url, depth = queue.popleft()
        if url in seen or not domain_allowed(url, domains):
            continue
        seen.add(url)
        if not robots_ok(session, url, robots_cache):
            continue
        final_url, ctype, data = fetch(session, url)
        time.sleep(SLEEP_SECONDS)
        if not data:
            continue
        final_url = final_url or url
        is_pdf = "pdf" in (ctype or "") or final_url.lower().split("?")[0].endswith(".pdf")
        if is_pdf:
            text = pdf_text(data)
            if text and looks_relevant(final_url, text[:3000], keywords):
                docs.append(make_record(brand, final_url.rsplit("/", 1)[-1], final_url, text, "official_pdf"))
            continue
        title, text, links = html_text_and_links(final_url, data)
        if text and looks_relevant(final_url, title + " " + text[:3000], keywords):
            docs.append(make_record(brand, title, final_url, text, "official_web"))
        if depth < 2:
            ranked = []
            for href, label in links:
                if not href.startswith(("http://", "https://")) or not domain_allowed(href, domains):
                    continue
                if looks_relevant(href, label, keywords):
                    score = sum(k in (href + " " + label).lower() for k in ["pdf", "valve", "hydraulic", "catalog", "datasheet", "product"])
                    ranked.append((score, href))
            for _, href in sorted(set(ranked), reverse=True)[:20]:
                if href not in seen:
                    queue.append((href, depth + 1))
    return docs


def dedupe(records):
    out, seen = [], set()
    for r in records:
        key = (r["brand"].lower(), r["url"].split("#")[0])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages-per-brand", type=int, default=18)
    ap.add_argument("--seed-only", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    records = [make_record(d["brand"], d["title"], d["url"], d["text"], d["source_type"]) for d in SEED_DOCS]
    errors = []
    if not args.seed_only:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8,ko;q=0.5"})
        robots_cache = {}
        for brand in cfg["brands"]:
            try:
                records.extend(crawl_brand(session, brand, max(1, args.max_pages_per_brand), robots_cache))
            except Exception as e:
                errors.append({"brand": brand["name"], "error": str(e)[:200]})

    records = dedupe(records)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brand_count": len(cfg["brands"]),
        "document_count": len(records),
        "brands": [b["name"] for b in cfg["brands"]],
        "errors": errors,
        "documents": records,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(records)} records to {OUT_FILE}")


if __name__ == "__main__":
    main()
