Workspace root: C:\Users\werdn\Documents\Investing\Single Stock Investments

Before answering:
1. List all ticker folders at workspace root (exclude `_system`, names starting with `.`)
2. Read _system/agents/MARVIN.md
3. Read _system/memory/MEMORY.md and _system/memory/daily/{today}.md
4. Read _system/portfolio/holdings.md
5. Read _system/frameworks/decision_stack.md; for {TICKER} read valuation.json and open only frameworks from classification.md trigger map (see investment-frameworks.mdc — not the full frameworks folder)
6. Read _system/frameworks/investment_process.md when doing discover/download workflow
7. For ticker {TICKER}: read {TICKER}/README.md if present; scan {TICKER}/research/ for prior work
8. Prefer primary sources in ticker folders (PDFs, INDEX.csv) over memory
9. Write analysis to {TICKER}/research/ — not chat-only
10. Mechanical close: marvin_cloud_refresh.py {TICKER} --date YYYY-MM-DD (do not duplicate its steps)
11. Propose memory updates as [PROPOSED] in daily log only
12. Separate facts / inferences / opinions; cite file paths and page refs where possible
13. New _system/frameworks/*.md files require framework_governance.md checklist
