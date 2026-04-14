# Analyze Phase

Goal: Classify all unclassified messages in the corrections database.

---

## Input

You receive a JSON array of unclassified messages from `audit.py unclassified`.
Each message has:

- `id` -- database ID (use as `message_id` in output)
- `user_text` -- the user's message
- `context_before` -- what the agent said/did before this message
- `context_after` -- how the agent responded after this message
- `session_id`, `agent_name`, `phase_id` -- context about where this happened
- `regex_score` -- keyword-based correction score (0.0-1.0)
- `regex_indicator` -- best regex pattern match label (nullable)

---

## How to Classify

For each message, use the 3-message context window:

1. Read `context_before` -- what did the agent do?
2. Read `user_text` -- what did the user say?
3. Read `context_after` -- did the agent change course?

Ask: "Is the user correcting, redirecting, or expressing dissatisfaction with
what the agent just did?"

- If YES: assign one of the 6 categories and a confidence level.
- If NO: mark as not a correction.

Use `regex_score` and `regex_indicator` as supplemental signals. A high regex
score suggests the message contains correction keywords, but context matters
more than keywords.

---

## Process All Messages

Classify every message in the input array. Do not skip any.

**Batch store -- one call for the entire chunk.** Collect all classifications
into a single JSON array and pipe it to `store-classifications` in one call.
Do NOT call `store-classifications` once per message -- that is slow and wastes
tool invocations.

```
echo '[{"message_id":42,"is_correction":1,"category":"factual_correction","confidence":"high"},{"message_id":43,"is_correction":0,"category":null,"confidence":null}]' | python scripts/audit/audit.py store-classifications
```

The entire chunk goes in one array, one pipe, one command.

Report a summary when done:
> "Classified N messages. Found M corrections (P high confidence, Q medium, R low)."

---

## Chunking

If the input includes `"has_more": true`, report that to the auditor so it
can fetch the next chunk. Continue classifying until all chunks are processed.
