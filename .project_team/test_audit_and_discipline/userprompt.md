# User Prompt

## Raw Request
Fix slow/flaky tests, enforce disciplined test runs with saved results, and critically audit test quality.

## Vision Summary (Approved)

| Field | Detail |
|---|---|
| **Goal** | Fix slow/flaky tests, enforce disciplined test runs with saved results, and critically audit test quality. |
| **Value** | A 2-min test run fails, output is truncated to ~10 lines, the agent retries blind — pure waste. Tests that mirror implementation instead of intent give false confidence and break on every refactor. Both problems compound. |
| **Domain Terms** | **xdist** — pytest parallel runner; **intent test** — tests the *why* (behavior/contract); **implementation test** — tests the *how* (fragile, coupled to internals); **test results artifact** — timestamped saved output from a full suite run. |
| **Success** | 1. A Claude Code hook that blocks bare `pytest` without a file output — forces all full runs to save timestamped results to `test-results/`. 2. Slow and xdist-incompatible tests identified and tagged/fixed. 3. An honest, critical audit of every test: intent-based vs. implementation-based, with concrete recommendations. |
| **Failure** | We "fix" a few tests superficially, don't enforce the save-results rule, and the audit is a rubber stamp that says "tests look fine" without honest critique. |

## Constraints
- pytest + pytest-xdist
- Test results must be timestamped (e.g., `test-results/2026-04-10_143022.log`), not "latest"
- Bare `pytest` streaming to terminal without saving to a named file must be BLOCKED via hook
- Audit scope: ALL test files
