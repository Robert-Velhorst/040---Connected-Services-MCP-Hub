# Freshdesk current public stable graph candidate

The complete 81-package frozen-graph review found seven newer public releases:
cachetools 7.2.6, cyclopts 5.3.1, FastMCP and FastMCP-slim 4.1.4, ruff 0.17.3,
sse-starlette 3.6.0 and starlette 1.10.0. The copied candidate manifest updates
only the direct FastMCP and ruff declarations. Owned hosted CI uses normal
`uv lock --upgrade --prerelease=disallow`, with no dependency overrides,
replacement packages or lower-version fallback, to determine the whole graph.

The ordinary checked-in application manifest and frozen locks stay intact
during preparation. The candidate job exports its actual resolved manifest,
uv lock and hashed runtime/build/audit requirements for independent review
and a later source freeze. No package lock is fabricated locally.

All four original mocked cases and 47 additional transport cases run unchanged
against the installed candidate. Complete original tracked payloads are hashed
before and after; only the declared generated manifest/lock/export inputs may
change in the worker. All seven installed versions, absence of prereleases,
native Python/YAML versions and the complete dependency audit are recorded.
Any normal-resolution, identity, case, source-integrity or security failure
remains fatal. Reports and generated inputs are retained even after a failure.

No original case/helper/fixture/assertion/selector is edited. Source generation
does not establish full native-source SDK, final-image, Windows, provider or
live-data acceptance. No operator machine environment or server is changed.
