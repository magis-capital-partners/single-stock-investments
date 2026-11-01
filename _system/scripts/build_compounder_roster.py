"""Generate the dashboard watchlist from the single maintained compounder roster."""
from buy_zones import load_config
from commodity_common import ROOT, save


def build():
    config=load_config(ROOT/'_system/reference/core_compounders.json')
    companies=[]
    for ticker in config['tickers']:
        meta=config['issuers'][ticker]
        companies.append({'ticker':ticker,'name':meta['display_name'],'group':meta['watchlist_group'],'aliases':meta.get('aliases',[])})
    as_of=str(config['version']).rsplit('.',1)[0]
    return {'schema_version':'compounders.v1','as_of':as_of,
            'source':f'Owner list, {as_of}','groups':config['groups'],'companies':companies}


if __name__=='__main__':
    save(ROOT/'dashboard/data/compounders.json',build())
