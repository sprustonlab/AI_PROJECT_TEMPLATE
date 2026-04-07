# Injections Phase

In this phase you'll see two things:

1. **Injections** — Workflow rules can modify tool inputs automatically.
   Try running `echo hello` — the injection rule will append text to the command.
   Injections are phase-scoped, so this only happens in this phase.

2. **Phase-scoped rules** — There's a warn-level rule that blocks Write in this phase only.
   Try asking the agent to write a file — it will be blocked here but would succeed in other phases.

To advance: create `tutorial_injections_done.txt` then call `advance_phase`.
