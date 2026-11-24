#!/usr/bin/env python3
"""Heureka.sk XML feed for vacice.sk, converted from the Glami feed (same data source).

Usage: python3 heureka_feed.py glami-sk.xml heureka-sk.xml
Material is written without percentages (Heureka has no PERCENTAGE tag).
"""
import re
import sys
from xml.sax.saxutils import escape

H = "Heureka.sk | "
KIDS = H + "Oblečenie, obuv a doplnky | Detské oblečenie | "
BABY = KIDS + "Dojčenské oblečenie | "
WOMEN = H + "Oblečenie, obuv a doplnky | Dámske oblečenie | "
BAGS = H + "Detský tovar | Vybavenie detskej izby | Detské spacie vaky a zavinovačky"

RULES = [  # (ITEMGROUP_ID prefix, Heureka category); first match wins
    ("CV-", BAGS), ("ZV-", BAGS), ("ZVDR-", BAGS), ("LV-", BAGS), ("402/", BAGS),
    ("NBS", BABY + "Dojčenské súpravy"),
    ("KOS-", KIDS + "Detská nočná bielizeň a župany | Detské nočné košieľky"),
    ("DET-SET-", KIDS + "Detská nočná bielizeň a župany | Detské pyžamá"),
    ("DET-PYZ-", KIDS + "Detská nočná bielizeň a župany | Detské pyžamá"),
    ("DET-BAG-", KIDS + "Detské nohavice | Detské klasické nohavice"),
    ("DET-LEG-", KIDS + "Detské nohavice | Detské legíny"),
    ("DB-", BABY + "Dojčenské body"), ("ZDB-", BABY + "Dojčenské body"),
    ("PO-", KIDS + "Detské ponožky a pančuchy | Detské ponožky"),
    ("ACC-ZUP-", KIDS + "Detská nočná bielizeň a župany | Detské župany"),
    ("DAM-DSET-", WOMEN + "Dámska nočná bielizeň a župany | Dámske pyžamá"),
    ("DAM-DPYZ-", WOMEN + "Dámska nočná bielizeň a župany | Dámske pyžamá"),
    ("DAM-KSET-", WOMEN + "Dámska nočná bielizeň a župany | Dámske pyžamá"),
    ("DAM-KPYZ-", WOMEN + "Dámska nočná bielizeň a župany | Dámske pyžamá"),
    ("DAMPO-", WOMEN + "Dámska spodná bielizeň | Dámske ponožky"),
]
PARAM_NAMES = {"veľkosť": "Veľkosť", "farba": "Farba", "materiál": "Materiál", "materiál podšívky": "Materiál podšívky"}


def conv(item):
    grp = re.search(r"<ITEMGROUP_ID>(.*?)</ITEMGROUP_ID>", item).group(1)
    cat = next((c for p, c in RULES if grp.startswith(p)), None)
    if not cat:
        return None
    item = re.sub(r"<CATEGORYTEXT>.*?</CATEGORYTEXT>", "<CATEGORYTEXT>%s</CATEGORYTEXT>" % escape(cat), item)
    item = re.sub(r"<GTIN>(.*?)</GTIN>", lambda m: "<EAN>%s</EAN>" % m.group(1).zfill(13), item)
    # Heureka IDs: only letters, digits, - and _ (max 36)
    for t_ in ("ITEM_ID", "ITEMGROUP_ID"):
        item = re.sub(r"<%s>(.*?)</%s>" % (t_, t_), lambda m: "<%s>%s</%s>" % (t_, re.sub(r"[^A-Za-z0-9_-]", "-", m.group(1))[:36], t_), item)
    item = re.sub(r"<URL>(.*?)</URL>", lambda m: "<URL>%s%sutm_source=heureka&amp;utm_medium=cpc&amp;utm_campaign=heureka-sk</URL>" % (m.group(1), "&amp;" if "?" in m.group(1) else "?"), item)
    size = re.search(r"<PARAM_NAME>veľkosť</PARAM_NAME><VAL>(.*?)</VAL>", item)
    name = re.search(r"<PRODUCTNAME>(.*?)</PRODUCTNAME>", item).group(1)
    full = "Vačice " + name + (" - veľkosť " + size.group(1) if size else "")
    item = item.replace("<PRODUCTNAME>%s</PRODUCTNAME>" % name, "<PRODUCTNAME>%s</PRODUCTNAME>\n<PRODUCT>%s</PRODUCT>" % (full, full), 1)
    params, seen = [], set()
    for name, val in re.findall(r"<PARAM><PARAM_NAME>(.*?)</PARAM_NAME><VAL>(.*?)</VAL>(?:<PERCENTAGE>.*?</PERCENTAGE>)?</PARAM>", item):
        if name not in PARAM_NAMES or (name, val) in seen:
            continue
        seen.add((name, val))
        params.append("<PARAM><PARAM_NAME>%s</PARAM_NAME><VAL>%s</VAL></PARAM>" % (PARAM_NAMES[name], val))
    item = re.sub(r"\n?<PARAM>.*?</PARAM>", "", item)
    # web says "Nie je skladom, ušijeme do 3 dní" for made-to-order sizes
    item = item.replace("<DELIVERY_DATE>5</DELIVERY_DATE>", "<DELIVERY_DATE>3</DELIVERY_DATE>")
    return item.replace("<DELIVERY_DATE>", "\n".join(params) + "\n<DELIVERY_DATE>", 1)


def main(src, out):
    x = open(src, encoding="utf-8").read()
    items = [c for c in (conv(i) for i in re.findall(r"<SHOPITEM>.*?</SHOPITEM>", x, re.S)) if c]
    if len(items) < 50:
        sys.exit("Only %d items, refusing to overwrite the feed" % len(items))
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<SHOP>\n' + "\n".join(items) + "\n</SHOP>\n")
    print("heureka items:", len(items))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "glami-sk.xml", sys.argv[2] if len(sys.argv) > 2 else "heureka-sk.xml")
