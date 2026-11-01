Investor disclosure coverage
============================

13F histories, registered-fund N-PORT reports, public daily portfolios, issuer
ownership registers and investor letters are separate dated sources. No source
is assumed to represent the complete worldwide portfolio of its manager.

`public_holdings_sources.json` identifies official public feeds. The Public daily
fund holdings workflow refreshes them twice per weekday, independently of the
long SEC historical backfill. It discovers all Horizon Kinetics ETFs from the
provider's product directory. Sequoia uses the live public Filepoint JSON feed,
not the launch-date fallback CSV. Akre and Pabrai Wagons use the publisher's
complete daily CSVs, including foreign, cash and zero-value lines.
The N-PORT source registry explicitly tracks the predecessor mutual funds and
successor ETFs for Akre and Pabrai Wagons by verified SEC series ID. Their public
report histories supplement the daily observations without joining fund books.

The private vault retains originals and dated portfolios under
`dashboard-private/public-holdings`. The public receipt selects a checksum-
verified snapshot. A failed source retains its previous dated observations and
records a review item. Deployment fails if the selected archive is missing or
corrupt. This lane does not read letters or connect to a broker.

KAP issuer registers disclose direct ownership in specific companies above the
register's threshold. Their percentages are ownership of the issuer, not fund
portfolio allocations. They have an observation date unless the source supplies
an explicit reporting date. Absence from a later register is not an inferred exit.

Letters are reprocessed from the authorized corpus during deployment. Explicit
corpus paths read that corpus's own text; a similarly named file in another
vault cannot supply the holdings or identity evidence. Explicit
dated valuation tables retain their named vehicle and table date. Missing tickers
and weights remain unknown. Foreign publisher identifiers are preserved because
Bloomberg symbols do not always match local exchange trading symbols.

`required_managers.json` captures every manager mentioned in PR #1282, including
Pershing Square's successor filer. Tests verify their SEC identities. The staged
directory includes a per-manager source audit, all available filing quarters and
disclosure counts. Sequoia Fund letters that name Ruane Cunniff as adviser belong
to that manager; Sequoia Capital's separate filing history is never combined.
Pinned publisher classifications are rechecked against the current letter
headers. A company letterhead before a salutation can identify that document's
manager; companies discussed in the body cannot. Only declared aliases shared
by every eligible record can link an entire publisher to a filing manager.
Ambiguous headers stay in review. Known filing managers are never combined by
a name match.

To refresh public sources locally, use an isolated research-vault checkout:

    python _system/scripts/public_holdings.py --archive <vault>/dashboard-private/public-holdings

Persist that archive in the private vault before publishing the resulting
`dashboard/data/holdings/public_sources_receipt.json`. The receipt contains no
letter text or private source membership. Historical daily portfolios begin with
the first available preserved disclosure; unobserved past days are not fabricated.
