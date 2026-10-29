# Company assumptions and consistent valuations

Judgments run only through the owner's signed-in local Codex CLI: GPT-6.1 Sol
with High reasoning for the author and a separate ephemeral challenger session.
There is no OpenAI API-key execution, Batch execution or Cursor builder call.
The computer and desktop automation must be available for scheduled judgments.
GitHub performs deterministic compilation, shared PV/IRR checks and publication.

## Evidence before judgment

The full-universe financial refresh discovers reports from SEC submissions,
independently of whether the operating-cash-flow XBRL tag has updated. Annual
financials and dated current/interim observations are stored separately in the
same company fundamentals record. Quarterly or year-to-date observations never
silently replace annual cash-flow inputs. The underwriting packet and shared
forecast consume the same report marker and semantic source fingerprint.

Primary financial evidence, verified share units, a current annual baseline and
the latest discovered SEC report plus annual disclosures are checked before any
judgment call. Financial companies do not have a compulsory industrial capex/FCF
template. Funds and special instruments need their own primary claim evidence;
missing disclosures are gaps, not zero values or permission to invent inputs.
International primary coverage remains explicit where an issuer's source adapter
has not supplied verifiable financial observations.

Evidence requests expand bounded contexts from independently discovered primary
reports. Model output cannot choose arbitrary destinations or execute tools. A
repaired evidence packet gets a new hash and review binding. Requests, incomplete
attempts and unresolved critiques persist privately and retry automatically
within the existing call limits; unchanged cached outputs are reused.

## Author, challenge and compile

Initial underwriting excludes old classifications, targets and market prices.
Every economic assumption has evidence, counterevidence, a falsifier, a review
trigger and explicit scenarios. Framework selection, financing scope, working
capital, reinvestment, dilution, terminal proceeds and all material claims must
be reconciled. The independent challenger reviews the entire contract; any major
or critical unresolved finding prevents approval.

Only a previously validated, independently approved contract can be supplied as
an update baseline. Changed evidence is identified explicitly. A new report
requires reconsidering every assumption and the framework. Price changes and
collection clocks alone do not trigger authoring. Expired reviews still require
renewal. Unverified legacy targets never become an assumption baseline.

The model prompt uses a lossless table/dictionary transport. Code round-trips it
and verifies its original hash before launch. Evidence IDs and complete source
contexts survive compression; the challenger receives primary evidence, not an
author's summary of it. Provider receipts preserve actual session IDs and usage.

The approved immutable handoff goes to GitHub. The existing compiler creates the
model directly, records its exact hash and validates it against the approved
contract. No builder inference is needed. Source updates during underwriting,
split/share inconsistencies, stale data, changed proof or failed PV/IRR replay
block replacement of the active model. Publication uses checked PRs and automatic
merge. No human economic review or capital authority is introduced.

## Progress and usage

The policy contains a 16-name pilot spanning operating businesses, a cyclical
with captive finance, a loss-making balance-sheet business, a bank, holding
companies, royalties, international listings and a fund. A fair attempt order
prevents one priority name from permanently monopolizing work. Cohort targets,
actual approvals, completed models, gaps and measured usage are separate fields
in each batch result. Existing call budgets are unchanged.

The installed runtime's `last-run.json` records the actual result. The shared
forecast summary's `data_collection` reports primary/provider coverage and
collection failures separately from available valuations. A successful job is
not a claim that every company has complete evidence or approved assumptions.

Inspect saved local usage without launching a model:

```powershell
python _system/scripts/underwriting_pipeline.py usage --work PATH_TO_RUNTIME/work
```

Unknown provider usage is counted as unknown, not zero. Reasoning is included in
the provider's output count; an actual per-approved-company estimate is withheld
when receipts lack usage. Subscription allowance and credits are not inferred
from API token prices.
