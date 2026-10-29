"""Generate the dashboard watchlist from the single maintained compounder roster."""
from commodity_common import ROOT, load, save


def build():
    config=load(ROOT/'_system/reference/core_compounders.json')
    companies=[]
    for ticker in config['tickers']:
        meta=config['issuers'][ticker]
        companies.append({'ticker':ticker,'name':meta['display_name'],'group':meta['watchlist_group'],'aliases':meta.get('aliases',[])})
    return {'schema_version':'compounders.v1','as_of':config['version'].rsplit('.',1)[0],
            'source':'Owner list, 2026-10-28','groups':config['groups'],'companies':companies}


if __name__=='__main__':
    save(ROOT/'dashboard/data/compounders.json',build())
