"""Exact standard-taxonomy facts from dated SEC submissions.

No custom-tag guesses, dimensional segment totals, unit mixing or estimates.
The resulting facts pass through the original scoring and period rules.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date

from lxml import etree, html

from .net_edge import moment
from .net_edge_evidence import ALIASES, FLOWS

TAGS = {namespace+":"+tag: metric for metric, tags in ALIASES.items()
        for tag in tags for namespace in ("us-gaap", "ifrs-full", "dei")}


def document_bodies(raw, *, prose=False):
    """Never interpret encoded graphic payloads or XBRL linkbases as prose."""
    blocks = re.finditer(r"<DOCUMENT>(.*?)</DOCUMENT>", raw, re.I | re.S)
    any_block = False
    for match in blocks:
        any_block = True
        block = match[1]
        kind = re.search(r"<TYPE>\s*([^\r\n<]+)", block[:1000], re.I)
        kind = kind[1].strip().upper() if kind else ""
        if not (kind.startswith(("10-", "20-F", "40-F", "8-K", "6-K", "S-", "F-", "424", "DEF ", "PRE ", "EX-99"))
                or prose and kind.startswith(("EX-10", "EX-3"))
                or not prose and kind.startswith("EX-101")): continue
        filename = re.search(r"<FILENAME>\s*([^\r\n<]+)", block[:2000], re.I)
        body = re.search(r"<TEXT>(.*?)</TEXT>", block, re.I | re.S)
        body = body[1] if body else block
        if kind.startswith("EX-101") and not re.search(r"<(?:\w+:)?xbrl\b", body[:3000], re.I): continue
        body = re.sub(r"<img\b[^>]*>", "", body, flags=re.I | re.S)
        yield filename[1].strip() if filename else "primary", kind, body
    if not any_block: yield "primary", "unknown", raw


def local_name(tag):
    return str(tag).split("}")[-1].split(":")[-1].lower()


def fact_text(node):
    pieces = [node.text or ""]
    for child in node:
        if local_name(child.tag) != "exclude": pieces.append(fact_text(child))
        pieces.append(child.tail or "")
    return "".join(pieces)


def numeric(text, *, scale=0, sign=None, format_name=None):
    """Supported SEC inline number transforms; unsupported formats stay unknown."""
    value = re.sub(r"\s+", "", text or "").replace("\u2212", "-")
    format_name = (format_name or "").split(":")[-1].lower()
    if format_name and format_name not in {"numdotdecimal", "num-dot-decimal", "numcommadecimal", "num-comma-decimal", "zerodash", "zero-dash"}: return None
    if format_name in {"zerodash", "zero-dash"} and value in {"-", "\u2014", "\u2013"}: value = "0"
    if format_name in {"numcommadecimal", "num-comma-decimal"}: value = value.replace(".", "").replace(",", ".")
    else: value = value.replace(",", "")
    negative = value.startswith("(") and value.endswith(")")
    if negative: value = "-"+value[1:-1]
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value): return None
    try:
        scale = int(scale)
        if abs(scale) > 12: return None
        result = float(value)*10**scale
        if sign == "-": result = -abs(result)
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError, TypeError): return None


def standard_facts(document, cik):
    """Extract whole-entity contexts, supported units, explicit periods and clocks."""
    known = moment(document.get("known_at"))
    if not known: return []
    raw = document["text"]
    facts = []
    for filename, _, body in document_bodies(raw):
        if not re.search(r"contextRef\s*=", body, re.I): continue
        try:
            if re.search(r"<(?:\w+:)?xbrl\b", body, re.I) and not re.search(r"<html\b", body, re.I):
                tree = etree.fromstring(body.strip().encode(), parser=etree.XMLParser(resolve_entities=False, no_network=True, recover=False))
            else:
                tree = html.fromstring(body.encode(), parser=html.HTMLParser(encoding="utf-8", no_network=True))
        except (etree.XMLSyntaxError, etree.ParserError, ValueError): continue
        contexts, units = {}, {}
        for node in tree.iter():
            if local_name(node.tag) == "context" and node.get("id"):
                descendants = list(node.iter())
                if any(local_name(n.tag) in {"segment", "scenario", "explicitmember", "typedmember"} for n in descendants): continue
                ids = ["".join(n.itertext()).strip() for n in descendants if local_name(n.tag) == "identifier"]
                if len(ids) != 1 or not ids[0].isdigit() or int(ids[0]) != int(cik): continue
                period = {local_name(n.tag): "".join(n.itertext()).strip() for n in descendants
                          if local_name(n.tag) in {"instant", "startdate", "enddate"}}
                start, end = period.get("startdate"), period.get("enddate", period.get("instant"))
                try:
                    if not end or date.fromisoformat(end) > known.date(): continue
                    if start and date.fromisoformat(start) > date.fromisoformat(end): continue
                except ValueError: continue
                contexts[node.get("id")] = {"start": start, "end": end}
            elif local_name(node.tag) == "unit" and node.get("id"):
                if any(local_name(n.tag) in {"divide", "unitnumerator", "unitdenominator"} for n in node.iter()): continue
                measures = ["".join(n.itertext()).strip().split(":")[-1] for n in node.iter() if local_name(n.tag) == "measure"]
                if len(measures) == 1 and (measures[0] == "shares" or re.fullmatch(r"[A-Z]{3}", measures[0])):
                    units[node.get("id")] = measures[0]
        for node in tree.iter():
            context = node.get("contextref") or node.get("contextRef")
            if context not in contexts: continue
            attrs = {local_name(k): v for k, v in node.attrib.items()}
            if attrs.get("nil", "").lower() in {"true", "1"}: continue
            tag = attrs.get("name") if local_name(node.tag) == "nonfraction" else str(node.tag)
            if tag and tag.startswith("{"):
                namespace, label = tag[1:].split("}", 1)
                family = next((k for k in ("us-gaap", "ifrs-full", "dei") if "/"+k+"/" in namespace or "/"+k+"-" in namespace or namespace.endswith("/"+k)), None)
                tag = family+":"+label if family else None
            if tag not in TAGS: continue
            metric, unit = TAGS[tag], units.get(attrs.get("unitref"))
            period = contexts[attrs["contextref"]]
            if not unit or metric == "shares" and unit != "shares" or metric != "shares" and unit == "shares": continue
            if bool(period["start"]) != (metric in FLOWS): continue
            # HTML's itertext also sees ix:exclude footnote content. Excluding
            # it explicitly prevents a footnote marker from changing an amount.
            value = numeric(fact_text(node), scale=attrs.get("scale", 0), sign=attrs.get("sign"), format_name=attrs.get("format"))
            if value is None: continue
            locator = "document="+filename+"; "+tag+"; contextRef="+attrs["contextref"]
            facts.append({"issuer": "cik/"+str(int(cik)), "metric": metric, "value": value, "unit": unit,
                          **period, "known_at": document["known_at"], "source_published_at": document["known_at"],
                          "filed": document.get("filed_at", document["known_at"][:10]),
                          "source_url": document["source_url"], "source_sha256": document["source_sha256"],
                          "locator": locator, "accession": document["accessionNumber"], "tag": tag,
                          "basis": "reported_whole_entity_standard_XBRL"})
    # Inconsistent repetitions require review. Do not choose a convenient value.
    grouped = defaultdict(list)
    for row in facts: grouped[row["metric"], row["unit"], row["start"], row["end"], row["tag"]].append(row)
    return [rows[0] for rows in grouped.values() if len({r["value"] for r in rows}) == 1]
