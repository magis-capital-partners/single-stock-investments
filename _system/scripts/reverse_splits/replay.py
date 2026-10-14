"""Independent account replay with partial covers and explicit residual liabilities."""
from collections import defaultdict
from datetime import date, timedelta
from math import floor, isfinite
from math import prod

from .execute import full_spread
from .realism import _locate, maintenance, rounded_collateral


def replay(leads, calendar, spec, case, borrows=None, *, constrain_exits=True):
    account = spec["conservative_account"] if case.get("account") == "conservative" else spec["account"]
    cost = spec["execution"][case["execution"]]
    initial = spec["initial_equity"]
    entries = defaultdict(list)
    for lead in sorted(leads, key=lambda c:(c["entry_date"],c["ticker"],c["id"])):
        entries[lead["entry_date"]].append(lead)
    opened, positions, rejections, covers, equity = [], [], [], [], []
    realized = 0.0
    def comm(q, price):
        charge = max(spec["commission"]["minimum_per_side"], q * spec["commission"]["per_share_per_side"])
        cap = spec["commission"].get("maximum_trade_fraction")
        return min(charge, q * price * cap) if cap is not None else charge
    def spread_for(prior, reference):
        minimum = cost["spread_floor"]
        if cost.get("sub_dollar_floor") is not None and reference < 1:
            minimum = cost["sub_dollar_floor"]
        return full_spread(prior.get("high"),prior.get("low"),minimum,cost["range_fraction"])
    def value():
        return initial + realized + sum(p["remaining"] * (p["entry_fill"]/p["factor"]-p["mark"]) for p in opened)
    def requirement(q, price, evidence=None, *, initial=False):
        base=maintenance(q,price,account['house_margin'])
        if evidence:
            base=max(base,q*evidence['minimum_per_share'],q*price*evidence['initial_fraction' if initial else 'maintenance_fraction'])
        return base
    def margin():
        return sum(requirement(p["remaining"],p["mark"],p.get('dated_margin')) for p in opened)
    def borrow_fee(p, days):
        nonlocal realized
        fee=0.0
        for offset in range(days):
            charged = (date.fromisoformat(p["fee_until"]) + timedelta(days=offset)).isoformat()
            actual = sorted((r for r in p.get("borrow_fees", []) if r['date'] == charged), key=lambda r:r['available_at'])
            rate = actual[-1]['fee_annual_fraction'] if actual else p['rate']
            p['actual_fee_days'] += bool(actual)
            p['assumed_fee_days'] += not bool(actual)
            fee += rounded_collateral(p["remaining"],p["mark"])*rate/spec["borrow_collateral"]["day_basis"]
        p["borrow"]+=fee;realized-=fee
    for i,day in enumerate(calendar):
        used_volume=defaultdict(float)
        for p in list(opened):
            elapsed=(date.fromisoformat(day)-date.fromisoformat(p["fee_until"])).days
            borrow_fee(p,elapsed)
            p["fee_until"]=day
            if p.get('share_actions'):
                newfactor=prod(a['ratio'] for a in p['share_actions'] if a['ex_date']<=day)
                if abs(newfactor/p['factor']-1)>1e-10:
                    change=newfactor/p['factor']
                    p['remaining']*=change
                    p['mark']/=change
                    p['factor']=newfactor
                    p['share_adjustments'].append({'date':day,'cumulative_factor':newfactor,'remaining_shares':p['remaining'],'price_observed':bool(p['rows'].get(day))})
                    if abs(p['remaining']-round(p['remaining']))>1e-8:p['fractional_obligation_seen']=True
            if case.get("fee_after_holding_session_3") is not None and i-p["entry_calendar_index"]>=2:
                p["rate"]=case["fee_after_holding_session_3"]
            row=p["rows"].get(day)
            if row:
                newfactor=row["factor"]
                if newfactor != p["factor"]:
                    p["remaining"]*=newfactor/p["factor"]
                    p["factor"]=newfactor
                    if abs(p["remaining"]-round(p["remaining"]))>1e-8:
                        p["fractional_obligation_seen"]=True
                if isfinite(row['open']) and row['open']>0:
                    p["mark"]=row["open"];p["mark_date"]=day
        # Opening gaps affect account buying power before today's entries.
        if value()<margin():
            for p in opened:p["pending"]="margin"

        def cover(p,at_open,reason):
            nonlocal realized
            row=p["rows"].get(day)
            if not row:return
            reference=row['open' if at_open else 'close']
            if not isfinite(reference) or reference<=0:
                p['blocked_cover_days']+=1
                return
            available=max(0,account["max_participation"]*row["volume"]-used_volume[p["ticker"]])
            requested=p["remaining"]
            if constrain_exits:
                q=floor(min(requested,available)+1e-9)
            else:
                q=requested
            if q<=0:
                p["blocked_cover_days"]+=1
                return
            prior=p["prior_row"]
            spread=spread_for(prior,reference)
            quote = row.get('quote_close' if not at_open else 'quote_open')
            if cost.get('quote_required') and not quote:
                p['blocked_cover_days']+=1
                return
            if quote and cost.get('use_quotes'):
                q=floor(min(q,quote['ask_size']))
                if q<=0:
                    p['blocked_cover_days']+=1
                    return
                spread = 2 * (quote['ask']-reference)
            before_slip=reference+spread/2
            fill=before_slip*(1+cost["extra_slippage_bps_per_side"]/10000)
            commission=comm(q,fill)
            if p["actual_fee_days"]+p["assumed_fee_days"]==0:
                current_mark=p['mark']
                prior_close=p['prior_row'].get('close')
                p['mark']=prior_close if prior_close is not None and isfinite(prior_close) and prior_close>0 else p['entry_price']
                p['minimum_fee_collateral_basis']='prior_close' if p['mark']==prior_close else 'entry_price_proxy_prior_close_unavailable'
                borrow_fee(p,1)
                p['fee_until']=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
                p['mark']=current_mark
            gross=q*(p["entry_fill"]/p["factor"]-fill)
            realized+=gross-commission
            p["gross_closed"]+=gross;p["exit_commission"]+=commission
            p["raw_closed"]+=q*(p["entry_price"]/p["factor"]-reference)
            p["spread_cost"]+=q*spread/2
            p["slippage_cost"]+=q*(fill-before_slip)
            p["remaining"]-=q;used_volume[p["ticker"]]+=q
            p["last_cover_date"]=day;p["exit_reason"]=reason
            p["last_exit_fill"]=fill
            covers.append({"position_id":p["id"],"ticker":p["ticker"],"date":day,"shares":q,"fill":fill,
                           "reference":reference,"commission":commission,"reason":reason,"at_open":at_open})
            if p["remaining"]<1e-8:
                p["remaining"]=0;opened.remove(p);p["status"]="closed"
            elif q+1e-8<requested:
                p["partial_covers"]+=1
        for p in list(opened):
            if p["pending"]:cover(p,True,p["pending"])
        for lead in entries.get(day,[]):
            reason=None
            if any(p["ticker"]==lead["ticker"] for p in opened):reason="already_open"
            elif len(opened)>=account["max_names"]:reason="max_names"
            elif any(p["pending"] in {"margin","risk_stop"} for p in opened):reason="risk_exit_pending"
            rate=case["fee_annual"]
            if case.get('current_rate_cap') is not None:
                indication=lead.get('current_borrow_indication')
                if not indication or indication['fee_annual_fraction'] is None or indication['available_shares']<=0:
                    reason=reason or 'current_borrow_indication_unavailable'
                elif indication['fee_annual_fraction']>case['current_rate_cap']:
                    reason=reason or 'current_indicative_rate_above_cap'
                else:rate=indication['fee_annual_fraction']
            locate=None
            if not reason and case.get("borrow_policy")=="strict":
                locate=_locate(borrows,lead["ticker"],day,spec["borrow_max_age_hours"])
                approval=locate[3] if locate and len(locate)>3 else {}
                if (not locate or not locate[1] or locate[1]<=0 or locate[2] is None or locate[2]<0
                        or not isinstance(approval,dict) or approval.get('approved') is not True or not approval.get('reference')):
                    reason="no_fresh_locate_and_fee"
                else:rate=float(locate[2])
                if not reason and rate>case.get('maximum_borrow_annual_fraction',float('inf')):
                    reason='dated_borrow_rate_above_cap'
            row=lead["rows"][day]
            prior=lead["prior_row"]
            spread=spread_for(prior,row['open'])
            quote = row.get('quote_open')
            if cost.get('quote_required') and not quote and not reason:
                reason='historical_entry_quote_unavailable'
            if quote and cost.get('use_quotes'):
                spread = 2 * (row['open']-quote['bid'])
            before_slip=row["open"]-spread/2
            fill=before_slip*(1-cost["extra_slippage_bps_per_side"]/10000)
            if not reason and (fill<=0 or row["volume"]<=0):reason="no_executable_entry_proxy"
            eq=value()
            if not reason:
                unit_margin=max(.5*fill,requirement(1,row["open"],lead.get('dated_margin'),initial=True))
                available=max(0,eq*(1-account["buffer_fraction"])-margin()-spec["commission"]["minimum_per_side"])
                size=min(account["target_notional"]/fill,max(0,eq)*account["position_fraction"]/fill,
                         account["max_participation"]*lead["adv"],
                         available/(unit_margin+max(0,row["open"]-fill)+spec["commission"]["per_share_per_side"]))
                if locate:size=min(size,float(locate[1]))
                size=floor(max(0,size))
                if quote and cost.get('use_quotes'):
                    size=min(size,floor(quote['bid_size']))
                stress = account.get('stress_adverse_fraction')
                if stress is not None:
                    stressed_price = row['open']*(1+stress)
                    stress_unit = max(0,stressed_price-fill) + rounded_collateral(1,stressed_price)*rate*account.get('stress_fee_multiple',3)*account.get('stress_calendar_days',7)/360
                    if stress_unit:
                        size=min(size,floor(max(0,eq)*account['name_loss_fraction']/stress_unit))
                    stressed_reserved=sum(requirement(p['remaining'],p['mark']*(1+stress),p.get('dated_margin'))+p['remaining']*p['mark']*stress for p in opened)
                    stressed_unit=requirement(1,stressed_price,lead.get('dated_margin'),initial=True)+max(0,stressed_price-fill)
                    size=min(size,floor(max(0,eq*(1-account['buffer_fraction'])-stressed_reserved)/stressed_unit))
                if cost.get('maximum_cost_fraction') is not None:
                    days=1 if case['horizon_sessions']==1 else case['horizon_sessions']*7/5+2
                    cost_fraction=(spread+2*fill*cost['extra_slippage_bps_per_side']/10000+2*comm(max(1,size),fill)/max(1,size)+rounded_collateral(1,row['open'])*rate*days/360)/fill
                    if cost_fraction>cost['maximum_cost_fraction']:
                        reason='cost_budget_exceeded'
                if size*fill<100:reason="margin_liquidity_or_minimum_size"
            if reason:
                rejections.append({"id":lead["id"],"ticker":lead["ticker"],"entry_date":day,"reason":reason});continue
            target=i+case["horizon_sessions"]-1
            planned=calendar[target] if target<len(calendar) else None
            scheduled=lead.get("announced_ex_date")
            if scheduled and day>=scheduled:
                rejections.append({"id":lead["id"],"ticker":lead["ticker"],"entry_date":day,"reason":"known_split_already_effective"});continue
            if scheduled and (planned is None or scheduled<=planned):
                earlier=[d for d in calendar[i:] if d<scheduled]
                planned=earlier[-1] if earlier else None
            p={"id":lead["id"],"ticker":lead["ticker"],"cik":lead["cik"],"entry_date":day,
               "announcement_category":lead.get('announcement_category','fixture'),"dated_margin":lead.get('dated_margin'),
               "entry_calendar_index":i,"planned_exit":planned,"entry_shares":size,"remaining":float(size),
               "entry_price":row["open"],"entry_fill":fill,"factor":1.0,"mark":row["open"],"mark_date":day,
               "rate":rate,"borrow":0.0,"fee_until":day,"entry_commission":comm(size,fill),"exit_commission":0.0,
               "borrow_fees":lead.get('borrow_fees',[]),"actual_fee_days":0,"assumed_fee_days":0,
               "share_actions":lead.get('share_actions',[]),"share_adjustments":[],
               "locate_reference":locate[3]['reference'] if locate else None,
               "spread_cost":size*spread/2,"slippage_cost":size*(before_slip-fill),
               "gross_closed":0.0,"raw_closed":0.0,"pending":None,"status":"open","last_cover_date":None,
               "partial_covers":0,"blocked_cover_days":0,"fractional_obligation_seen":False,"rows":lead["rows"],
               "prior_row":prior,"score":lead["fundamental"],"source_url":lead.get("source_url"),"mae":0.0}
            realized-=p["entry_commission"];positions.append(p);opened.append(p)
        for p in list(opened):
            row=p["rows"].get(day)
            if row:
                valid_close=isfinite(row['close']) and row['close']>0
                if valid_close:
                    p["mark"]=row["close"];p["mark_date"]=day
                p["mae"]=max(p["mae"],row["high"]*p["factor"]/p["entry_fill"]-1)
                if p["planned_exit"] and day>=p["planned_exit"] and not p["pending"]:
                    p["pending"]="scheduled" if valid_close else 'scheduled_missing_close'
                    cover(p,False,p['pending'])
                elif p['pending'] and valid_close:
                    cover(p,False,p['pending'])
                elif case.get("stop_adverse") is not None and row["high"]*p["factor"]/p["entry_fill"]-1>=case["stop_adverse"]:
                    p["pending"]="risk_stop"
                p["prior_row"]=row
            elif p["planned_exit"] and day>=p["planned_exit"] and not p["pending"]:
                p["pending"]="scheduled_missing_quote"
        eq,req=value(),margin()
        if eq<req:
            for p in opened:p["pending"]="margin"
        equity.append({"date":day,"equity":eq,"margin_required":req,"cash_buffer":eq-req,
                       "gross_exposure":sum(p["remaining"]*p["mark"] for p in opened),"open_names":len(opened),
                       "encumbered_proceeds":sum(p["remaining"]*p["entry_fill"]/p["factor"] for p in opened),
                       "stale_names":sum(p["mark_date"]!=day for p in opened),"margin_breach":eq<req})
    result=[]
    for p in positions:
        unreal=p["remaining"]*(p["entry_fill"]/p["factor"]-p["mark"])
        raw_unreal=p["remaining"]*(p["entry_price"]/p["factor"]-p["mark"])
        net=p["gross_closed"]+unreal-p["borrow"]-p["entry_commission"]-p["exit_commission"]
        result.append({k:v for k,v in p.items() if k not in {"rows","prior_row"}}|{
            "net_pnl":net,"net_return":net/(p["entry_shares"]*p["entry_fill"]),
            "raw_price_pnl":p["raw_closed"]+raw_unreal,"unrealized_pnl":unreal,
            "notional":p["entry_shares"]*p["entry_fill"],
            "commission":p["entry_commission"]+p["exit_commission"],
            "entry_calendar_index":p["entry_calendar_index"],
            "residual_value":p["remaining"]*p["mark"]})
    reconciliation=(equity[-1]["equity"]-initial-sum(p["net_pnl"] for p in result)) if equity else 0
    if abs(reconciliation)>max(1e-6,abs(initial+realized)*1e-10):
        raise AssertionError(f"Account reconciliation failed: {reconciliation}")
    return {"positions":result,"covers":covers,"rejections":rejections,"equity":equity,
            "reconciliation_error":reconciliation,"unresolved":sum(p["remaining"]>0 for p in result)}
