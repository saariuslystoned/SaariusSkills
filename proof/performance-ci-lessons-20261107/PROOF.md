# Performance CI reference update

Base: `820a8397b559a8ae865bf2531fb6b420812562f1`.

Integrated metric denominators, natural job admission, artifact retry lifecycle,
case identity, timing granularity and build-consumer tracing into the two
existing references. Entrypoint, capture helper/schema, catalog and tests remain
unchanged. No new performance result is claimed.

Duplication review: existing comparability, cache-cost and billing guidance stays
in place; additions cover the distinct decision mistakes above rather than a
second checklist. No private case-study paths, topology or session history are
included.

Validation (Linux, Python 3.14.8): skill validation passes. Packaging (33 tests)
and full suite (229 tests, 129.806s) report the same two failed subcases in the
unchanged Linux shell-capture test: `/usr/bin/time` is absent. Capture helper,
protocol and packaging-test bytes match the base. Whitespace, links and scope
pass. No test waiver or environment installation; supported-platform CI remains
pending.
