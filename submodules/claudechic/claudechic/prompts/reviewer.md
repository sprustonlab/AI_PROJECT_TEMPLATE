# Reviewer - Spawn a Critical Review Agent

Start an agent to review our changes. The agent thinks critically and sends back its review using `tell_agent`.

## Implementation

When invoked:

1. Use `mcp__chic__spawn_agent` to create a review agent with the following characteristics:
   - Name: "review-<topic>" where topic describes what you're working on
   - Path: current working directory
   - Prompt should instruct the agent to:
     - Review recent changes and think critically
     - Use `tell_agent("{agent_name}", ...)` to send its findings back to you when done

2. If the user provided context, include it in the prompt to help focus the review.

3. Before spawning, briefly summarize what you've been working on so you can include that context in the reviewer's prompt.

4. Let the reviewer determine what's important - don't prescribe specific things to check.

5. After spawning the reviewer, you're done for now. The reviewer will send its findings back to you via `tell_agent` when it's ready — no need to check in on it.

## Review Cycle

After receiving feedback from the reviewer:

1. Address the issues raised
2. Use `ask_agent` to request another review from the same reviewer
3. Iterate until both parties agree the changes are in good shape
4. Once agreed, use `mcp__chic__close_agent` to close the reviewer agent

## Example Prompt for the Reviewer Agent

```
Review the recent changes in this repository. Think critically about what could be improved.

[Your context about what you've been working on]
[User context if provided]

When done, use `tell_agent` to send your review back to the agent named "{agent_name}".
If asked for a follow-up review, check that previous issues were addressed and look for any new concerns.
When everything looks good, say so clearly so we can wrap up.
```
