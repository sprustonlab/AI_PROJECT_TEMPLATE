# User Prompt

Design the bootstrapping bridge for AI_PROJECT_TEMPLATE.

The template has a two-phase onboarding: Copier (generation time) and Claude/workflows (runtime). Information gathered in phase one doesn't reliably flow into phase two.

Specific concern raised: PR #18 converts cluster_setup to an executable workflow, but there's no connection between what Copier already asked (ssh_target, scheduler) and what the workflow re-detects. Same pattern exists for git setup, codebase integration, and other setup concerns.

Solve this generically — not just for cluster, but for all seams between template generation and runtime workflows.
