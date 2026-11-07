"""Complete financing documents from authenticated issuer SEC submissions."""
from __future__ import annotations

import hashlib
import re
from datetime import date


def financing_references(submissions, cik, as_of, keywords):
    years = {m[1] for term in keywords for m in re.finditer(
        r'\b((?:19|20)\d{2})\b[^\n]{0,60}\bnotes?\b', term, re.I)}
    if not years:
        return []
    recent = (submissions.get('filings') or {}).get('recent') or {}
    result, identities = [], {}
    def value(key, index):
        rows = recent.get(key) or []
        return rows[index] if index < len(rows) else ''
    for i, form in enumerate(recent.get('form') or []):
        filed, accession, name, items = (value(k, i) for k in ('filingDate', 'accessionNumber', 'primaryDocument', 'items'))
        if (form not in ('8-K', '8-K/A') or not isinstance(filed, str)
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', filed)
                or filed[:4] not in years or filed > as_of
                or not isinstance(accession, str) or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession)
                or not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.html?', name)
                or not isinstance(items, str)):
            continue
        try:
            date.fromisoformat(filed)
        except ValueError:
            continue
        item_set = {s.strip() for s in items.split(',')}
        if '2.03' not in item_set and not {'8.01', '9.01'} <= item_set:
            continue
        url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{accession}.txt'
        metadata = {'form': form, 'filed': filed, 'accession': accession, 'primary_document': name}
        if url in identities:
            if identities[url] != metadata:
                raise ValueError('Ambiguous primary financing discovery metadata')
            continue
        identities[url] = metadata
        result.append({'source_url': url, '_score': 40, '_submission': metadata})
    return result


def financing_documents(url, raw, cik, metadata):
    """Keep every primary/EX-4 text intact; distinguish package and member hashes."""
    from underwriting_contract import digest, require
    from underwriting_evidence import primary_text, text_of, registered_securities
    require(len(raw) <= 20_000_000, 'Primary submission exceeds the bounded evidence size')
    acc = metadata['accession']
    expected = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/{acc}.txt'
    require(url == expected, 'Primary submission URL identity mismatch')
    require(re.match(rb'\s*<SEC-DOCUMENT>'+re.escape(acc.encode())+rb'\.txt\b', raw)
            and raw.rstrip().endswith(b'</SEC-DOCUMENT>'), 'Incomplete primary submission envelope')
    headers = re.findall(br'<SEC-HEADER\b[^>]*>(.*?)</SEC-HEADER>', raw, re.I|re.S)
    require(len(headers) == 1, 'Ambiguous primary submission header')
    header = headers[0]
    def header_values(label):
        return re.findall(rb'^\s*'+label+rb':\s*([^\r\n]+)', header, re.I|re.M)
    require(header_values(b'ACCESSION NUMBER') == [acc.encode()], 'Primary submission accession mismatch')
    require(header_values(b'CONFORMED SUBMISSION TYPE') == [metadata['form'].encode()], 'Primary submission form mismatch')
    require(header_values(b'FILED AS OF DATE') == [metadata['filed'].replace('-', '').encode()], 'Primary submission date mismatch')
    ciks = header_values(b'CENTRAL INDEX KEY')
    require(ciks and all(value.isdigit() for value in ciks) and {int(v) for v in ciks} == {int(cik)},
            'Primary submission issuer mismatch')
    blocks = re.findall(br'<DOCUMENT>\s*(.*?)</DOCUMENT>', raw, re.I|re.S)
    counts = header_values(b'PUBLIC DOCUMENT COUNT')
    require(len(counts) == 1 and counts[0].isdigit() and int(counts[0]) == len(blocks),
            'Incomplete primary submission document count')
    parts, names, sequences = [], set(), set()
    for block in blocks:
        def field(label):
            values = re.findall(br'^<'+label+br'>([^\r\n<]+)', block, re.I|re.M)
            require(len(values) == 1, 'Ambiguous primary submission document metadata')
            return values[0].decode('ascii')
        kind, name, sequence = field(b'TYPE'), field(b'FILENAME'), field(b'SEQUENCE')
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', name) and name not in names
                and sequence.isdigit() and sequence not in sequences, 'Invalid primary submission member identity')
        names.add(name); sequences.add(sequence)
        texts = re.findall(br'<TEXT>\s*(.*?)</TEXT>', block, re.I|re.S)
        require(len(texts) == 1, 'Incomplete primary submission member text')
        parts.append((kind.upper(), name, sequence, texts[0]))
    primary = [p for p in parts if p[0] == metadata['form'] and p[1] == metadata['primary_document']]
    require(len(primary) == 1, 'Primary submission report identity mismatch')
    body = text_of(primary_text(primary[0][3]))
    event = re.search(r'\bItem\s+(?:8\.01|2\.03)\b', body, re.I)
    if not event or not re.search(r'\bnotes?\s+offering\b|\b(?:issued|issuance)\b.{0,300}\bnotes?\b',
                                  body[event.end():], re.I):
        return []  # A security-cover mention does not identify a note issuance.
    docs = []
    package_hash = hashlib.sha256(raw).hexdigest()
    for kind, name, sequence, content in parts:
        if (kind, name) != primary[0][:2] and not re.fullmatch(r'EX-4(?:\.\d+)?', kind):
            continue
        require(re.fullmatch(r'[A-Za-z0-9_.-]+\.html?', name), 'Unsupported complete financing member format')
        source = primary_text(content); text = text_of(source)
        require(500 <= len(text) <= 350000, 'Complete financing member exceeds the bounded evidence size')
        securities = registered_securities(source)
        docs.append({'id': 'doc_'+digest(url+'#'+name)[:16], 'source_url': url,
                     'content_hash': package_hash, 'contexts': [text],
                     'coverage': 'complete_requested_primary_document', 'form': metadata['form'],
                     'filed': metadata['filed'], 'accession': acc, 'document_kind': 'material_financing_disclosure',
                     'submission_document': {'type': kind, 'filename': name, 'sequence': sequence,
                                             'embedded_text_sha256': hashlib.sha256(content).hexdigest()},
                     **({'registered_securities': securities} if securities else {})})
    return docs
