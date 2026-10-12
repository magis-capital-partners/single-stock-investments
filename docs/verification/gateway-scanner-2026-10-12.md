# Missing SSI code scanner

The `--scan-ssi` flag imported `scan_ib_gateway_clients.py`, which is absent
from this checkout. It therefore raised an unexplained import error after
printing a successful registry-validation line.

The flag now returns exit code 1 with an explicit message: the scanner is
absent, registry validation passed, and **no SSI code scan was performed**.
It never reports scan success for missing code. A missing dependency inside
an available scanner still raises its original error rather than being
misclassified as an absent scanner. Registry-only validation is unchanged.

Tests cover all three cases. The local CLI verification was:

```sh
python _system/scripts/check_ib_gateway_registry.py --skip-mirrors --scan-ssi
```

It exited 1 with the absent-scanner explanation. `--skip-mirrors` confines
this check to the committed registry file in the isolated clone; registry
hash validation remains active. This reads local JSON and performs no broker
connection, probe, restart, order operation or market-data request.

Required pre-PR checks: 1,061 script/extra-suite tests passed, 7 skipped,
56 subtests; the known D1 timer assertion failed, unchanged from main.
Sources, desk briefs, strict reverse splits, strict separations and Short Alpha
checks passed. Graph P3/P6 stayed OK; sparse-checkout E5 omissions and the
pre-existing E7 finding are disclosed. A full-checkout comparison clears E5
but retains E7. Scratch graph baselines were not committed.

Not implemented: restoration of the scanner or a clean result for SSI client
code. This chooses the request's explicit absent-scanner reporting option.
No schema, registry allocation, research conclusion or authority changed.
