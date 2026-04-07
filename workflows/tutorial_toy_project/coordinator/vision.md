# Vision Phase

The project goal is pre-selected for this tutorial. Present it to the user and get confirmation.

## Present to User

Explain to the user:

> **Project: labmeta — Animal Experiment Metadata Manager**
>
> A CLI tool that manages experiment protocols and per-session metadata with inheritance, validation, and locking.
>
> **Why this project?** It exercises all Project Team features: workflow rules, advance checks, multi-agent delegation, and phase transitions. It's domain-relevant to neuroscience labs and small enough to build in one session.
>
> **What it does:**
> - Define reusable **protocols** (cranial window surgery, injection procedures, etc.)
> - Create per-animal **session records** that inherit from protocols with overrides
> - **Validate** all configs against a schema (strains, coordinates, weight ranges)
> - **Resolve** merged configs showing protocol defaults + session overrides
> - **Lock** completed sessions to prevent accidental edits
>
> **Core commands:** `init`, `create`, `validate`, `resolve`, `lock`, `tree`, `dependents`
>
> **Size:** ~380 lines across 4 Python modules

## After User Confirms

Once the user approves, call `advance_phase` to move to the specification phase.

## If User Wants Changes

This is a tutorial with a pre-selected project. Gently explain that the project is fixed for this tutorial, but they can build their own project using the full Project Team workflow (`/project-team`) after completing this tutorial.
