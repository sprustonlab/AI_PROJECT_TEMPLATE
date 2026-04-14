# Specification Phase

1. Wait for all Leadership agents to report findings
2. If UI-heavy project, spawn UIDesigner
3. If Researcher active, request prior art investigation
4. Composability spawns axis-agents for deep review
5. Synthesize all findings into specification document
   - Keep the spec strictly operational: what to build, how it connects, what constraints apply
   - Move all non-operational content to a separate appendix file (e.g. SPEC_APPENDIX.md): architecture decision rationale, rejected alternatives, "what NOT to do" lists, and historical context
   - Research findings belong in their own files (e.g. RESEARCH.md), not in the spec or appendix
   - Implementer and test agents read the spec -- if content would confuse them or waste their attention, it belongs in the appendix or a separate file
6. Present to user

Handle user response:
- **Approve** -> proceed to implementation
- **Modify** -> incorporate feedback, re-present
- **Redirect** -> adjust approach, re-present
- **Fresh Review** -> close Leadership, spawn fresh team
