/* Research scenarios are separate from the approved valuation and capital gates. */
(function (global) {
  'use strict';
  const cases = ['bear', 'base', 'bull'];
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const positive = x => finite(x) && x > 0;
  const day = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
  const years = (from, to) => (Date.parse(to) - Date.parse(from)) / 86400000 / 365.25;
  function anniversary(from, n) {
    const d = new Date(from + 'T00:00:00Z'), month = d.getUTCMonth();
    d.setUTCFullYear(d.getUTCFullYear() + n);
    if (d.getUTCMonth() !== month) d.setUTCDate(0); // February 29 -> February 28.
    return d.toISOString().slice(0, 10);
  }
  function monthAfter(from,n) {
    const d=new Date(from+'T00:00:00Z'),original=d.getUTCDate();
    d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+n);
    const last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();
    d.setUTCDate(Math.min(original,last));return d.toISOString().slice(0,10);
  }
  function presentValue(flows, rate, asOf) {
    if (!day(asOf) || !finite(rate) || rate <= -1 || flows.some(p => !day(p.date) || p.date <= asOf || !finite(p.amount))) return null;
    const value = flows.reduce((sum, p) => sum + p.amount / (1 + rate) ** years(asOf, p.date), 0);
    return finite(value) ? value : null;
  }
  function irr(price, flows, asOf) {
    // Only a conventional purchase followed by nonnegative proceeds has one root.
    if (!positive(price) || !day(asOf) || !flows.length || flows.some(p => !day(p.date) || p.date <= asOf || !finite(p.amount) || p.amount < 0)) return null;
    if (!flows.some(p => p.amount > 0)) return -1;
    let lo = -0.99999999, hi = 1;
    while (presentValue(flows, hi, asOf) > price && hi < 1e8) hi *= 2;
    if (presentValue(flows, lo, asOf) < price || presentValue(flows, hi, asOf) > price) return null;
    for (let i = 0; i < 180; i++) {
      const mid = (lo + hi) / 2;
      if (presentValue(flows, mid, asOf) > price) lo = mid; else hi = mid;
    }
    const result = (lo + hi) / 2;
    return finite(result) ? result : null;
  }
  function calculate(model, edits = {}) {
    const input = {...model.inputs, ...edits.inputs};
    const fixed = ['payoff','dated_cashflows'].includes(model.method);
    const required = fixed ? ['entry_price'] : ['entry_price', 'anchor'];
    const gaps = [...(model.blockers || [])];
    if (!['owner_cash','earnings','book','nav','transition','payoff','dated_cashflows','preferred'].includes(model.method)) gaps.push('A supported model method is required');
    for (const id of required) if (!positive(input[id])) gaps.push(id === 'anchor' ? model.anchor_label + ' is required' : 'A positive entry price is required');
    if (!day(input.entry_date)) gaps.push('A dated entry price is required');
    if (!finite(input.discount_rate) || input.discount_rate <= 0 || input.discount_rate > 1) gaps.push('Required return must be above 0% and at most 100%');
    if (!Number.isInteger(input.horizon) || input.horizon < 1 || input.horizon > 30) gaps.push('Forecast horizon must be 1–30 whole years');
    const results = {};
    for (const name of cases) {
      const c = {...model.cases?.[name], ...edits.cases?.[name]}, errors = [...new Set(gaps)];
      const percent = (key, min, max) => {if (!finite(c[key]) || c[key] < min || c[key] > max) errors.push(key.replaceAll('_', ' ') + ' is outside its supported range');};
      if(model.method==='preferred') {
        percent('coupon_paid',0,1);
        if(!finite(c.exit_price)||c.exit_price<0)errors.push('An assumed future preferred sale price is required');
      } else if (model.method === 'dated_cashflows') {
        percent('scale',0,3);
        if (!Array.isArray(c.cashflows) || !c.cashflows.length || c.cashflows.some(p=>!day(p.date)||p.date<=input.entry_date||!finite(p.distribution)||!finite(p.terminal)||p.distribution+p.terminal<0)) errors.push('The source schedule needs future dated, nonnegative net cash flows');
      } else if (model.method !== 'payoff') {
        if (!finite(c.exit_multiple) || c.exit_multiple < 0 || c.exit_multiple > 100) errors.push('Exit multiple must be between 0 and 100');
        if (model.method === 'owner_cash') {percent('reinvestment', 0, 1); percent('incremental_roic', -0.9, 1);}
        else if (model.method === 'book') {percent('roe', -0.9, 1); percent('payout', 0, 1);}
        else {percent('growth', -0.9, 1); if (model.method === 'nav') percent('distribution_yield', 0, 1); else percent('payout', 0, 1);}
        if (model.method === 'transition') {percent('target_margin', 0, 1); percent('dilution', 0, 1);}
      } else if (!finite(c.payoff) || c.payoff < 0 || !day(c.payoff_date) || c.payoff_date <= input.entry_date) errors.push('A nonnegative future payoff and its future date are required');
      const flows = []; let terminal = null;
      if (!errors.length) {
        let anchor = input.anchor;
        if(model.method==='preferred') {
          for(let month=1;month<=input.horizon*12;month++) {
            const distribution=input.anchor*c.coupon_paid/12,sale=month===input.horizon*12?c.exit_price:0;
            flows.push({date:monthAfter(input.entry_date,month),distribution,terminal:sale,amount:distribution+sale,anchor:input.anchor*c.coupon_paid});
          }
          terminal=c.exit_price;
        } else if (model.method === 'dated_cashflows') {
          for (const p of c.cashflows) flows.push({date:p.date,distribution:p.distribution*c.scale,terminal:p.terminal*c.scale,amount:(p.distribution+p.terminal)*c.scale,anchor:(p.distribution+p.terminal)*c.scale});
          terminal=flows.reduce((sum,p)=>sum+p.terminal,0);
        } else if (model.method === 'payoff') {
          terminal = c.payoff; flows.push({date: c.payoff_date, distribution: 0, terminal, amount: terminal, anchor});
        } else for (let year = 1; year <= input.horizon; year++) {
          let distribution, metric;
          if (model.method === 'owner_cash') {anchor *= 1 + c.reinvestment * c.incremental_roic; metric = anchor; distribution = anchor * (1 - c.reinvestment);}
          else if (model.method === 'book') {const earnings = anchor * c.roe; distribution = Math.max(0, earnings * c.payout); anchor += earnings - distribution; metric = anchor;}
          else if (model.method === 'nav') {distribution = Math.max(0, anchor * c.distribution_yield); anchor *= 1 + c.growth; metric = anchor;}
          else if (model.method === 'transition') {anchor *= (1 + c.growth) / (1 + c.dilution); metric = anchor * c.target_margin; distribution = 0;}
          else {anchor *= 1 + c.growth; metric = anchor; distribution = Math.max(0, anchor * c.payout);}
          terminal = year === input.horizon ? Math.max(0, metric * c.exit_multiple) : 0;
          flows.push({date: anniversary(input.entry_date, year), distribution, terminal, amount: distribution + terminal, anchor: metric});
        }
      }
      if (flows.some(p => !finite(p.amount) || p.amount < 0)) errors.push('Cash flows could not be calculated');
      const value = errors.length ? null : presentValue(flows, input.discount_rate, input.entry_date);
      const rate = errors.length ? null : irr(input.entry_price, flows, input.entry_date);
      results[name] = {value, irr: rate, upside: value === null ? null : value / input.entry_price - 1, terminal: errors.length ? null : terminal, flows: errors.length ? [] : flows, gaps: [...new Set(errors)]};
    }
    return {inputs: input, cases: results, ready: cases.every(c => results[c].irr !== null)};
  }
  global.StockValuation = {cases, calculate, irr, presentValue, anniversary, monthAfter};
  if (typeof module !== 'undefined') module.exports = global.StockValuation;
})(typeof window !== 'undefined' ? window : globalThis);
