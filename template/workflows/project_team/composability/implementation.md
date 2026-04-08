# Implementation Phase

1. Review Implementer code for composability violations
2. Check: file structure reflects axes
3. Check: no cross-axis branches (`if format == "arrow"` in storage code)
4. Check: seams are clean -- data crosses, assumptions don't
5. Check: protocols defined, not class hierarchies
6. Report violations to Coordinator for Implementer fixes
