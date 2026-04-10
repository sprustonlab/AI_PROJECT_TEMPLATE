# User Prompt

Improve the cluster MCP tools' cross-platform path handling so they work reliably regardless of how or where users access the cluster filesystem (SMB mounts, Windows, WSL, etc.), and ensure the model is aware of the configuration so it can guide users.

Approach: TDD — write failing tests first that define expected behavior for path mapping, remote_cwd, Windows paths, etc., then implement until they pass.

Reference: GitHub Issue #14 — Add path_map and remote_cwd to cluster tools for remote filesystem mapping.
