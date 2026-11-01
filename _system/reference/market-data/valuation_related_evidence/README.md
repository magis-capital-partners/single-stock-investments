# Related issuer evidence

The underwriting collector stores source-bound acquisition-target evidence here.
Targets must have a verified SEC issuer identity and an exact name match in the
parent's transaction disclosure. Keep each target's fiscal period, currency and
source hashes distinct from the parent's. Target shares are never a substitute
for the parent's shareholder denominator.

This tracked file also keeps the optional cache present in sparse automated
checkouts before any company needs acquisition evidence, so the normal refresh
can stage its publication paths when the cache has no JSON records yet.
