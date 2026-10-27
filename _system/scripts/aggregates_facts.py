"""Dated, period-aligned financial observations for the aggregates universe."""
from __future__ import annotations
import hashlib
import math
from datetime import date, timedelta

FLOW_TAGS = {
    'revenue_usd': ['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueNet'],
    'operating_income_usd':['OperatingIncomeLoss'],
    'dda_usd':['DepreciationDepletionAndAmortization','DepreciationAmortizationAndAccretionNet','DepreciationDepletionAndAmortizationExcludingAmortizationOfDeferredFinancingCosts','DepreciationAndAmortization'],
    'cfo_usd':['NetCashProvidedByUsedInOperatingActivities','NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
    'capex_usd':['PaymentsToAcquirePropertyPlantAndEquipment','PaymentsToAcquireProductiveAssets'],
    'net_income_usd':['NetIncomeLoss','NetIncomeLossAvailableToCommonStockholdersBasic'],
    'acquisitions_usd':['PaymentsToAcquireBusinessesNetOfCashAcquired'],
    'dividends_usd':['PaymentsOfDividendsCommonStock','PaymentsOfDividends'],
    'repurchases_usd':['PaymentsForRepurchaseOfCommonStock'],
    'interest_expense_usd':['InterestExpenseNonOperating','InterestAndDebtExpense','InterestExpense'],
    'income_tax_usd':['IncomeTaxExpenseBenefit'],
    'pretax_income_usd':['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest','IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments'],
}
BALANCE_TAGS={
    'cash_usd':['CashAndCashEquivalentsAtCarryingValue'],
    'restricted_cash_usd':['RestrictedCashAndCashEquivalentsCurrent','RestrictedCashAndCashEquivalents'],
    'equity_usd':['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
    'ppe_net_usd':['PropertyPlantAndEquipmentNet'],
    'goodwill_usd':['Goodwill'],
    'intangibles_usd':['IntangibleAssetsNetExcludingGoodwill','FiniteLivedIntangibleAssetsNet'],
    'total_assets_usd':['Assets'],
    'noncontrolling_interest_usd':['MinorityInterest'],
    'lease_liabilities_usd':['OperatingLeaseLiability'],
    'current_debt_usd':['DebtCurrent','LongTermDebtCurrent','LongTermDebtAndCapitalLeaseObligationsCurrent'],
    'short_term_borrowings_usd':['ShortTermBorrowings'],
    'noncurrent_debt_usd':['LongTermDebtNoncurrent','LongTermDebtAndCapitalLeaseObligationsNoncurrent'],
    'reported_total_debt_usd':['LongTermDebtAndCapitalLeaseObligations','LongTermDebt','DebtAndCapitalLeaseObligations'],
}
FORMS={'10-K','10-K/A','10-Q','10-Q/A','20-F','20-F/A','40-F','40-F/A'}


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def duration(row):
    try:return (date.fromisoformat(row['end'])-date.fromisoformat(row['start'])).days+1
    except (ValueError,KeyError,TypeError):return None


def observation(ticker, cik, key, tag, unit, row, retrieved_at):
    accession=str(row.get('accn') or '')
    return {'id':hashlib.sha256(f"{ticker}:{key}:{row.get('start')}:{row.get('end')}:{accession}:{unit}".encode()).hexdigest()[:24],
        'issuer_id':'cik:'+str(cik),'ticker':ticker,'metric':key,'value':row['val'],'unit':unit,'currency':unit if unit in {'USD','EUR','MXN','GBP'} else None,
        'period_start':row.get('start'),'period_end':row['end'],'period_type':'FY' if (duration(row) or 0)>=330 else 'Q' if 70<=(duration(row) or 0)<=110 else 'YTD' if row.get('start') else 'instant',
        'filed_at':row.get('filed'),'retrieved_at':retrieved_at,'business_segment':'corporate','geography':'consolidated','product':'all',
        'freight_basis':'reported','sales_scope':'consolidated','perimeter_basis':'reported','status':'reported','confidence':'high',
        'source_url':f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/" if accession else f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json',
        'accession':accession,'locator':'us-gaap:'+tag,'version':'aggregates-financial-v1'}


def collect(facts, ticker, cik, retrieved_at, retain_vintages=False):
    selected={}
    for key,tags in {**FLOW_TAGS,**BALANCE_TAGS}.items():
        for rank,tag in enumerate(tags):
            for unit,rows in facts.get('facts',{}).get('us-gaap',{}).get(tag,{}).get('units',{}).items():
                if unit!='USD':continue
                for row in rows:
                    if row.get('form') not in FORMS or not finite(row.get('val')) or not row.get('end'):continue
                    if key in FLOW_TAGS and not row.get('start'):continue
                    if key in BALANCE_TAGS and row.get('start'):continue
                    signature=(key,row.get('start'),row['end'],unit,str(row.get('filed') or '') if retain_vintages else '')
                    old=selected.get(signature)
                    # Latest filing restatement wins; tag preference breaks ties.
                    priority=(str(row.get('filed') or ''),-rank)
                    if not old or priority>old[0]:selected[signature]=(priority,observation(ticker,cik,key,tag,unit,row,retrieved_at))
    return [v[1] for v in selected.values()]


def balance_at(observations, end):
    found={r['metric']:r for r in observations if r['period_type']=='instant' and r['period_end']==end}
    result={k:r['value'] for k,r in found.items()}
    total=result.get('reported_total_debt_usd')
    if total is not None:
        # These concepts include the current portion; never add it again.
        result['total_debt_usd']=total
        result['debt_basis']='reported total debt; current portion included'
    elif all(k in result for k in ['noncurrent_debt_usd','current_debt_usd']):
        result['total_debt_usd']=result['noncurrent_debt_usd']+result['current_debt_usd']
        result['debt_basis']='noncurrent plus current debt; short-term borrowings scope unresolved' if 'short_term_borrowings_usd' in result else 'noncurrent plus current debt'
        current_is_total=found['current_debt_usd'].get('locator')=='us-gaap:DebtCurrent'
        if result.get('short_term_borrowings_usd',0)!=0 and not current_is_total:
            result['total_debt_usd']=None
    else:
        result['total_debt_usd']=None
        result['debt_basis']='incomplete debt scope'
    result['sources']=list(found.values())
    return result


def financial_history(observations):
    periods={}
    for row in observations:
        if row['metric'] not in FLOW_TAGS or row['period_type'] not in {'FY','Q','YTD'}:continue
        key=(row['period_start'],row['period_end'],row['period_type'])
        record=periods.setdefault(key,{'period_start':key[0],'period_end':key[1],'period_type':key[2],'currency':'USD','sources':[]})
        record[row['metric']]=row['value'];record['sources'].append(row)
    values=list(periods.values())
    # Derive standalone quarters from non-overlapping fiscal YTD differences.
    for record in list(values):
        if record['period_type'] not in {'YTD','FY'}:continue
        earlier=[r for r in values if r['period_start']==record['period_start'] and r['period_end']<record['period_end']]
        if not earlier:continue
        prior=max(earlier,key=lambda r:r['period_end']);start=(date.fromisoformat(prior['period_end'])+timedelta(days=1)).isoformat()
        days=(date.fromisoformat(record['period_end'])-date.fromisoformat(start)).days+1
        if not 70<=days<=110:continue
        if any(r['period_start']==start and r['period_end']==record['period_end'] and r['period_type']=='Q' for r in values):continue
        derived={'period_start':start,'period_end':record['period_end'],'period_type':'Q','currency':'USD','status':'derived','sources':record['sources']+prior['sources']}
        for key in FLOW_TAGS:
            if key in record and key in prior:derived[key]=record[key]-prior[key]
        values.append(derived)
    return sorted([r for r in values if r['period_type'] in {'FY','Q'}],key=lambda r:(r['period_end'],r['period_type']))
