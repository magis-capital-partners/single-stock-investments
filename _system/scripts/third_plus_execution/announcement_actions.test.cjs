'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),C=require('./announcement_actions.cjs');
const ctx=()=>{const days=['2024-11-19','2024-11-20','2024-11-21','2024-11-22'];return {prices:{days,index:new Map(days.map((d,i)=>[d,i])),point:(_t,d)=>({open:d<'2024-11-21'?1:15,close:d<'2024-11-21'?1:15})}};};
test('the final approved ratio wins over the authorization range',()=>{
 const clause='At a ratio of 1-for-5 to 1-for-20, as determined by the Board. The Board approved the Reverse Stock Split at a ratio of 1-for-15. The Reverse Stock Split is expected to become effective at 5:01 p.m., Eastern Time, on November 20, 2024.';
 assert.equal(C.inferFactor(clause,clause,'2024-11-20').factor,15);assert.deepEqual(C.tradingDay(ctx(),'2024-11-20',clause),{day:'2024-11-21',confidence:90,after_close:true});
});
test('word-form authorization ranges cannot create a fictitious twenty-one-for-one ratio',()=>{
 const text='The permitted reverse stock split ratio is between one-for-twenty and one-for-fifty. The Board approved a one-for-fifty reverse stock split effective August 20, 2024.';assert.equal(C.inferFactor(text,text,'2024-08-20').factor,50);assert.ok(!C.pairs(text).some(p=>p.factor===21));
});
test('both reverse conventions and word ratios establish exact units',()=>{
 for(const [s,f]of [['220-for-1 reverse stock split',220],['20 to1 Reverse Share Split',20],['a reverse share split on a one-for-two-hundred-fifty basis',250],['a one-for-four reverse stock split',4]])assert.equal(C.inferFactor(s,s,'2024-11-20').factor,f,s);
});
test('parenthetical word numbers preserve the ratio separator and clock times are never ratios',()=>{
 const text='A reverse stock split at a ratio of one (1)-for-twenty-five (25) will become effective at 5:01 p.m. on November 20, 2024.';assert.equal(C.inferFactor(text,text,'2024-11-20').factor,25);assert.deepEqual(C.pairs('The reverse stock split becomes effective at 5:01 p.m.').map(x=>x.factor),[]);
});
test('ADS changes use the change in ordinary shares per ADS, not the new denominator alone',()=>{
 const text='The current ADS Ratio of one (1) ADS to five (5) Ordinary Shares changes to a new ADS Ratio of one (1) ADS to thirty (30) Ordinary Shares. The ADS Ratio Change will be effective on April 21, 2023.';assert.equal(C.adsRatio(text).factor,6);assert.equal(C.inferFactor(text,text,'2023-04-21').factor,6);assert.equal(C.operative(text),true);
});
test('share consolidations and reverse-split adjusted trading clauses establish an action',()=>{
 const text='The Share Consolidation is a ratio of eight (8) pre-consolidation Shares for one (1) post-consolidation Share. Shares will begin trading on a post-consolidation basis on June 4, 2024.';assert.equal(C.inferFactor(text,text,'2024-06-04').factor,8);assert.equal(C.operative(text),true);assert.equal(C.operative('The reverse stock split will begin trading on an adjusted basis giving effect to the reverse stock split on January 15, 2025.'),true);
});
test('ordinary share conversion wording survives a decimal par value and repeated qualifiers',()=>{
 const text='The share consolidation converts six (6) ordinary shares with a par value of $0.003125 each into one (1) ordinary share with par value $0.01875. The Share Consolidation will be effective tomorrow.';assert.equal(C.inferFactor(text,text,'2023-07-27').factor,6);
 const common='The Share Consolidation is four (4) pre-consolidation common shares for every one (1) post-consolidation common share.';assert.equal(C.inferFactor(common,common,'2023-07-07').factor,4);
 assert.equal(C.inferFactor('The Company issued and outstanding common shares at a consolidation ratio of '+common,common,'2023-07-07').factor,4);
});
test('an unrelated quoted investment ticker cannot replace the issuer security',()=>{
 assert.equal(C.sourceSymbol('The Company invests in WonderFi, with the trading symbol “WNDR”.','MOGO').ticker,'MOGO');
 assert.equal(C.sourceSymbol('Title of each class Trading Symbol(s) Name of exchange Common Stock, par value $0.001 MOGO The Nasdaq Capital Market','OTHER').ticker,'MOGO');
 assert.equal(C.sourceSymbol('Title of each class Common Stock "MOGO" Nasdaq Capital Market Redeemable warrants MOGOW Nasdaq Capital Market','OTHER').ticker,'MOGO');
});
test('a price jump does not establish an unmentioned split ratio',()=>{
 assert.equal(C.inferFactor('Common shares will trade on a split-adjusted basis.','No exact exchange ratio is stated.','2024-11-20'),null);
 assert.equal(C.corroborate(ctx(),'X','2024-11-20',15),null);assert.ok(C.corroborate(ctx(),'X','2024-11-21',15));
});
test('a source-bound action moves a duplicate legal-date adjustment rather than applying twice',()=>{
 const x=ctx();x.actions=new Map([['X',new Map([['2024-11-20',{factor:15,priority:3}]])]]);x.prices.priorCache=new Map([['old',1]]);
 C.apply(x,[{ticker:'X',ex_date:'2024-11-21',price_factor:15}]);assert.equal(x.actions.get('X').get('2024-11-20').factor,1);assert.equal(x.actions.get('X').get('2024-11-21').factor,15);assert.equal(x.prices.priorCache.size,0);
});
test('a range-derived wrong ratio on the legal date cannot multiply the final trading-day adjustment',()=>{
 const x=ctx();x.actions=new Map([['X',new Map([['2024-11-20',{factor:5,priority:4}]])]]);C.apply(x,[{ticker:'X',ex_date:'2024-11-21',declared_date:'2024-11-20',price_factor:15}]);assert.equal(x.actions.get('X').get('2024-11-20').factor,1);assert.equal(x.actions.get('X').get('2024-11-21').factor,15);
});
test('funds are excluded from an operating-stock study, not used as another company ticker',()=>{
 assert.equal(C.fundIssuer('ProShares Trust II'),true);assert.equal(C.fundIssuer('United States Natural Gas Fund, LP'),true);assert.equal(C.fundIssuer('Oxford Lane Capital Corp.','As a registered closed -end management investment company, we are regulated.'),true);assert.equal(C.fundIssuer('Healthcare Realty Trust Incorporated'),false);assert.equal(C.fundIssuer('Bollinger Innovations','Investor X is a registered closed-end management investment company.'),false);assert.equal(C.sourceSymbol('under the current symbol “LNKS.”','LNKS').ticker,'LNKS');
 assert.equal(C.fundIssuer('Bollinger Innovations','If the Company is a registered closed-end investment company, the following voting rules would apply.'),false);
});

test('overlapping searches cannot turn twenty-two into two, and pre-reverse wording is supported',()=>{
 const a='The reverse stock split combines every twenty-two ordinary shares into one ordinary share.';assert.equal(C.inferFactor(a,a,'2023-08-21').factor,22);assert.deepEqual([...new Set(C.pairs(a).map(x=>x.factor))],[22]);
 const b='The reverse share split is on the basis of four (4) pre-Reverse Split shares for every one (1) post-Reverse Split share.';assert.equal(C.inferFactor(b,b,'2025-01-02').factor,4);
});

test('a forward split-adjusted trading clause is not a reverse-split candidate',()=>{assert.equal(C.operative('Common stock will begin trading on a split-adjusted basis effective on May 1, 2024.'),false);});

test('a reviewed legal restructuring weeks before trading does not apply the factor twice',()=>{const x=ctx();x.actions=new Map([['X',new Map([['2024-11-01',{factor:40,priority:4}]])]]);C.apply(x,[{ticker:'X',ex_date:'2024-11-21',declared_date:'2024-11-01',price_factor:40}]);assert.equal(x.actions.get('X').get('2024-11-01').factor,1);assert.equal(x.actions.get('X').get('2024-11-21').factor,40);});

test('a later historical reference cannot replace the original action ratio',()=>{assert.equal(C.nearPublication('2025-12-30','2024-12-17'),false);assert.equal(C.nearPublication('2025-02-07','2025-02-11'),true);});
test('the traded class ratio wins over a separate nontraded class ratio',()=>{for(const [a,b]of [[8,2],[7,28]]){const clause=`The share consolidation combines Class A ordinary shares at a ratio of 1-for-${a} and Class B ordinary shares at a ratio of 1-for-${b}, effective May 1, 2026.`;const text=clause+' Class A ordinary shares will begin trading on Nasdaq.';assert.equal(C.inferFactor(clause,text,'2026-05-01').factor,a);assert.match(C.inferFactor(clause,text,'2026-05-01').unit_scope,/requires_separate_class_proof/);}});

test('event reports exclude proxy draft certificates and registration templates',()=>{assert.equal(C.eventReport('DEF 14A'),false);assert.equal(C.eventReport('DEF14A'),false);assert.equal(C.eventReport('S-1'),false);assert.equal(C.eventReport('8-K'),true);assert.equal(C.eventReport('6-K/A'),true);});
test('a ranging-from / up-to authorization cannot replace the final board ratio',()=>{const t='The Reverse Stock Split is at a ratio ranging from 1-for-5 up to a ratio of 1-for-16. The Board approved the Reverse Stock Split at a ratio of 1-for-11 shares.';assert.equal(C.inferFactor(t,t,'2025-03-04').factor,11);});

test('a release dateline is not the later market-effective split date',()=>{const days=['2025-07-14','2025-07-15','2025-07-16','2025-07-17','2025-07-18','2025-07-21'],x={prices:{days,index:new Map(days.map((d,i)=>[d,i]))}},text='MicroAlgo Announces Effective Date for 30-for-1 Share Consolidation. Shenzhen, China, July 14, 2025. At the open of business on July 18, 2025, Class A ordinary shares will begin trading on a split-adjusted basis following the Share Consolidation.';assert.equal(C.schedules(x,{filed_at:'2025-07-14'}, {},text).announced.day,'2025-07-18');});
test('an authorization deadline and an unapproved proxy date are not scheduled actions',()=>{const x=ctx(),deadline='The Share Consolidation shall be effective on any date prior to November 21, 2024, as determined by the board. The effective date when determined shall be announced.';assert.equal(C.schedules(x,{filed_at:'2024-11-19'}, {},deadline).announced,null);const proposal='The Company is hereby soliciting shareholder approval of a Share Consolidation on the effective date of November 21, 2024. The Share Consolidation must be passed by ordinary resolution.';assert.equal(C.schedules(x,{filed_at:'2024-11-19'}, {},proposal).announced,null);});
test('an approved resolution with a fixed effective date is distinct from a proposal',()=>{const text='The shareholders adopted the following resolution: the Share Consolidation will be effective on November 21, 2024, and every 100 ordinary shares will be consolidated into one share.';const s=C.schedules(ctx(),{filed_at:'2024-11-19'}, {},text);assert.equal(s.announced.declared_date,'2024-11-21');assert.equal(s.announced.day,'2024-11-22');});
test('a five-for-one forward ADS split is a 0.2 price-unit factor and not a reverse candidate',()=>{const text='The ADS ratio will change from one (1) ADS representing five (5) common shares to one (1) ADS representing one (1) common share. The ADS Ratio Change becomes effective on February 27, 2025.';assert.equal(C.adsRatio(text).factor,.2);assert.equal(C.inferFactor(text,text,'2025-02-27').factor,.2);});

test('a dated earlier original action release has a bounded, source-specific publication date',()=>{const text='On April 24, 2026, the Company issued a press release announcing the Reverse Stock Split. The stock will trade on April 28, 2026.';assert.equal(C.releaseDate(text,'2026-05-01').day,'2026-04-24');assert.equal(C.releaseDate(text,'2026-06-01'),null);assert.equal(C.releaseDate('Our annual earnings were issued April 24, 2026.','2026-05-01'),null);});

test('only the event body and actual releases survive attached warrant and proxy templates',()=>{
 const body='The Company approved the reverse stock split. ',release='FOR IMMEDIATE RELEASE. Company Announces Reverse Stock Split. ',warrant='Form of Warrant: hypothetical reverse stock split July 22, 2026.',text=body+'SIGNATURES Pursuant to the requirements. Exhibit 99.1 '+release+'Exhibit 10.1 '+warrant;
 const selected=C.eventSections(text).join(' ');assert.ok(selected.includes(body.trim()));assert.ok(selected.includes(release.trim()));assert.ok(!selected.includes(warrant));
 assert.deepEqual(C.eventSections('Proxy statement: the Company is hereby soliciting shareholder approval of a reverse stock split.'),[]);
});
test('a warrant exercise start is not a split trading date, and another issuer owns its own action',()=>{
 assert.equal(C.dateRole('2026-07-22','The warrants start on July 22, 2026, subject to a reverse split adjustment.'),null);
 assert.equal(C.otherIssuer('Glatfelter common stock will begin trading after a reverse stock split on November 4, 2024.','2024-11-04','Berry Global Group, Inc.'),true);
 assert.equal(C.otherIssuer('The Company common stock will begin trading after a reverse stock split on November 4, 2024.','2024-11-04','Berry Global Group, Inc.'),false);
});
test('a missing price anchor requires an explicitly completed action rather than a merger or proposal',()=>{
 const x={prices:{days:['2024-11-20','2024-11-21'],index:new Map([['2024-11-21',1]]),point:()=>null},auction:()=>({})};
 assert.ok(C.completedWithoutAnchor(x,'X','2024-11-21','The Company completed a reverse stock split.','2024-11-22'));
 assert.equal(C.completedWithoutAnchor(x,'X','2024-11-21','The Company completed a merger and would effect a reverse stock split.','2024-11-22'),null);
 x.auction=()=>({close:1});assert.equal(C.completedWithoutAnchor(x,'X','2024-11-21','The Company completed a reverse stock split.','2024-11-22'),null);
});

test('outstanding share-count prose cannot invent a multi-million-for-one ratio',()=>{
 const text='The Board approved a 10:1 reverse split. Each ten (10) pre-split shares of Freight Technologies Inc. shares will combine into one (1) ordinary share without any action on the part of the holders, and the number of outstanding ordinary shares will be reduced from 32,713,866 to 3,271,386 ordinary shares.';
 assert.equal(C.inferFactor(text,text,'2023-03-24').factor,10);assert.deepEqual([...new Set(C.pairs(text).map(p=>p.factor))],[10]);
});
test('two-and-a-half consolidation wording preserves exact decimal share units',()=>{
 const t='The share consolidation is on the basis of one (1) post-consolidation common share for every two and a half (2.5) pre-consolidation common shares.';assert.equal(C.inferFactor(t,t,'2025-08-26').factor,2.5);
});
test('a superseded announcement date and ratio cannot replace the revised actual action',()=>{
 const text='The Board approved a consolidation ratio of 1-for-30. The Share Consolidation will become effective on November 21, 2024. This supersedes the Company’s prior announcement that a 1-for-40 share consolidation would become effective on November 20, 2024. Accordingly, the previously announced 1-for-40 ratio and November 20, 2024 effective date are no longer applicable.';
 const s=C.schedules(ctx(),{filed_at:'2024-11-19'},{},text);assert.equal(s.announced.declared_date,'2024-11-21');assert.equal(s.announced.day,'2024-11-22');assert.equal(C.inferFactor(s.announced.clause,text,s.announced.declared_date).factor,30);assert.deepEqual(C.supersededDates(text),['2024-11-20']);
 const x=ctx();x.actions=new Map([['X',new Map([['2024-11-01',{factor:40}]])]]);C.apply(x,[{ticker:'X',ex_date:'2024-11-21',price_factor:30,superseded_dates:['2024-11-01']}]);assert.equal(x.actions.get('X').get('2024-11-01').factor,1);
});
test('hypothetical share-combination events and a different fund series are not operating-stock announcements',()=>{
 assert.equal(C.operative('The offering closed after a Share Combination Event. Its registration statement was declared effective on May 18, 2026.'),false);assert.equal(C.fundIssuer('VS Trust'),true);
});

test('a repeated date is classified at its own occurrence rather than an earlier legal-date mention',()=>{
 const text='The reverse stock split was effective on November 21, 2024, at 12:01 a.m. Eastern Time. The common stock is expected to begin trading on a post-split basis on November 21, 2024, under a new CUSIP.';const s=C.schedules(ctx(),{filed_at:'2024-11-20'},{},text);assert.equal(s.announced.kind,'explicit_trading_date');assert.equal(s.announced.day,'2024-11-21');
});

test('weekday-prefixed and Beginning-on market dates remain explicit first trading days',()=>{
 for(const clause of ['The Share Consolidation is complete. The ordinary shares will begin trading on a split-adjusted basis on Thursday, November 21, 2024.','The Share Consolidation is complete. Beginning on November 21, 2024, the ordinary shares will trade on a split-adjusted basis.']){const s=C.schedules(ctx(),{filed_at:'2024-11-20'},{},clause);assert.equal(s.announced.kind,'explicit_trading_date');assert.equal(s.announced.day,'2024-11-21');}
 const clause='The reverse split is effective after the market close on November 20, 2024. Common stock will begin trading on November 21, 2024.';assert.equal(C.tradingDay(ctx(),'2024-11-21',clause,'explicit_trading_date').day,'2024-11-21');
});

test('a past completed split cannot turn a later warrant-update release or registration date into a new split',()=>{
 const text='The reverse stock split became effective on November 20, 2024. The Company is working to update warrant records. On November 21, 2024, the Company issued a press release announcing warrant exercises.';assert.equal(C.schedules(ctx(),{filed_at:'2024-11-21'},{},text).clauses.some(c=>c.date==='2024-11-21'),false);
 const registration='The reverse stock split occurred previously. The registration statement on Form S-1 was declared effective on November 21, 2024.';assert.equal(C.schedules(ctx(),{filed_at:'2024-11-21'},{},registration).announced,null);
});
test('an explicit change of effective time links the old date to the revised action',()=>{
 const text='The Board previously approved the Reverse Stock Split at a ratio of 1-for-15 to become effective at 12:01 a.m. PT on November 20, 2024. The Board determined to change such effective time to November 21, 2024 at 12:01 a.m. PT. The common stock will begin trading on a split-adjusted basis on November 21, 2024.';assert.deepEqual(C.supersededDates(text),['2024-11-20']);assert.equal(C.schedules(ctx(),{filed_at:'2024-11-19'},{},text).announced.day,'2024-11-21');
});

test('a named synthetic repurchase with an explicitly defined reverse split is eligible before the exact ratio is published',()=>{
 const text='The synthetic share repurchase plan combines a direct capital repayment with a reverse stock split. The synthetic share repurchase will become effective on November 21, 2024.';assert.ok(C.schedules(ctx(),{filed_at:'2024-11-19'},{},text).announced);
 assert.equal(C.schedules(ctx(),{filed_at:'2024-11-19'},{},'The synthetic share repurchase will become effective on November 21, 2024.').announced,null);
 const release='Exhibit 99.1 QIAGEN to return capital through a synthetic share repurchase that combines direct repayment with a reverse stock split. '+text;assert.ok(C.eventSections('Cover report. SIGNATURES Pursuant to the Exchange Act. '+release).join(' ').includes(release));
});
test('an original issuer dateline with today-announced action wording supplies a date without inventing an hour',()=>{
 const text='Venlo, The Netherlands, November 19, 2024 – QIAGEN N.V. (NYSE: QGEN) today announced a synthetic share repurchase combining capital repayment and a reverse stock split.';assert.equal(C.releaseDate(text,'2024-11-20').day,'2024-11-19');
});
