"""Re-score the activism lens from index.json. Usage: python3 score.py
Tallies rule_cases (right / wrong / mixed) per rule. Edit rule_cases when a case resolves, then run this
and copy the new scores into lenses/activism.md §2 with a dated change-log line."""
import json,os
p=os.path.join(os.path.dirname(os.path.abspath(__file__)),'index.json')
idx=json.load(open(p))
for rid,cases in sorted(idx['rule_cases'].items()):
    f=len(cases); r=sum(c['result']=='right' for c in cases); w=sum(c['result']=='wrong' for c in cases); m=f-r-w
    hr=f"{100*r/(r+w):.0f}%" if r+w else '-'
    print(f"{rid}: fired {f} / right {r} / wrong {w} / mixed {m}  hit {hr}{'  (untested, n<5)' if f<5 else ''}")
