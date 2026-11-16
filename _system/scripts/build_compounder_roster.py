"""Generate the dashboard watchlist from the single maintained compounder roster."""
from buy_zones import load_config
from commodity_common import ROOT, save
import json
from listing_units import resolve_units


def build(root=ROOT):
    config=load_config(root/'_system/reference/core_compounders.json')
    holdings=json.loads((root/'_system/portfolio/registry.json').read_text(encoding='utf-8'))['holdings']
    companies=[]
    for ticker in config['tickers']:
        meta=config['issuers'][ticker]
        listing=holdings.get(ticker, {})
        companies.append({'ticker':ticker,'name':meta['display_name'],'group':meta['watchlist_group'],'aliases':meta.get('aliases',[]),
                          'units':resolve_units(ticker,listing.get('market'),listing.get('exchange')),
                          **{key:listing[key] for key in ('market','exchange','quote_ticker','classification') if key in listing}})
    as_of=str(config['version']).rsplit('.',1)[0]
    return {'schema_version':'compounders.v1','as_of':as_of,
            'source':f'Owner list, {as_of}','groups':config['groups'],'companies':companies}


def build_serial_acquirers(root=ROOT):
    """Publish curated listing identities, never the source's scores or valuations."""
    source = json.loads((root/'_system/reference/serial_acquirers.json').read_text(encoding='utf-8'))
    tickers = [row['ticker'] for row in source['companies']]
    source_ids = [row['source_id'] for row in source['companies']]
    if len(tickers) != len(set(tickers)) or len(source_ids) != len(set(source_ids)):
        raise ValueError('Serial acquirer listings and source IDs must be unique')
    holdings=json.loads((root/'_system/portfolio/registry.json').read_text(encoding='utf-8'))['holdings']
    return {**source, 'schema_version': 'serial_acquirers.v1', 'companies': [
        {**row, 'classification': holdings.get(row['ticker'], {}).get('classification', {}),
         'units':resolve_units(row['ticker'],row['market'],row['exchange'])}
        for row in source['companies']
    ]}


def publish():
    save(ROOT/'dashboard/data/compounders.json',build())
    save(ROOT/'dashboard/data/serial_acquirers.json',build_serial_acquirers())


if __name__=='__main__':
    publish()
