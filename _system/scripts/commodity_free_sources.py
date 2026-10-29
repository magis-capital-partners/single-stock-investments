"""Free publisher evidence. Regional samples and reported ranges remain explicit.

These observations inform the evidence panel; they never calibrate scenario prices
or silently replace a missing global balance, cost curve, or OTC financing tape.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import io
from pathlib import Path
import re
from urllib.parse import urljoin

from commodity_common import digest, finite, load, save
from commodity_history import month_end

WEEKLY = 'https://www.cochilco.cl/web/informe-semanal-del-cobre/'
INVENTORIES = 'https://www.cochilco.cl/web/download/138/estadisticas-historico-inventarios-mundiales-de-cobre/13744/inventarios-mundiales-del-cobre-mensual-2.xlsx'
CONCENTRATES = 'https://www.cochilco.cl/web/cochilco-publica-estudio-sobre-el-mercado-de-concentrados-y-la-industria-mundial-de-fundiciones/'
AURUM = 'https://www.aurumanalytics.com.au/reports_and_media'
WGC = 'https://www.gold.org/goldhub/gold-focus/2026/08/record-gold-prices-outpace-rising-mining-costs-q126'
SILVER = 'https://silverinstitute.org/wp-content/uploads/2026/04/World-Silver-Survey-2026.pdf'
MONTHS = dict(zip('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split(), range(1, 13)))


def pdf_text(raw):
    import fitz
    if not raw.startswith(b'%PDF'): raise ValueError('Expected publisher PDF')
    with fitz.open(stream=raw, filetype='pdf') as doc:
        if doc.needs_pass: raise ValueError('Publication requires a password')
        return '\n'.join(page.get_text() for page in doc)


def copper_weekly(text):
    """Read the labelled inventory table, never the unrelated chart coordinates."""
    stamp = re.search(r'Reporte al \w+\s+(\d{1,2}) de (\w+) de (\d{4})', text, re.I)
    if not stamp:
        heading=re.search(r'\bSemana\b[^\n]+',text,re.I)
        stamp=re.search(r'(\d{1,2}) (?:de )?(\w+) del? (\d{4})\s*$',heading[0]) if heading else None
    if not stamp: raise ValueError('Weekly report date missing')
    day, month, year = stamp.groups()
    when = date(int(year), MONTHS[month.lower()], int(day)).isoformat()
    column=re.search(r'Stock Actual\s*\(TM\)',text)
    table = text[column.end():] if column else ''
    row = {'period': when, 'basis': 'exchange stocks reported by Cochilco'}
    for key, label in [('lme_t', r'BML[-–]Londres'), ('comex_t', r'COMEX[-–]EE\.?UU\.?'), ('shfe_t', r'SHFE[-–]Shanghai'), ('total_t', 'TOTAL GLOBAL')]:
        value = re.search(label + r'\s+([\d.]+)\s', table, re.I)
        if value: row[key] = int(value[1].replace('.', ''))
    if len(row)<6:
        # Earlier PDFs put numbers in prose and embed the table as an image.
        # Only exact tonne amounts in the inventory section are accepted.
        heading=re.search(r'INVENTARIOS EN (?:LAS BODEGAS DE LAS BOLSAS\s+DE METALES|BOLSAS DE METALES)',text)
        body=' '.join(text[heading.end():].split()) if heading else ''
        symbols=list(re.finditer(r'\b(LME|BML|COMEX|SHFE)\b',body,re.I))
        for i,hit in enumerate(symbols):
            segment=body[hit.end():symbols[i+1].start() if i+1<len(symbols) else hit.end()+250][:250]
            amount=re.search(r'(\d{1,3}(?:\.\d{3})+)\s*(?:toneladas|t\b)',segment)
            if amount:
                key={'lme':'lme_t','bml':'lme_t','comex':'comex_t','shfe':'shfe_t'}[hit[1].lower()]
                number=int(amount[1].replace('.',''))
                if key in row and row[key]!=number:raise ValueError('Ambiguous regional stock amounts')
                row[key]=number
        total=re.search(r'(?:sumaron|totalizaron)\s+(\d{1,3}(?:\.\d{3})+)\s+toneladas',body)
        if total:row['total_t']=int(total[1].replace('.',''))
    if len(row)<6 and 'Resumen de inventarios' in text and re.search(r'\bT\.M\b',text):
        legacy=text.split('Resumen de inventarios',1)[1]
        for key,label in [('lme_t','BML'),('comex_t','COMEX'),('shfe_t','SHFE'),('total_t','Total')]:
            amount=re.search(r'(?m)^\s*'+label+r'\s*\n\s*(\d{1,3}(?:[,.]\d{3})+)\s*\n',legacy)
            if amount:row[key]=int(re.sub(r'[,.]','',amount[1]))
    if len(row)<6:raise ValueError('Exact inventory rows/units unavailable')
    if abs(row['lme_t'] + row['comex_t'] + row['shfe_t'] - row['total_t']) > 2:
        raise ValueError('Regional inventory total does not reconcile')
    return row


def copper_monthly(raw, as_of):
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        values = list(book.active.values)
        if 'toneladas métricas' not in str(values[2][0]): raise ValueError('Inventory workbook units changed')
        if values[4][:7] != ('Mes-Año', 'Wirebars', 'Cátodos', 'Total', 'Total', 'Total', 'Total'):
            raise ValueError('Inventory workbook columns changed')
        rows = []
        for cells in values[5:]:
            if not isinstance(cells[0], datetime): continue
            period = month_end(cells[0].strftime('%Y-%m'))
            if period > as_of.isoformat(): continue
            row = {'period': period, 'basis': 'month end; unavailable exchanges remain blank'}
            row.update({k: float(cells[i]) if finite(cells[i]) else None for k, i in [('lme_t', 3), ('comex_t', 4), ('shfe_t', 5), ('total_t', 6)]})
            if all(row[k] is not None for k in ('lme_t', 'comex_t', 'shfe_t', 'total_t')) and abs(sum(row[k] for k in ('lme_t', 'comex_t', 'shfe_t')) - row['total_t']) > 2:
                raise ValueError('Monthly regional inventory total does not reconcile')
            rows.append(row)
        if not rows: raise ValueError('No monthly inventories')
        return rows
    finally: book.close()


def aurum(text):
    """Parse the disclosed mine sample, preserving AUD and negative by-product costs."""
    stamp = re.search(r'(March|June|September|December) Quarter (\d{4})', text)
    if not stamp: raise ValueError('Aurum quarter missing')
    month = {'March': 3, 'June': 6, 'September': 9, 'December': 12}[stamp[1]]
    period = month_end(f'{stamp[2]}-{month:02}')
    start = text.find('AISC Rank')
    end = text.find('Gold Operations That Report AISC', start)
    if start < 0 or end < 0 or 'A$/oz' not in text[start:end]: raise ValueError('Aurum cost table missing')
    pattern = r'(?m)^\s*(\d+)=?\s*\n([^\n]+)\n([^\n]+)\n(OP/UG|OP|UG|NM)\s*\n\s*(-?[\d,]+)\s*\n\s*([\d.]+|NA)\s*\n\s*(?:\d+=?|NR)\s*\n\s*([\d,]+)\s*(?=\n)'
    rows = []
    for rank, operation, company, kind, cost, grade, output in re.findall(pattern, text[start:end]):
        rows.append({'period': operation.strip(), 'company': company.strip(), 'rank': int(rank), 'mine_type': kind,
                     'aisc_aud_oz': int(cost.replace(',', '')), 'production_oz': int(output.replace(',', '')),
                     'grade_g_t': float(grade) if grade!='NA' else None, 'basis': 'reported AISC; may include by-product credits'})
    rows.sort(key=lambda r:r['rank'])
    if len(rows) < 15 or any(r['rank']!=i+1 and (not i or r['rank']!=rows[i-1]['rank']) for i,r in enumerate(rows)):
        raise ValueError('Incomplete or reordered Aurum cost table')
    summary = re.search(r'average All-in Sustaining Cost.*?A\$([\d,]+)/oz', text, re.S)
    if not summary: raise ValueError('Aurum average missing')
    return {'period': period, 'rows': rows, 'simple_average_aud_oz': int(summary[1].replace(',', ''))}


def collect(download, prior, as_of, root):
    """Independent failures preserve each dataset's last good observations and hash."""
    from bs4 import BeautifulSoup
    root = Path(root)
    output, failures = {}, []

    def raw(url, immutable=False):
        receipt = root / 'free-vintages' / (digest(url) + '.json')
        cached = load(receipt, {}) if immutable else {}
        original = root / 'objects' / cached.get('sha256', 'missing')
        if cached and original.is_file():
            data = original.read_bytes()
            if digest(data) == cached['sha256']: return data
        data = download(url)
        path = root / 'objects' / digest(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists(): path.write_bytes(data)
        save(receipt, {'url': url, 'sha256': digest(data), 'fetched_at': as_of.isoformat()})
        return data

    def dataset(key, title, url, fn):
        try:
            value = fn()
            period = value.get('period')
            if period and period > as_of.isoformat(): raise ValueError('Future observation')
            output[key] = {'title': title, 'source_url': url, 'status': 'available', 'fetched_at': as_of.isoformat(), **value}
        except Exception as exc:
            output[key] = {**prior.get(key, {}), 'title': title, 'status': 'fetch_failed', 'attempted_url': url,
                           'last_attempt': as_of.isoformat(), 'error': str(exc)[:180]}
            failures.append(key)

    def inventories():
        monthly_raw = raw(INVENTORIES)
        monthly = copper_monthly(monthly_raw, as_of)
        page = raw(WEEKLY); soup = BeautifulSoup(page, 'html.parser')
        years=f'(?:{as_of.year-1}|{as_of.year})'
        urls = list(dict.fromkeys(urljoin(WEEKLY, a['href']) for a in soup.select('a[href]')
                                 if re.search(r'/'+years+r'/.*informe-del-mercado-internacional-del-cobre.*\.pdf$', a['href'])))
        if not urls: raise ValueError('No weekly inventory publications')
        def weekly(url):
            try:
                data = raw(url, immutable=True); row = copper_weekly(pdf_text(data))
                return {**row, 'source_url': url, 'sha256': digest(data)}, None
            except Exception as exc: return None, {'source_url': url, 'error': str(exc)[:120]}
        with ThreadPoolExecutor(max_workers=4) as pool: parsed = list(pool.map(weekly, urls))
        retained={r['period']:r for r in prior.get('copper_exchange_stocks',{}).get('rows',[]) if r['period']<=as_of.isoformat()}
        retained.update({r['period']:r for r,_ in parsed if r and r['period']<=as_of.isoformat()})
        rows = [retained[k] for k in sorted(retained)]
        errors = [e for _, e in parsed if e]
        if not rows: raise ValueError('No validated weekly inventory tables')
        return {'period': rows[-1]['period'], 'unit': 'metric tonnes', 'rows': rows, 'monthly_rows': monthly,
                'monthly_source_url': INVENTORIES, 'monthly_sha256': digest(monthly_raw), 'sha256': digest(page),
                'status': 'partial' if errors else 'available', 'parse_failures': errors,
                'note': 'Cochilco reports LME, COMEX and SHFE separately. Exchange location is not warehouse geography or freely available metal. Monthly history and weekly observations remain separate; gaps are not interpolated.'}

    def costs():
        page = raw(AURUM); soup = BeautifulSoup(page, 'html.parser')
        links = list(dict.fromkeys(urljoin(AURUM, a['href']) for a in soup.select('a[href]')
                                  if re.search(r'/20\d{2}_Q[1-4]_Aurum_Analytics_Quarterly_Gold_Report.*\.pdf$', urljoin(AURUM, a['href']))))
        reports = []; errors = []
        for url in links:
            try:
                data = raw(url, immutable=True); report = aurum(pdf_text(data))
                if report['period'] <= as_of.isoformat(): reports.append({**report, 'source_url': url, 'sha256': digest(data)})
            except Exception as exc: errors.append({'source_url': url, 'error': str(exc)[:120]})
        if not reports: raise ValueError('No validated Aurum mine-cost tables')
        reports.sort(key=lambda r: r['period']); latest = reports[-1]
        return {**latest, 'unit': 'AUD/oz', 'history': [{k: v for k, v in r.items() if k != 'rows'} for r in reports],
                'status': 'partial' if errors else 'available', 'parse_failures': errors,
                'note': 'Australia/New Zealand reporting mines only. Costs retain AUD/oz and by-product credits, including negative values. Production is generally on a 100% basis, with publisher exceptions; this sample is not a global cost curve or a bullion price floor.'}

    def global_cost():
        data = raw(WGC); text = BeautifulSoup(data, 'html.parser').get_text(' ', strip=True)
        if 'Q1’26' not in text or 'US$1,785/oz' not in text: raise ValueError('Reviewed WGC cost observation changed')
        return {'period': '2026-03-31', 'published_at': '2026-08-24', 'unit': 'USD/oz', 'sha256': digest(data),
                'rows': [{'period': '2026-Q1', 'aisc_usd_oz': 1785, 'basis': 'WGC / Metals Focus published global average'}],
                'note': 'Limited public extract from WGC / Metals Focus. A global average does not supply mine-level global percentiles. Historical quarter, not current mining costs.'}

    def concentrates():
        page = raw(CONCENTRATES); soup = BeautifulSoup(page, 'html.parser')
        links = [urljoin(CONCENTRATES, a['href']) for a in soup.select('a[href]') if 'mercado-de-concentrados-e-industria-de-fundiciones-2026.pdf' in a['href']]
        if not links: raise ValueError('2026 concentrate report missing')
        data = raw(links[0], immutable=True); text = pdf_text(data)
        if '18.723 ktmf' not in text or 'Reporte 2026' not in text: raise ValueError('Reviewed concentrate supply changed')
        return {'source_url': links[0], 'sha256': digest(data), 'period': '2025-12-31', 'publication_period': '2026-08',
                'unit': 'thousand tonnes contained copper', 'status': 'partial',
                'rows': [{'period': '2025', 'concentrate_supply_kt_cu': 18723, 'basis': 'Cochilco / WMS published estimate'}],
                'note': '2026 report: 2025 global concentrate output is 18,723 kt of contained copper. Custom concentrate availability differs from integrated supply. The report supplies TC/RC and custom-balance charts, but no complete machine-readable, dated spot TC tape or matching global intake table. Chart values are not invented or mixed with refined copper balances.'}

    def silver_liquidity():
        data = raw(SILVER, immutable=True); text = ' '.join(pdf_text(data).split())
        if not all(s in text for s in ('2-3%', '17%', '24%', '35%')): raise ValueError('Reviewed silver liquidity observations changed')
        return {'sha256': digest(data), 'period': '2026-02-28', 'publication_period': '2026-04', 'unit': 'percent', 'status': 'partial',
                'rows': [{'period': '2024-12', 'non_etp_share_pct': 35, 'basis': 'approximately; reported by Metals Focus'},
                         {'period': '2025-09', 'non_etp_share_pct': 17, 'basis': 'reported by Metals Focus'},
                         {'period': '2026-02', 'non_etp_share_pct': 24, 'basis': 'reported by Metals Focus'}],
                'lease_observation': {'period': 'mid-Q1 2026', 'low_pct': 2, 'high_pct': 3, 'tenor': 'not specified in the cited paragraph'},
                'note': 'World Silver Survey 2026, page 43. Lease rates were reported around 2–3% in mid-Q1; no exact day or consistent tenor is assigned. Non-ETP holdings remain privately owned: these percentages are not available float. Neither observation is a current financing quote.'}

    dataset('copper_exchange_stocks', 'Copper inventories by exchange', WEEKLY, inventories)
    dataset('gold_regional_cost_curve', 'Australia/New Zealand mine costs', AURUM, costs)
    dataset('gold_global_average_cost', 'Global gold mining cost reference', WGC, global_cost)
    dataset('copper_concentrate_report', 'Concentrate supply and smelter conditions', CONCENTRATES, concentrates)
    dataset('silver_liquidity_report', 'Silver liquidity observations', SILVER, silver_liquidity)
    return output, failures
