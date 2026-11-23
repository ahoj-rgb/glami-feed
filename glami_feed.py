#!/usr/bin/env python3
"""Glami.sk XML feed for vacice.sk, built only from public e-shop data.

Sources (no login, no API token):
  - Creativesites Google Merchant export (product list, texts, images, links)
  - each product page (sizes, per-size price and availability, composition)
  - ean_map.json (variant EANs from the BASE catalog, GS1 codes)

Usage: python3 glami_feed.py OUTPUT.xml
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
from xml.sax.saxutils import escape

GOOGLE_FEED = "https://www.vacice.sk/084b6fbb10729ed4da8c3d3f5a3ae7c9/googleMerchant_sk_export.xml"
UA = "Mozilla/5.0 (compatible; vacice-glami-feed/1.0)"
HERE = os.path.dirname(os.path.abspath(__file__))
BABY = "Glami.sk | Detské oblečenie a obuv | Detské oblečenie | Oblečenie pre bábätká"
WOMEN = "Glami.sk | Dámske oblečenie a obuv | Dámske oblečenie"

# (SKU prefix, Glami category). First match wins; SKUs matching nothing are left out.
RULES = [
    ("CV-", BABY + " | Baby nočné prádlo"),           # celoročné vaky
    ("ZV-", BABY + " | Baby nočné prádlo"),           # zimné vaky
    ("ZVDR-", BABY + " | Baby nočné prádlo"),
    ("LV-", BABY + " | Baby nočné prádlo"),           # letné vaky
    ("402/", BABY + " | Baby nočné prádlo"),          # Fresh
    ("NBS", BABY + " | Baby sety"),                   # novorodenecké výbavičky
    ("KOS-", BABY + " | Baby nočné prádlo"),          # detské nočné košieľky
    ("DET-SET-", BABY + " | Baby nočné prádlo"),      # detské pyžamká / sety
    ("DET-PYZ-", BABY + " | Baby nočné prádlo"),
    ("DET-BAG-", BABY + " | Baby nohavice"),          # baggy spoďáre
    ("DET-LEG-", BABY + " | Baby nohavice | Dojčenské legíny"),
    ("DB-", BABY + " | Baby body"),
    ("ZDB-", BABY + " | Baby body"),
    ("PO-", BABY + " | Baby spodné prádlo | Baby ponožky"),
    ("ACC-ZUP-", BABY + " | Baby nočné prádlo"),      # detský župan
    ("DAM-DSET-", WOMEN + " | Dámska nočná bielizeň | Dámske pyžamá | Dámske pyžamá s dlhými nohavicami"),
    ("DAM-DPYZ-", WOMEN + " | Dámska nočná bielizeň | Dámske pyžamá | Dámske pyžamá s dlhými nohavicami"),
    ("DAM-KSET-", WOMEN + " | Dámska nočná bielizeň | Dámske pyžamá | Dámske kraťasové pyžamá"),
    ("DAM-KPYZ-", WOMEN + " | Dámska nočná bielizeň | Dámske pyžamá | Dámske kraťasové pyžamá"),
    ("DAMPO-", WOMEN + " | Dámska spodná bielizeň | Dámske ponožky"),
]
EXCLUDE = {"CV-MER-CERFOLK", "CV-MER-MODFOLK"}  # Folk-love: user does not list it on marketplaces

MATERIALS = [  # (pattern, Glami value)
    (r"merino", "merino vlna"), (r"biobavln|bavln", "bavlna"), (r"vln", "vlna"),
    (r"viskóz", "viskóza"), (r"polyester", "polyester"), (r"elastan|spandex", "elastan"),
    (r"tencel|lyocell", "lyocell"), (r"modal", "modal"), (r"polyamid", "polyamid"), (r"hodváb", "hodváb"),
]
SIZE_RE = re.compile(r"^(NEWBORN|NB|UNI|XXS|XS|S|M|L|XL|XXL|XXXL)\b", re.I)


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def tag(block, name):
    m = re.search(r"<%s>(.*?)</%s>" % (re.escape(name), re.escape(name)), block, re.S)
    if not m:
        return ""
    v = m.group(1).strip()
    v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v, flags=re.S)
    return html.unescape(v).strip()


def js_array(page, name):
    m = re.search(name + r"\s*=\s*new Array\((.*?)\);", page, re.S)
    return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)) if m else []


def js_indexed(page, name):
    return {int(i): v for i, v in re.findall(name + r"\[(\d+)\]\s*=\s*'([^']*)'", page)}


def price(txt):
    m = re.search(r"([\d\s]+,\d{2})", txt or "")
    return float(m.group(1).replace(" ", "").replace(",", ".")) if m else None


def composition(page):
    """Return (outer, lining) lists of (material, percent) from the 'Zloženie' box."""
    i = page.find(">Zloženie<")
    if i < 0:
        return [], []
    box = page[i:i + 4000]
    box = box[:box.find("</div>")] if "</div>" in box else box
    lines = [html.unescape(re.sub(r"<[^>]+>", " ", x)) for x in re.findall(r"<p[^>]*>(.*?)</p>", box, re.S)]
    outer, lining = [], []
    for ln in lines:
        target = lining if re.search(r"podšív|vnútor", ln, re.I) else outer
        for pct, word in re.findall(r"(\d{1,3})\s*%\s*([^\d%,;\-–]+)", ln):
            w = word.lower()
            for pat, val in MATERIALS:
                if re.search(pat, w):
                    target.append((val, int(pct)))
                    break
    if not outer and lining:
        outer, lining = lining, []
    return outer, lining


def parse_pcts(text):
    res = []
    for pct, word in re.findall(r"(\d{1,3})\s*%\s*([^\d%,;\-–()]+)", text):
        for pat, val in MATERIALS:
            if re.search(pat, word.lower()):
                if val not in [r[0] for r in res]:
                    res.append((val, int(pct)))
                break
    return res


def composition_any(page, name=""):
    outer, lining = composition(page)
    if outer and sum(p for _, p in outer) in range(95, 106):
        return outer, lining
    d = page.find('class="flypage-desc"')
    if d >= 0:
        txt = html.unescape(re.sub(r"<[^>]+>", " ", page[d:d + 60000]))
        txt = re.sub(r"\s+", " ", txt.replace("\xa0", " "))
        for m in re.finditer(r"Zloženie|Materiál\s*:", txt):
            seg = txt[m.start():m.start() + 300]
            seg = re.split(r"Farba|Upozornenie|Veľkosť|zips|Zips|Ostatní", seg)[0]
            parts = re.split(r"vnútorná vrstva|podšívka", seg, flags=re.I)
            o = parse_pcts(parts[0])
            li = parse_pcts(parts[1]) if len(parts) > 1 else []
            if o and sum(p for _, p in o) in range(95, 106):
                return o, li
    m = re.search(r"param_id_15[^>]*>\s*Materiál\s*:\s*([A-Za-zÁ-ž ]+)", re.sub(r"<[^>]+>", " ", page))
    hint = (m.group(1) if m else "") + " " + name
    for pat, val in MATERIALS:
        if re.search(pat, hint.lower()):
            return [(val, 100)], []
    return [], []


def size_of(title):
    t = re.sub(r"^\s*Veľkosť:\s*", "", title).strip()
    m = SIZE_RE.match(t)
    if m:
        s = m.group(1).upper()
        return ("INT", "XS" if s in ("NB", "NEWBORN") else s), t
    m = re.match(r"(\d{2,3})", t)
    if m:
        return ("EU", m.group(1)), t
    return None, t


def color_of(name):
    parts = [p.strip() for p in re.split(r"\s+-\s+", name)]
    for p in parts[1:]:
        if not re.search(r"TOG|\d|merino|bavln|ZIMN|CELOROČ|BAGGY|KR$", p, re.I):
            return p.lower()
    return ""


def main(out):
    eans = json.load(open(os.path.join(HERE, "ean_map.json"), encoding="utf-8"))
    feed = get(GOOGLE_FEED)
    items = re.findall(r"<item>(.*?)</item>", feed, re.S)
    out_items, skipped = [], []
    for it in items:
        sku = tag(it, "g:id")
        cat = next((c for p, c in RULES if sku.startswith(p)), None)
        if not cat or sku in EXCLUDE:
            continue
        link = tag(it, "link")
        name = re.sub(r"\s+", " ", tag(it, "title"))
        try:
            page = get(link)
        except Exception as e:
            skipped.append((sku, "page error %s" % e))
            continue
        titles = js_array(page, "js_title_list")
        prices = js_array(page, r"(?<!_)js_list")
        avail = js_indexed(page, "shop_product_details_avail_names_list")
        days = js_indexed(page, "shop_product_details_avail_days_list")
        outer, lining = composition_any(page, name)
        if not outer:
            skipped.append((sku, "no composition"))
            continue
        imgs = [tag(it, "g:image_link")] + [html.unescape(x).strip() for x in re.findall(
            r"<g:additional_image_link><!\[CDATA\[(.*?)\]\]></g:additional_image_link>", it)]
        desc = tag(it, "description")
        base_price = price(tag(it, "g:sale_price")) or price(tag(it, "g:price").replace(".", ","))
        variants = []
        if titles:
            for i, t in enumerate(titles):
                variants.append((t, price(prices[i]) if i < len(prices) else base_price, avail.get(i, ""), days.get(i, "")))
        else:
            variants.append(("", base_price, tag(it, "g:availability"), "0"))
        color = color_of(name)
        for t, pr, av, dd in variants:
            if re.search(r"vypredan|out_of_stock", av, re.I) or not pr:
                continue
            if re.search(r"predobjedn|došív", av, re.I):
                delivery = 5  # sewn to order, same handling time as on Allegro
            else:
                delivery = int(dd) if str(dd).isdigit() else 0
            sz, raw = size_of(t) if t else (None, "")
            if t and not sz:
                skipped.append((sku, "size?" + raw))
                continue
            vid = sku + ("-" + sz[1] if sz else "")
            ean = eans.get(sku + "|" + raw) or eans.get(sku + "|" + (sz[1] if sz else ""))
            x = ["<SHOPITEM>", "<ITEM_ID>%s</ITEM_ID>" % escape(vid), "<ITEMGROUP_ID>%s</ITEMGROUP_ID>" % escape(sku),
                 "<PRODUCTNAME>%s</PRODUCTNAME>" % escape(name), "<DESCRIPTION><![CDATA[%s]]></DESCRIPTION>" % desc.replace("]]>", ""),
                 "<URL>%s</URL>" % escape(link)]
            x += ["<IMGURL>%s</IMGURL>" % escape(imgs[0])] + ["<IMGURL_ALTERNATIVE>%s</IMGURL_ALTERNATIVE>" % escape(u) for u in imgs[1:10] if u]
            x += ["<PRICE_VAT>%.2f</PRICE_VAT>" % pr, "<MANUFACTURER>Vačice Sleepwear</MANUFACTURER>",
                  "<CATEGORYTEXT>%s</CATEGORYTEXT>" % escape(cat)]
            if sz:
                x += ["<PARAM><PARAM_NAME>veľkosť</PARAM_NAME><VAL>%s</VAL></PARAM>" % escape(sz[1]),
                      "<PARAM><PARAM_NAME>size_system</PARAM_NAME><VAL>%s</VAL></PARAM>" % sz[0]]
            if color:
                x.append("<PARAM><PARAM_NAME>farba</PARAM_NAME><VAL>%s</VAL></PARAM>" % escape(color))
            for pname, lst in (("materiál", outer), ("materiál podšívky", lining)):
                for mat, pct in lst:
                    x.append("<PARAM><PARAM_NAME>%s</PARAM_NAME><VAL>%s</VAL><PERCENTAGE>%d%%</PERCENTAGE></PARAM>" % (pname, mat, pct))
            x.append("<DELIVERY_DATE>%d</DELIVERY_DATE>" % delivery)
            if ean:
                x.append("<GTIN>%s</GTIN>" % ean.lstrip("0") if len(ean) == 14 else "<GTIN>%s</GTIN>" % ean)
            x.append("</SHOPITEM>")
            out_items.append("\n".join(x))
        time.sleep(0.3)
    if len(out_items) < 50:
        sys.exit("Only %d items, refusing to overwrite the feed" % len(out_items))
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<SHOP>\n' + "\n".join(out_items) + "\n</SHOP>\n")
    print("items:", len(out_items))
    for s in skipped:
        print("skipped:", *s)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "glami-sk.xml")
