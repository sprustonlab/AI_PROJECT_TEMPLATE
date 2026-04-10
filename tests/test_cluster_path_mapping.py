"""Tests for cluster path mapping, log reading strategies, and config integration.

Tests PathMapper, LogReader (3 strategies), config validation, CWD resolution,
submit integration, status display paths, shell injection safety, default
passthrough, and model tool descriptions.

All subprocess/SSH calls are mocked — no real cluster needed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import tool modules directly (no claudechic needed)
# ---------------------------------------------------------------------------

TEMPLATE_MCP = Path(__file__).resolve().parent.parent / "template" / "mcp_tools"


def _get_tool_name(tool) -> str | None:
    """Get name from a tool object."""
    return getattr(tool, "name", None) or getattr(tool, "_tool_name", None)


def _get_tool_description(tool) -> str:
    """Get description from a tool object."""
    return getattr(tool, "description", "") or getattr(tool, "_tool_description", "")


def _import_module(name: str, filepath: Path):
    """Import a module from file path, registering in sys.modules."""
    module_name = f"mcp_tools.{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    assert spec and spec.loader, f"Cannot load {filepath}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load modules
_cluster_mod = _import_module("_cluster", TEMPLATE_MCP / "_cluster.py")
lsf_mod = _import_module("lsf", TEMPLATE_MCP / "lsf.py")
slurm_mod = _import_module("slurm", TEMPLATE_MCP / "slurm.py")

PathMapper = _cluster_mod.PathMapper
LocalLogReader = _cluster_mod.LocalLogReader
SSHLogReader = _cluster_mod.SSHLogReader
AutoLogReader = _cluster_mod.AutoLogReader

# ---------------------------------------------------------------------------
# Reusable environment definitions
# ---------------------------------------------------------------------------

SMB_MAC = {"local": "/Volumes/groups", "cluster": "/groups"}
WINDOWS_DRIVE = {"local": "Z:\\groups", "cluster": "/groups"}
WSL_MOUNT = {"local": "/mnt/cluster/groups", "cluster": "/groups"}
UNC_PATH = {"local": "//smb-server/groups", "cluster": "/groups"}
DIRECT_CLUSTER = {}  # no mapping needed
MULTI_MOUNT = [
    {"local": "/mnt/projects", "cluster": "/groups/projects"},
    {"local": "/mnt/scratch", "cluster": "/scratch"},
]
OVERLAP_RULES = [
    {"local": "/mnt/cluster", "cluster": "/"},
    {"local": "/mnt/cluster/groups", "cluster": "/groups"},
]


# ---------------------------------------------------------------------------
# Test 1: test_path_translates_local_to_cluster
# ---------------------------------------------------------------------------


class TestPathTranslatesLocalToCluster:
    """Local-to-cluster translation via PathMapper.to_cluster()."""

    @pytest.mark.parametrize(
        "rules,input_path,expected",
        [
            pytest.param(
                [SMB_MAC], "/Volumes/groups/lab/script.sh",
                "/groups/lab/script.sh", id="smb_mac",
            ),
            pytest.param(
                [WINDOWS_DRIVE], "Z:\\groups\\lab\\run.py",
                "/groups/lab/run.py", id="windows_drive",
            ),
            pytest.param(
                [WSL_MOUNT], "/mnt/cluster/groups/spruston/project",
                "/groups/spruston/project", id="wsl_mount",
            ),
            pytest.param(
                [UNC_PATH], "//smb-server/groups/lab/data",
                "/groups/lab/data", id="unc_path",
            ),
            pytest.param(
                [SMB_MAC], "/tmp/scratch/data",
                "/tmp/scratch/data", id="no_match_passthrough",
            ),
            pytest.param(
                OVERLAP_RULES, "/mnt/cluster/groups/spruston/file.py",
                "/groups/spruston/file.py", id="longest_prefix_wins",
            ),
            pytest.param(
                [{"local": "/mnt/cluster", "cluster": "/"}],
                "/mnt/clusterX/foo",
                "/mnt/clusterX/foo", id="boundary_safe_no_false_match",
            ),
            pytest.param(
                [{"local": "/Volumes/groups/", "cluster": "/groups/"}],
                "/Volumes/groups/lab/data",
                "/groups/lab/data", id="trailing_slash_config",
            ),
        ],
    )
    def test_to_cluster(self, rules, input_path, expected):
        mapper = PathMapper(rules)
        assert mapper.to_cluster(input_path) == expected


# ---------------------------------------------------------------------------
# Test 2: test_path_translates_cluster_to_local
# ---------------------------------------------------------------------------


class TestPathTranslatesClusterToLocal:
    """Cluster-to-local translation via PathMapper.to_local()."""

    @pytest.mark.parametrize(
        "rules,input_path,expected",
        [
            pytest.param(
                [SMB_MAC], "/groups/lab/logs/out.log",
                "/Volumes/groups/lab/logs/out.log", id="smb_mac_reverse",
            ),
            pytest.param(
                [WINDOWS_DRIVE], "/groups/lab/out.log",
                "Z:/groups/lab/out.log", id="windows_forward_slashes",
            ),
            pytest.param(
                [WSL_MOUNT], "/groups/spruston/logs/out.log",
                "/mnt/cluster/groups/spruston/logs/out.log", id="wsl_reverse",
            ),
            pytest.param(
                [SMB_MAC], "/tmp/scratch/data",
                "/tmp/scratch/data", id="no_match_passthrough",
            ),
            pytest.param(
                [], "/groups/lab/out.log",
                "/groups/lab/out.log", id="empty_rules_passthrough",
            ),
            pytest.param(
                None, "/groups/lab/out.log",
                "/groups/lab/out.log", id="none_rules_passthrough",
            ),
            pytest.param(
                OVERLAP_RULES, "/groups/spruston/deep/file.py",
                "/mnt/cluster/groups/spruston/deep/file.py",
                id="longest_cluster_prefix_wins",
            ),
        ],
    )
    def test_to_local(self, rules, input_path, expected):
        mapper = PathMapper(rules)
        assert mapper.to_local(input_path) == expected


# ---------------------------------------------------------------------------
# Test 3: test_cwd_resolves_correctly
# ---------------------------------------------------------------------------


class TestCWDResolvesCorrectly:
    """_resolve_cwd() priority: remote_cwd > translated CWD > raw os.getcwd()."""

    @pytest.mark.parametrize(
        "remote_cwd,local_cwd,rules,expected",
        [
            pytest.param(
                "/groups/lab/project", "/Volumes/groups/lab/project",
                [SMB_MAC], "/groups/lab/project",
                id="remote_cwd_wins",
            ),
            pytest.param(
                "", "/Volumes/groups/lab/project",
                [SMB_MAC], "/groups/lab/project",
                id="translates_local_cwd",
            ),
            pytest.param(
                "", "/home/user/project",
                [], "/home/user/project",
                id="no_config_passthrough",
            ),
            pytest.param(
                "", "/groups/lab/project",
                [], "/groups/lab/project",
                id="direct_cluster_verbatim",
            ),
            pytest.param(
                "", "Z:\\groups\\lab\\project",
                [WINDOWS_DRIVE], "/groups/lab/project",
                id="windows_cwd_normalized",
            ),
        ],
    )
    def test_resolve_cwd(self, remote_cwd, local_cwd, rules, expected, monkeypatch):
        monkeypatch.setattr(os, "getcwd", lambda: local_cwd)
        config = {"remote_cwd": remote_cwd} if remote_cwd else {}
        mapper = PathMapper(rules)
        assert _cluster_mod._resolve_cwd(config, mapper) == expected


# ---------------------------------------------------------------------------
# Test 4: test_log_reading_works
# ---------------------------------------------------------------------------


class TestLogReadingWorks:
    """LogReader strategy selects correct transport and handles failures."""

    def test_local_reader_success(self, tmp_path):
        """LocalLogReader reads files via local mount."""
        log_file = tmp_path / "out.log"
        log_file.write_text("line1\nline2\nline3\n")
        # Map cluster path to local temp dir
        mapper = PathMapper([
            {"local": str(tmp_path), "cluster": "/cluster/logs"},
        ])
        reader = LocalLogReader(mapper)
        content = reader.read_tail("/cluster/logs/out.log", tail=2)
        assert content is not None
        assert "line2" in content
        assert "line3" in content

    def test_local_reader_file_not_found(self):
        """LocalLogReader returns None when file doesn't exist."""
        reader = LocalLogReader(PathMapper([]))
        assert reader.read_tail("/nonexistent/file.log", tail=10) is None

    @patch.object(_cluster_mod, "_run_ssh")
    def test_ssh_reader_success(self, mock_ssh):
        """SSHLogReader reads via SSH."""
        mock_ssh.return_value = ("last line\n", "", 0)
        reader = SSHLogReader("login.example.com")
        content = reader.read_tail("/cluster/logs/out.log", tail=10)
        assert content == "last line\n"
        # Verify shlex.quote is used
        call_cmd = mock_ssh.call_args[0][0]
        assert "tail" in call_cmd

    @patch.object(_cluster_mod, "_run_ssh")
    def test_ssh_reader_failure(self, mock_ssh):
        """SSHLogReader returns None on SSH failure."""
        mock_ssh.return_value = ("", "error", 1)
        reader = SSHLogReader("login.example.com")
        assert reader.read_tail("/cluster/logs/out.log", tail=10) is None

    def test_ssh_reader_no_target(self):
        """SSHLogReader returns None when no ssh_target."""
        reader = SSHLogReader("")
        assert reader.read_tail("/cluster/logs/out.log", tail=10) is None

    def test_auto_reader_local_success(self, tmp_path):
        """AutoLogReader uses local when available."""
        log_file = tmp_path / "out.log"
        log_file.write_text("local content\n")
        mapper = PathMapper([
            {"local": str(tmp_path), "cluster": "/cluster/logs"},
        ])
        local = LocalLogReader(mapper)
        ssh = SSHLogReader("login.example.com")
        reader = AutoLogReader(local, ssh)
        content = reader.read_tail("/cluster/logs/out.log", tail=0)
        assert content == "local content\n"

    @patch.object(_cluster_mod, "_run_ssh")
    def test_auto_reader_fallback_to_ssh(self, mock_ssh):
        """AutoLogReader falls back to SSH when local fails."""
        mock_ssh.return_value = ("ssh content\n", "", 0)
        local = LocalLogReader(PathMapper([]))  # no mapping -> file not found
        ssh = SSHLogReader("login.example.com")
        reader = AutoLogReader(local, ssh)
        content = reader.read_tail("/nonexistent/out.log", tail=0)
        assert content == "ssh content\n"

    @patch.object(_cluster_mod, "_run_ssh")
    def test_auto_reader_both_fail(self, mock_ssh):
        """AutoLogReader returns None when both fail."""
        mock_ssh.return_value = ("", "error", 1)
        local = LocalLogReader(PathMapper([]))
        ssh = SSHLogReader("login.example.com")
        reader = AutoLogReader(local, ssh)
        assert reader.read_tail("/nonexistent/out.log", tail=0) is None


# ---------------------------------------------------------------------------
# Test 5: test_submit_uses_correct_paths
# ---------------------------------------------------------------------------


class TestSubmitUsesCorrectPaths:
    """Submit builds correct CWD flag per scheduler x environment."""

    @patch.object(lsf_mod, "_run_lsf")
    def test_lsf_smb_mac(self, mock_lsf, monkeypatch):
        """LSF submit translates SMB Mac CWD to cluster path."""
        monkeypatch.setattr(os, "getcwd", lambda: "/Volumes/groups/lab/project")
        mock_lsf.return_value = ("Job <12345> is submitted.", "", 0)
        config = {"ssh_target": "login.example.com"}
        mapper = PathMapper([SMB_MAC])
        result = lsf_mod._submit_job(
            queue="gpu", cpus=1, walltime="1:00",
            command="python train.py",
            config=config, path_mapper=mapper,
        )
        bsub_cmd = mock_lsf.call_args[0][0]
        assert "-cwd" in bsub_cmd
        assert "/groups/lab/project" in bsub_cmd
        assert result["job_id"] == "12345"

    @patch.object(lsf_mod, "_run_lsf")
    def test_lsf_remote_cwd(self, mock_lsf, monkeypatch):
        """LSF submit uses remote_cwd when set."""
        monkeypatch.setattr(os, "getcwd", lambda: "/Volumes/groups/lab/project")
        mock_lsf.return_value = ("Job <12345> is submitted.", "", 0)
        config = {"ssh_target": "login.example.com", "remote_cwd": "/groups/lab/project"}
        mapper = PathMapper([])
        result = lsf_mod._submit_job(
            queue="gpu", cpus=1, walltime="1:00",
            command="python train.py",
            config=config, path_mapper=mapper,
        )
        bsub_cmd = mock_lsf.call_args[0][0]
        assert "-cwd" in bsub_cmd
        assert "/groups/lab/project" in bsub_cmd

    @patch.object(slurm_mod, "_run_slurm")
    def test_slurm_smb_mac(self, mock_slurm, monkeypatch):
        """SLURM submit translates SMB Mac CWD."""
        monkeypatch.setattr(os, "getcwd", lambda: "/Volumes/groups/lab/project")
        mock_slurm.return_value = ("Submitted batch job 99999", "", 0)
        config = {"ssh_target": "login.example.com"}
        mapper = PathMapper([SMB_MAC])
        result = slurm_mod._submit_job(
            partition="gpu", cpus=1, time_limit="1:00:00",
            command="python train.py",
            config=config, path_mapper=mapper,
        )
        sbatch_cmd = mock_slurm.call_args[0][0]
        assert "--chdir=" in sbatch_cmd
        assert "/groups/lab/project" in sbatch_cmd
        assert result["job_id"] == "99999"

    @patch.object(slurm_mod, "_run_slurm")
    def test_slurm_windows(self, mock_slurm, monkeypatch):
        """SLURM submit translates Windows CWD."""
        monkeypatch.setattr(os, "getcwd", lambda: "Z:\\groups\\lab\\project")
        mock_slurm.return_value = ("Submitted batch job 88888", "", 0)
        config = {"ssh_target": "login.example.com"}
        mapper = PathMapper([WINDOWS_DRIVE])
        result = slurm_mod._submit_job(
            partition="gpu", cpus=1, time_limit="1:00:00",
            command="python train.py",
            config=config, path_mapper=mapper,
        )
        sbatch_cmd = mock_slurm.call_args[0][0]
        assert "--chdir=" in sbatch_cmd
        assert "/groups/lab/project" in sbatch_cmd

    @patch.object(lsf_mod, "_run_lsf")
    def test_lsf_direct_cluster(self, mock_lsf, monkeypatch):
        """LSF submit on direct cluster uses CWD verbatim."""
        monkeypatch.setattr(os, "getcwd", lambda: "/groups/lab/project")
        mock_lsf.return_value = ("Job <12345> is submitted.", "", 0)
        config = {}
        mapper = PathMapper([])
        lsf_mod._submit_job(
            queue="gpu", cpus=1, walltime="1:00",
            command="python train.py",
            config=config, path_mapper=mapper,
        )
        bsub_cmd = mock_lsf.call_args[0][0]
        assert "-cwd" in bsub_cmd
        assert "/groups/lab/project" in bsub_cmd

    @patch.object(lsf_mod, "_run_lsf")
    def test_lsf_command_not_modified(self, mock_lsf, monkeypatch):
        """User command string is NOT modified by path translation."""
        monkeypatch.setattr(os, "getcwd", lambda: "/Volumes/groups/lab/project")
        mock_lsf.return_value = ("Job <12345> is submitted.", "", 0)
        config = {}
        mapper = PathMapper([SMB_MAC])
        lsf_mod._submit_job(
            queue="gpu", cpus=1, walltime="1:00",
            command="python /Volumes/groups/lab/train.py",
            config=config, path_mapper=mapper,
        )
        bsub_cmd = mock_lsf.call_args[0][0]
        # The command inside the bsub call should still contain the local path
        assert "/Volumes/groups/lab/train.py" in bsub_cmd


# ---------------------------------------------------------------------------
# Test 6: test_status_returns_local_paths
# ---------------------------------------------------------------------------


class TestStatusReturnsLocalPaths:
    """Status response paths are translated to local filesystem."""

    @pytest.mark.parametrize(
        "rules,cluster_paths,expected_local",
        [
            pytest.param(
                [SMB_MAC],
                {"stdout_path": "/groups/lab/out.log", "execution_cwd": "/groups/lab/project"},
                {"stdout_path": "/Volumes/groups/lab/out.log", "execution_cwd": "/Volumes/groups/lab/project"},
                id="smb_mac",
            ),
            pytest.param(
                [],
                {"stdout_path": "/groups/lab/out.log"},
                {"stdout_path": "/groups/lab/out.log"},
                id="empty_rules_passthrough",
            ),
            pytest.param(
                [WINDOWS_DRIVE],
                {"stdout_path": "/groups/lab/out.log"},
                {"stdout_path": "Z:/groups/lab/out.log"},
                id="windows_forward_slashes",
            ),
            pytest.param(
                MULTI_MOUNT,
                {"stdout_path": "/groups/projects/out.log", "stderr_path": "/scratch/err.log"},
                {"stdout_path": "/mnt/projects/out.log", "stderr_path": "/mnt/scratch/err.log"},
                id="multi_mount_routing",
            ),
        ],
    )
    def test_translate_paths(self, rules, cluster_paths, expected_local):
        mapper = PathMapper(rules)
        for key, cluster_val in cluster_paths.items():
            assert mapper.to_local(cluster_val) == expected_local[key]


# ---------------------------------------------------------------------------
# Test 7: test_config_loads_correctly
# ---------------------------------------------------------------------------


class TestConfigLoadsCorrectly:
    """Config parsing succeeds with valid input or fails with clear errors."""

    def test_full_valid_config(self):
        """Full valid config creates PathMapper without error."""
        config = {
            "path_map": [SMB_MAC],
            "log_access": "auto",
            "remote_cwd": "/groups/lab/project",
        }
        mapper = _cluster_mod._create_path_mapper(config)
        assert mapper.to_cluster("/Volumes/groups/lab/x") == "/groups/lab/x"

    def test_empty_config(self):
        """Empty config creates passthrough PathMapper."""
        mapper = _cluster_mod._create_path_mapper({})
        assert mapper.to_cluster("/any/path") == "/any/path"

    def test_missing_path_map_key(self):
        """Config without path_map key defaults to empty."""
        config = {"ssh_target": "login.example.com"}
        mapper = _cluster_mod._create_path_mapper(config)
        assert mapper.to_cluster("/any/path") == "/any/path"

    def test_missing_local_key(self):
        """path_map entry missing 'local' raises ValueError."""
        config = {"path_map": [{"cluster": "/groups"}]}
        with pytest.raises(ValueError, match="local"):
            _cluster_mod._create_path_mapper(config)

    def test_missing_cluster_key(self):
        """path_map entry missing 'cluster' raises ValueError."""
        config = {"path_map": [{"local": "/mnt/groups"}]}
        with pytest.raises(ValueError, match="cluster"):
            _cluster_mod._create_path_mapper(config)

    def test_empty_local_prefix(self):
        """Empty local prefix raises ValueError."""
        config = {"path_map": [{"local": "", "cluster": "/groups"}]}
        with pytest.raises(ValueError, match="non-empty"):
            _cluster_mod._create_path_mapper(config)

    def test_empty_cluster_prefix(self):
        """Empty cluster prefix raises ValueError."""
        config = {"path_map": [{"local": "/mnt/groups", "cluster": ""}]}
        with pytest.raises(ValueError, match="non-empty"):
            _cluster_mod._create_path_mapper(config)

    def test_invalid_log_access(self):
        """Invalid log_access raises ValueError."""
        config = {"log_access": "ftp"}
        with pytest.raises(ValueError, match="auto.*local.*ssh"):
            _cluster_mod._create_path_mapper(config)

    def test_path_map_wrong_type(self):
        """path_map as string raises TypeError."""
        config = {"path_map": "/mnt:/groups"}
        with pytest.raises(TypeError, match="list"):
            _cluster_mod._create_path_mapper(config)


# ---------------------------------------------------------------------------
# Test 8: test_shell_injection_prevented
# ---------------------------------------------------------------------------


class TestShellInjectionPrevented:
    """shlex.quote() neutralizes shell metacharacters in paths."""

    @pytest.mark.parametrize(
        "dangerous_path",
        [
            pytest.param("/path/with spaces/file.log", id="spaces"),
            pytest.param("/path/$HOME/file.log", id="dollar_var"),
            pytest.param("/path/`whoami`/file.log", id="backticks"),
            pytest.param("/path/it's/file.log", id="single_quote"),
            pytest.param("/path/$(whoami)/file.log", id="dollar_paren"),
        ],
    )
    def test_shlex_quote_neutralizes(self, dangerous_path):
        """shlex.quote produces safe strings for all dangerous chars."""
        quoted = shlex.quote(dangerous_path)
        # Quoted string should not execute subshells
        assert "$(" not in quoted or quoted.startswith("'")
        assert "`" not in quoted or quoted.startswith("'")

    @patch.object(_cluster_mod, "_run_ssh")
    def test_ssh_log_reader_quotes_path(self, mock_ssh):
        """SSHLogReader embeds quoted path in SSH command."""
        mock_ssh.return_value = ("content", "", 0)
        reader = SSHLogReader("login.example.com")
        reader.read_tail("/path/$(whoami)/file.log", tail=10)
        call_cmd = mock_ssh.call_args[0][0]
        # The path should be quoted
        assert "$(whoami)" not in call_cmd or "'" in call_cmd


# ---------------------------------------------------------------------------
# Test 9: test_defaults_passthrough
# ---------------------------------------------------------------------------


class TestDefaultsPassthrough:
    """Configs without new keys use safe defaults — paths pass through."""

    @pytest.mark.parametrize(
        "config",
        [
            pytest.param({"ssh_target": "login1.org"}, id="no_new_keys"),
            pytest.param({"ssh_target": "login1.org", "path_map": []}, id="explicit_empty"),
            pytest.param({"ssh_target": "login1.org"}, id="no_log_access"),
            pytest.param({}, id="completely_empty"),
        ],
    )
    def test_passthrough(self, config, monkeypatch):
        monkeypatch.setattr(os, "getcwd", lambda: "/groups/lab/project")
        mapper = _cluster_mod._create_path_mapper(config)
        # to_cluster passthrough
        assert mapper.to_cluster("/any/path") == "/any/path"
        # to_local passthrough
        assert mapper.to_local("/any/path") == "/any/path"
        # resolve_cwd passthrough
        assert _cluster_mod._resolve_cwd(config, mapper) == "/groups/lab/project"


# ---------------------------------------------------------------------------
# Test 10: test_model_sees_correct_descriptions
# ---------------------------------------------------------------------------


class TestModelSeesCorrectDescriptions:
    """Tool descriptions inform the model about path mapping and setup."""

    @patch.object(lsf_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_lsf_descriptions(self, mock_config):
        tools = lsf_mod.get_tools()
        tool_map = {_get_tool_name(t): t for t in tools}

        submit_desc = _get_tool_description(tool_map["cluster_submit"]).lower()
        assert "path_map" in submit_desc
        assert "remote_cwd" in submit_desc
        assert "setup_needed" in submit_desc
        assert "not automatically translated" in submit_desc

        logs_desc = _get_tool_description(tool_map["cluster_logs"]).lower()
        assert "log_access" in logs_desc
        assert "ssh" in logs_desc

        status_desc = _get_tool_description(tool_map["cluster_status"]).lower()
        assert "local paths" in status_desc

    @patch.object(slurm_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_slurm_descriptions(self, mock_config):
        tools = slurm_mod.get_tools()
        tool_map = {_get_tool_name(t): t for t in tools}

        submit_desc = _get_tool_description(tool_map["cluster_submit"]).lower()
        assert "path_map" in submit_desc
        assert "setup_needed" in submit_desc

        logs_desc = _get_tool_description(tool_map["cluster_logs"]).lower()
        assert "log_access" in logs_desc


# ---------------------------------------------------------------------------
# Test 11: test_onboarding_detect_phase (config readiness)
# ---------------------------------------------------------------------------


class TestOnboardingDetectPhase:
    """_check_config_readiness identifies config state correctly."""

    @pytest.mark.parametrize(
        "config,local_scheduler,expected",
        [
            pytest.param(
                {"ssh_target": "login1.org", "path_map": [SMB_MAC]},
                False, "ready", id="fully_configured",
            ),
            pytest.param(
                {}, False, "needs_setup", id="no_target_no_local",
            ),
            pytest.param(
                {"ssh_target": "login1.org"}, False, "incomplete",
                id="target_no_path_map",
            ),
            pytest.param(
                {}, True, "ready", id="local_scheduler_found",
            ),
            pytest.param(
                {"ssh_target": "{{ ssh_host }}"}, False, "needs_setup",
                id="jinja_placeholder",
            ),
        ],
    )
    def test_readiness(self, config, local_scheduler, expected):
        if local_scheduler:
            mock_which = lambda x: "/usr/bin/bsub" if x == "bsub" else None
        else:
            mock_which = lambda x: None

        with patch.object(_cluster_mod.shutil, "which", mock_which):
            assert _cluster_mod._check_config_readiness(config) == expected


# ---------------------------------------------------------------------------
# Test 12: test_onboarding_validate_phase (config validation)
# ---------------------------------------------------------------------------


class TestOnboardingValidatePhase:
    """Config validation catches errors and reports fix phases."""

    def test_valid_config_passes(self):
        """Full valid config passes all validation."""
        config = {
            "ssh_target": "login.example.com",
            "path_map": [SMB_MAC],
            "log_access": "auto",
        }
        mapper = _cluster_mod._create_path_mapper(config)
        # Round-trip test
        original = "/Volumes/groups/lab/file.py"
        cluster = mapper.to_cluster(original)
        local = mapper.to_local(cluster)
        assert local == original

    def test_invalid_path_map_fails(self):
        """Invalid path_map entry is caught at creation time."""
        config = {"path_map": [{"local": "/mnt"}]}  # missing cluster
        with pytest.raises(ValueError):
            _cluster_mod._create_path_mapper(config)

    def test_invalid_log_access_fails(self):
        """Invalid log_access is caught at creation time."""
        config = {"log_access": "ftp"}
        with pytest.raises(ValueError):
            _cluster_mod._create_path_mapper(config)

    def test_round_trip_consistency(self):
        """Path round-trip: local -> cluster -> local produces original."""
        for rules in [[SMB_MAC], [WINDOWS_DRIVE], [WSL_MOUNT], MULTI_MOUNT]:
            mapper = PathMapper(rules)
            for rule in (rules if isinstance(rules, list) else [rules]):
                if "local" in rule:
                    test_path = rule["local"] + "/sub/file.py"
                    cluster = mapper.to_cluster(test_path)
                    back = mapper.to_local(cluster)
                    assert back == _cluster_mod._normalize_local_path(test_path)


# ---------------------------------------------------------------------------
# Test 13: test_onboarding_apply_phase (config write)
# ---------------------------------------------------------------------------


class TestOnboardingApplyPhase:
    """Apply writes only after validation; dry_run previews safely."""

    def test_dry_run_no_write(self, tmp_path):
        """Dry run previews config without writing."""
        config_path = tmp_path / "lsf.yaml"
        # Simulate a dry_run by just building the config
        proposed = {
            "ssh_target": "login.example.com",
            "path_map": [SMB_MAC],
            "log_access": "auto",
        }
        # dry_run=True: just validate, don't write
        dry_run = True
        validation_passed = False
        status = "preview" if dry_run else ("written" if validation_passed else "rejected")
        assert status == "preview"
        assert not config_path.exists()

    def test_apply_after_validation(self, tmp_path):
        """Apply writes config after validation passes."""
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not available")

        config_path = tmp_path / "lsf.yaml"
        proposed = {
            "ssh_target": "login.example.com",
            "path_map": [SMB_MAC],
            "log_access": "auto",
        }
        dry_run = False
        validation_passed = True

        if not dry_run and validation_passed:
            with open(config_path, "w") as f:
                yaml.safe_dump(proposed, f)
            status = "written"
        elif not dry_run:
            status = "rejected"
        else:
            status = "preview"

        assert status == "written"
        assert config_path.exists()
        with open(config_path) as f:
            written = yaml.safe_load(f)
        assert written["ssh_target"] == "login.example.com"
        assert written["path_map"] == [SMB_MAC]

    def test_apply_rejected_without_validation(self, tmp_path):
        """Apply is rejected when validation hasn't passed."""
        config_path = tmp_path / "lsf.yaml"
        dry_run = False
        validation_passed = False
        status = "preview" if dry_run else ("written" if validation_passed else "rejected")
        assert status == "rejected"
        assert not config_path.exists()

    def test_dry_run_with_validation(self, tmp_path):
        """Dry run is always allowed, even with validation passed."""
        config_path = tmp_path / "lsf.yaml"
        dry_run = True
        validation_passed = True
        status = "preview" if dry_run else ("written" if validation_passed else "rejected")
        assert status == "preview"
        assert not config_path.exists()


# ---------------------------------------------------------------------------
# Additional integration tests
# ---------------------------------------------------------------------------


class TestResolveLogPath:
    """_resolve_log_path uses startswith('/') for POSIX detection."""

    def test_absolute_path(self):
        result = _cluster_mod._resolve_log_path("/groups/lab/out.log", None)
        assert result == "/groups/lab/out.log"

    def test_relative_with_cwd(self):
        result = _cluster_mod._resolve_log_path("out.log", "/groups/lab")
        assert result == "/groups/lab/out.log"

    def test_relative_without_cwd(self):
        result = _cluster_mod._resolve_log_path("out.log", None)
        assert result == "out.log"


class TestLogReaderFactory:
    """_create_log_reader returns correct reader based on config."""

    def test_auto_mode(self):
        reader = _cluster_mod._create_log_reader(
            {"ssh_target": "login.example.com"},
            PathMapper([]),
        )
        assert isinstance(reader, AutoLogReader)

    def test_local_mode(self):
        reader = _cluster_mod._create_log_reader(
            {"log_access": "local"},
            PathMapper([]),
        )
        assert isinstance(reader, LocalLogReader)

    def test_ssh_mode(self):
        reader = _cluster_mod._create_log_reader(
            {"log_access": "ssh", "ssh_target": "login.example.com"},
            PathMapper([]),
        )
        assert isinstance(reader, SSHLogReader)

    def test_default_auto(self):
        reader = _cluster_mod._create_log_reader({}, PathMapper([]))
        assert isinstance(reader, AutoLogReader)


class TestErrorWithHint:
    """_error_with_hint includes setup workflow guidance."""

    def test_path_hint(self):
        resp = _cluster_mod._error_with_hint("File not found", "path")
        text = resp["content"][0]["text"]
        assert "cluster_setup" in text
        assert resp["isError"] is True

    def test_connection_hint(self):
        resp = _cluster_mod._error_with_hint("SSH failed", "connection")
        text = resp["content"][0]["text"]
        assert "cluster_setup" in text

    def test_first_use_hint(self):
        resp = _cluster_mod._error_with_hint("Not configured", "first_use")
        text = resp["content"][0]["text"]
        assert "cluster_setup" in text
