# User Request

The tests for our features are lacking. I found many promised things in the specs but not in the code. I want intent-based tests that use a TUI and the copier into a temp location and run through the features. The guardrail system is not firing as there is no wiring into the settings.json, this is with "all tests passing"!

We also need to know how to change settings.json when it is already there and has values — must merge, not overwrite.

## Approach
TDD: Write failing tests FIRST, then fix the code to make them pass. Red → Green.

## Vision Summary
**Goal:** Write intent-based integration tests that fail today (proving features are broken/unwired), then fix the code to make them pass.
**Approach:** Red → Green. No fixing until the test proves the failure.
**Value:** Current tests validate components in isolation but never prove the system works end-to-end.
**Domain terms:** Intent-based tests, guardrail wiring, settings merge
**Success looks like:** Failing tests that prove guardrails don't fire, settings.json isn't wired, features are dead. A settings.json merge strategy that preserves existing values. Targeted fixes that turn red tests green.
**Failure looks like:** Tests that mock everything and prove nothing. generate_hooks.py that blindly overwrites settings.json. Guardrails that still silently fail.
