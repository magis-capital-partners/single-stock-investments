"""Independent account replay with partial covers and explicit residual liabilities."""
from collections import defaultdict
from datetime import date
from math import floor

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
    def comm(q):
        return max(spec["commission"]["minimum_per_side"], q * spec["commission"]["per_share_per_side"])
    def value():
        return initial + realized + sum(p["remaining"] * (p["entry_fill"]/p["factor"]-p["mark"]) for p in opened)
    def margin():
        return sum(maintenance(p["remaining"],p["mark"],account["house_margin"]) for p in opened)
    def borrow_fee(p, days):
        nonlocal realized
        fee=rounded_collateral(p["remaining"],p["mark"])*p["rate"]*days/spec["borrow_collateral"]["day_basis"]
        p["borrow"]+=fee;realized-=fee
    for i,day in enumerate(calendar):
        used_volume=defaultdict(float)
        for p in list(opened):
            elapsed=(date.fromisoformat(day)-date.fromisoformat(p["fee_until"])).days
            borrow_fee(p,elapsed)
            p["fee_until"]=day
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
                p["mark"]=row["open"];p["mark_date"]=day
        # Opening gaps affect account buying power before today's entries.
        if value()<margin():
            for p in opened:p["pending"]="margin"

        def cover(p,at_open,reason):
            nonlocal realized
            row=p["rows"].get(day)
            if not row:return
            available=max(0,account["max_participation"]*row["volume"]-used_volume[p["ticker"]])
            requested=p["remaining"]
            if constrain_exits:
                q=floor(min(requested,available)+1e-9)
            else:
                q=requested
            if q<=0:
                p["blocked_cover_days"]+=1
                return
            reference=row["open" if at_open else "close"]
            prior=p["prior_row"]
            spread=full_spread(prior.get("high"),prior.get("low"),cost["spread_floor"],cost["range_fraction"])
            before_slip=reference+spread/2
            fill=before_slip*(1+cost["extra_slippage_bps_per_side"]/10000)
            commission=comm(q)
            if p["borrow"]==0:borrow_fee(p,1)
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
            locate=None
            if not reason and case.get("borrow_policy")=="strict":
                locate=_locate(borrows,lead["ticker"],day,spec["borrow_max_age_hours"])
                approval=locate[3] if locate and len(locate)>3 else {}
                if (not locate or not locate[1] or locate[1]<=0 or locate[2] is None or locate[2]<0
                        or not isinstance(approval,dict) or approval.get('approved') is not True or not approval.get('reference')):
                    reason="no_fresh_locate_and_fee"
                else:rate=float(locate[2])
            row=lead["rows"][day]
            prior=lead["prior_row"]
            spread=full_spread(prior.get("high"),prior.get("low"),cost["spread_floor"],cost["range_fraction"])
            before_slip=row["open"]-spread/2
            fill=before_slip*(1-cost["extra_slippage_bps_per_side"]/10000)
            if not reason and (fill<=0 or row["volume"]<=0):reason="no_executable_entry_proxy"
            eq=value()
            if not reason:
                unit_margin=max(.5*fill,maintenance(1,row["open"],account["house_margin"]))
                available=max(0,eq*(1-account["buffer_fraction"])-margin()-spec["commission"]["minimum_per_side"])
                size=min(account["target_notional"]/fill,max(0,eq)*account["position_fraction"]/fill,
                         account["max_participation"]*lead["adv"],
                         available/(unit_margin+max(0,row["open"]-fill)+spec["commission"]["per_share_per_side"]))
                if locate:size=min(size,float(locate[1]))
                size=floor(max(0,size))
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
               "announcement_category":lead.get('announcement_category','fixture'),
               "entry_calendar_index":i,"planned_exit":planned,"entry_shares":size,"remaining":float(size),
               "entry_price":row["open"],"entry_fill":fill,"factor":1.0,"mark":row["open"],"mark_date":day,
               "rate":rate,"borrow":0.0,"fee_until":day,"entry_commission":comm(size),"exit_commission":0.0,
               "locate_reference":locate[3]['reference'] if locate else None,
               "spread_cost":size*spread/2,"slippage_cost":size*(before_slip-fill),
               "gross_closed":0.0,"raw_closed":0.0,"pending":None,"status":"open","last_cover_date":None,
               "partial_covers":0,"blocked_cover_days":0,"fractional_obligation_seen":False,"rows":lead["rows"],
               "prior_row":prior,"score":lead["fundamental"],"source_url":lead.get("source_url"),"mae":0.0}
            realized-=p["entry_commission"];positions.append(p);opened.append(p)
        for p in list(opened):
            row=p["rows"].get(day)
            if row:
                p["mark"]=row["close"];p["mark_date"]=day
                p["mae"]=max(p["mae"],row["high"]*p["factor"]/p["entry_fill"]-1)
                if p["planned_exit"] and day>=p["planned_exit"] and not p["pending"]:
                    p["pending"]="scheduled";cover(p,False,"scheduled")
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
