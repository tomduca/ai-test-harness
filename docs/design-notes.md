# Design notes

Running log of design decisions, known limitations and findings. The README summarizes it.

## Decisions

- **Python + uv, src layout, Python 3.14.** Local dev on macOS (Intel); CI on Linux.
- **Provider-agnostic LLM chain.** `LLM_MODELS` is an ordered `provider:model` list with
  fallbacks across providers, bounded timeouts and retries. Groq is primary: the Gemini free
  tier allowed only 20 requests/day for gemini-3.8-flash and returned frequent 503s.
- **Gherkin parsed with the official Cucumber parser** into pickles; stable scenario IDs
  (`feature::scenario[row]`) for traceability across runs; duplicate scenario names rejected.
- **One graph run per scenario.** `TypedDict` state with Pydantic payloads; bounded retry loop
  (`MAX_ATTEMPTS`) from evaluator back to planner on `test_defect` only.
- **Closed action vocabulary** (Pydantic discriminated union) instead of LLM-generated code.
  Site-relative paths only. The vocabulary grows only when a spec needs it.
- **Blind planner** (no DOM) for the MVP, so the impact of an ARIA snapshot can be measured later.
- **Two validation layers in the planner:** schema (Pydantic) + semantic checks (step coverage,
  outcome steps asserted) with bounded self-correction.
- **Executor:** deterministic dispatcher; stops on failed interactions, soft assertions otherwise;
  Playwright trace + final screenshot per attempt; 5 s action timeout. Tested against an in-memory
  fake site via `context.route()`.
- **Evaluator:** deterministic rules on Playwright error signatures. Priority
  infra_error > test_defect > product_bug; unknown failures become "unclassified" product bugs.
  - **Fallback models must be qualified for the schema, not just available.** With full error
  reporting, qwen3.8-27b turned out to invent its own locator schema and gemini-3.5-flash-lite
  produced invalid plans; both were removed from the chain. Rate limiting is per request, but
  the binding Groq limit is tokens per minute (each call carries the full JSON schema).
  - **Two quality gates.** pre-commit runs the project's own ruff (from `uv.lock`) on staged files;
  the `checks` workflow runs lint + all harness tests on Linux for every push and PR. CI caught a
  file committed before the hook existed. Dependabot keeps actions and dependencies updated, and
  every update PR goes through `checks`.
  - **Infra errors are retried once per run, after 60 s; nothing else ever is.** A run in CI ended
  in `infra_error` because Groq hit its tokens-per-minute limit while Gemini returned 503. Retried
  scenarios are flagged in the output and the job summary. Product bugs are never retried, so
  intermittent bugs stay visible.
- **API contracts double as LLM context.** `@api` scenarios get docs/contracts/*.md in the
  planner prompt, so specs stay free of endpoints and field names. All 17 API scenarios passed
  on the first attempt with a blind planner.
- **expect_status is a gate.** An unexpected status skips the body checks that follow: their
  failures would be cascades of the real finding.
  - **Proven-plan cache.** A plan that passed is reused while the scenario, the prompt, the
  vocabulary and the contracts are unchanged (hash key); retries always replan. Only `pass`
  plans are cached: a product_bug plan may be a misclassified test defect, and caching it would
  repeat the mistake daily. Motivated by a CI run where 17 of 28 scenarios hit the Groq
  tokens-per-day limit. In CI the cache is restored/saved separately (`if: always()`), because
  the e2e job fails by design when it finds bugs. Next step (stage D): approved plans in the repo.

## Known limitations

- A removed element and a wrong locator look the same ("no elements"): classified as
  `test_defect`. Motivates the LLM-as-judge stage.
- Console-error checks include third-party embeds (YouTube, Clublog): needs a domain filter.
- Lazy-loaded images are not checked unless they were loaded.
- The model that produced each plan is not recorded yet.
- LLM plans are not deterministic: the same scenario can get different locators on different runs. Each attempt's plan.json is kept as evidence.
- Free-tier rate limits: runs are paced client-side (`LLM_REQUESTS_PER_MINUTE`). Results can vary
  between runs when providers are saturated; such failures are reported as `infra_error`.

## Findings on the system under test

- "Mapa" menu item is redundant: `#mapa` points to an `<h3>` inside "En el aire". Detected
  by the harness on its first real run.
- `/api/qso` returns an undocumented `call_logged` field (contract v0.1).
- The home page takes ~5 s to reach the `load` event (third-party embeds).
- First full run: 8 scenarios, 6 pass, 2 product_bug (one was a harness false positive, see above).
- A Dependabot PR failed CI because its branch predated a formatting fix on `main`, not because of
  the update itself. Confirmed from the CI log, then regenerated with `@dependabot recreate`.
  Release notes for checkout v7 reviewed: the breaking change (fork PRs in `pull_request_target`)
  does not affect this repo, which uses `pull_request`.
  - The API accepts `333AAAZZZ` as a callsign (200, not found) while the UI rejects it: the API
  validation is looser than the UI's.

## Bugs found in the harness itself

- The site-path regex accepted `"/\n"`; found from real LLM output, fixed with a regression test.
- Locators used Playwright's substring matching (`exact=False`): "EN" clicked "En el aire" on the
  real site, and the wrong URL two steps later was reported as a product bug (cascading false
  positive). Fixed: whole-text, case-insensitive matching; regression tests on the fake site.
  - `action` had a default, so it was optional in the JSON schema; gpt-oss in `json_schema` mode
  omitted it and plans could not be parsed. Fixed: required in the LLM-facing schema only.
  - Cascading misclassification (second occurrence): 333aaazzz returned 200; the check for the
  `error` field then failed, was classified as test_defect and won over the real product bug.
  Fixed by making expect_status a gate. Deterministic rules judge failures one by one and miss
  cause-effect chains: a core motivation for the LLM-as-judge stage.