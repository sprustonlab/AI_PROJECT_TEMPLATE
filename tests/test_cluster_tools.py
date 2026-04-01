"""Tests for LSF and SLURM cluster MCP tools.

Tests parsers, get_tools() contract, config loading, and graceful degradation.
All subprocess/SSH calls are mocked — no real cluster needed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
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
    """Get name from a tool object (works with real SdkMcpTool or mock)."""
    return getattr(tool, "name", None) or getattr(tool, "_tool_name", None)


async def _call_tool(tool, args: dict):
    """Call a tool handler (works with real SdkMcpTool or mock decorated function)."""
    handler = getattr(tool, "handler", None)
    if handler is not None:
        return await handler(args)
    # Mock: tool is the async function itself
    return await tool(args)


def _import_module(name: str, filepath: Path):
    """Import a module from file path, registering in sys.modules."""
    module_name = f"mcp_tools.{name}"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    assert spec and spec.loader, f"Cannot load {filepath}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load _cluster first (shared helper), then backends

_cluster_mod = _import_module("_cluster", TEMPLATE_MCP / "_cluster.py")
lsf_mod = _import_module("lsf", TEMPLATE_MCP / "lsf.py")
slurm_mod = _import_module("slurm", TEMPLATE_MCP / "slurm.py")


# ---------------------------------------------------------------------------
# Captured real-ish output samples
# ---------------------------------------------------------------------------

BJOBS_WIDE_OUTPUT = """\
JOBID   USER    STAT  QUEUE      FROM_HOST   EXEC_HOST   JOB_NAME   SUBMIT_TIME
123456  moharb  RUN   gpu        login01     gpu-0042    train_v3   Mar 28 14:30
123457  moharb  PEND  normal     login01     -           preprocess Mar 28 14:35
123458  moharb  DONE  short      login01     cpu-0001    cleanup    Mar 28 13:00
"""

BJOBS_WIDE_NO_JOBS = """\
No unfinished job found
"""

BJOBS_LONG_OUTPUT = """\
Job <123456>, Job Name <train_v3>, User <moharb>, Project <default>,
                     Status <RUN>, Queue <gpu>, Command <python train.py
                     --epochs 100 --lr 0.001>
Thu Mar 28 14:30:22 2026: Submitted from host <login01>, CWD </home/moharb/project>;
Thu Mar 28 14:30:25 2026: Started 1 Task(s) on Host(s) <gpu-0042>, Allocated 1
                     Slot(s) on Host(s) <gpu-0042>;
                     Execution CWD </home/moharb/project>;
                     Output File </home/moharb/project/logs/train.out>;
                     Error File </home/moharb/project/logs/train.err>;

 RUNLIMIT
 1440.0 min of gpu-0042

 SCHEDULING PARAMETERS:
 CPU time used is 3600.5 seconds.
 MEM: 4.2 Gbytes;  SWAP: 0 Mbytes;
 MAX MEM: 8.1 Gbytes;  MAX SWAP: 0 Mbytes;
"""

SQUEUE_OUTPUT = """\
JOBID|NAME|STATE|TIME|TIME_LIMIT|NODES|NODELIST(REASON)
100001|train_model|RUNNING|2:30:15|8:00:00|1|gpu-node-01
100002|preprocess|PENDING|0:00|4:00:00|1|(Priority)
100003|eval_metrics|COMPLETED|0:45:20|2:00:00|1|cpu-node-03
"""

SCONTROL_JOB_OUTPUT = """\
JobId=100001 JobName=train_model UserId=moharb(1000) GroupId=research(2000) MCS_label=N/A
   Priority=1000 Nice=0 Account=default QOS=normal
   JobState=RUNNING Reason=None Dependency=(null)
   Requeue=0 Restarts=0 BatchFlag=1 Reboot=0 ExitCode=0:0
   RunTime=02:30:15 TimeLimit=08:00:00 TimeMin=N/A
   SubmitTime=2026-03-28T12:00:00 EligibleTime=2026-03-28T12:00:00
   AcctSuspTime=0 StartTime=2026-03-28T12:00:05 EndTime=2026-03-28T20:00:05
   Deadline=N/A SuspendTime=None SecsPreSuspend=0
   LastSchedEval=2026-03-28T12:00:05
   Partition=gpu AllocNode:Sid=login01:12345
   ReqNodeList=(null) ExcNodeList=(null)
   NodeList=gpu-node-01 BatchHost=gpu-node-01
   NumNodes=1 NumCPUs=8 NumTasks=8 CPUs/Task=1 ReqB:S:C:T=0:0:*:*
   Command=/home/moharb/project/run_train.sh
   WorkDir=/home/moharb/project
   StdErr=/home/moharb/project/logs/train.err
   StdOut=/home/moharb/project/logs/train.out
   CPUTimeRAW=72060
   MaxRSS=4096M
"""


# ---------------------------------------------------------------------------
# LSF Parser Tests
# ---------------------------------------------------------------------------


class TestLSFParseBjobsWide:
    """Tests for _parse_bjobs_wide."""

    def test_parse_multiple_jobs(self):
        jobs = lsf_mod._parse_bjobs_wide(BJOBS_WIDE_OUTPUT)
        assert len(jobs) == 3
        assert jobs[0]["job_id"] == "123456"
        assert jobs[0]["user"] == "moharb"
        assert jobs[0]["status"] == "RUN"
        assert jobs[0]["queue"] == "gpu"
        assert jobs[0]["job_name"] == "train_v3"

    def test_parse_pending_job(self):
        jobs = lsf_mod._parse_bjobs_wide(BJOBS_WIDE_OUTPUT)
        pending = [j for j in jobs if j["status"] == "PEND"]
        assert len(pending) == 1
        assert pending[0]["job_name"] == "preprocess"

    def test_parse_no_jobs(self):
        jobs = lsf_mod._parse_bjobs_wide(BJOBS_WIDE_NO_JOBS)
        assert jobs == []

    def test_parse_empty_string(self):
        jobs = lsf_mod._parse_bjobs_wide("")
        assert jobs == []

    def test_header_only(self):
        jobs = lsf_mod._parse_bjobs_wide(
            "JOBID   USER    STAT  QUEUE      FROM_HOST   EXEC_HOST   JOB_NAME   SUBMIT_TIME\n"
        )
        assert jobs == []

    def test_short_lines_skipped(self):
        """Lines with fewer than 7 fields are skipped."""
        jobs = lsf_mod._parse_bjobs_wide("123 user RUN\n")
        assert jobs == []


class TestLSFParseBjobsDetail:
    """Tests for _parse_bjobs_detail / _collapse_lsf_lines."""

    def test_parse_detail(self):
        detail = lsf_mod._parse_bjobs_detail(BJOBS_LONG_OUTPUT, "123456")
        assert detail["job_id"] == "123456"
        assert detail["job_name"] == "train_v3"
        assert detail["status"] == "RUN"
        assert detail["queue"] == "gpu"
        assert detail["exec_host"] == "gpu-0042"
        assert detail["execution_cwd"] == "/home/moharb/project"
        assert detail["stdout_path"] == "/home/moharb/project/logs/train.out"
        assert detail["stderr_path"] == "/home/moharb/project/logs/train.err"

    def test_cpu_time_parsed(self):
        detail = lsf_mod._parse_bjobs_detail(BJOBS_LONG_OUTPUT, "123456")
        assert detail["cpu_time_seconds"] == 3600

    def test_memory_parsed(self):
        detail = lsf_mod._parse_bjobs_detail(BJOBS_LONG_OUTPUT, "123456")
        assert detail["mem_gb"] == 4.2
        assert detail["max_mem_gb"] == 8.1

    def test_run_limit_parsed(self):
        detail = lsf_mod._parse_bjobs_detail(BJOBS_LONG_OUTPUT, "123456")
        assert detail["run_limit_min"] == 1440.0

    def test_collapse_continuation_lines(self):
        """Continuation lines (10+ leading spaces) are collapsed."""
        text = "Line one\n          continuation\nLine two\n"
        collapsed = lsf_mod._collapse_lsf_lines(text)
        assert "Line onecontinuation" in collapsed
        assert "Line two" in collapsed

    def test_command_with_continuation(self):
        """Command spanning multiple continuation lines is parsed correctly."""
        detail = lsf_mod._parse_bjobs_detail(BJOBS_LONG_OUTPUT, "123456")
        # Command should include the continuation
        assert detail["command"] is not None
        assert "python" in detail["command"]


# ---------------------------------------------------------------------------
# SLURM Parser Tests
# ---------------------------------------------------------------------------


class TestSLURMParseSqueue:
    """Tests for _parse_squeue."""

    def test_parse_multiple_jobs(self):
        jobs = slurm_mod._parse_squeue(SQUEUE_OUTPUT)
        assert len(jobs) == 3
        assert jobs[0]["job_id"] == "100001"
        assert jobs[0]["job_name"] == "train_model"
        assert jobs[0]["status"] == "RUNNING"

    def test_parse_pending_job(self):
        jobs = slurm_mod._parse_squeue(SQUEUE_OUTPUT)
        pending = [j for j in jobs if j["status"] == "PENDING"]
        assert len(pending) == 1
        assert pending[0]["nodelist_reason"] == "(Priority)"

    def test_parse_empty_string(self):
        jobs = slurm_mod._parse_squeue("")
        assert jobs == []

    def test_header_only(self):
        jobs = slurm_mod._parse_squeue(
            "JOBID|NAME|STATE|TIME|TIME_LIMIT|NODES|NODELIST(REASON)\n"
        )
        assert jobs == []

    def test_short_lines_skipped(self):
        """Lines with fewer than 7 pipe-delimited fields are skipped."""
        jobs = slurm_mod._parse_squeue("100|name|RUNNING\n")
        assert jobs == []


class TestSLURMParseScontrol:
    """Tests for _parse_scontrol_job."""

    def test_parse_scontrol(self):
        detail = slurm_mod._parse_scontrol_job(SCONTROL_JOB_OUTPUT, "100001")
        assert detail["job_id"] == "100001"
        assert detail["job_name"] == "train_model"
        assert detail["status"] == "RUNNING"
        assert detail["partition"] == "gpu"
        assert detail["exec_host"] == "gpu-node-01"
        assert detail["command"] == "/home/moharb/project/run_train.sh"
        assert detail["execution_cwd"] == "/home/moharb/project"

    def test_cpu_time_raw(self):
        detail = slurm_mod._parse_scontrol_job(SCONTROL_JOB_OUTPUT, "100001")
        assert detail["cpu_time_seconds"] == 72060

    def test_max_mem_gb(self):
        detail = slurm_mod._parse_scontrol_job(SCONTROL_JOB_OUTPUT, "100001")
        # 4096M = 4.0 GB
        assert detail["max_mem_gb"] is not None
        assert abs(detail["max_mem_gb"] - 4.0) < 0.01

    def test_stdout_stderr_paths(self):
        detail = slurm_mod._parse_scontrol_job(SCONTROL_JOB_OUTPUT, "100001")
        assert detail["stdout_path"] == "/home/moharb/project/logs/train.out"
        assert detail["stderr_path"] == "/home/moharb/project/logs/train.err"

    def test_time_limit(self):
        detail = slurm_mod._parse_scontrol_job(SCONTROL_JOB_OUTPUT, "100001")
        assert detail["time_limit"] == "08:00:00"

    def test_submit_and_start_time(self):
        detail = slurm_mod._parse_scontrol_job(SCONTROL_JOB_OUTPUT, "100001")
        assert detail["submit_time"] == "2026-03-28T12:00:00"
        assert detail["start_time"] == "2026-03-28T12:00:05"


# ---------------------------------------------------------------------------
# get_tools() contract tests
# ---------------------------------------------------------------------------


class TestLSFGetTools:
    """Test lsf.py get_tools() contract."""

    @patch.object(lsf_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_get_tools_no_kwargs(self, mock_config):
        """get_tools() with no kwargs returns tool list without crashing."""
        tools = lsf_mod.get_tools()
        assert len(tools) == 6  # jobs, status, submit, kill, logs, watch
        # Verify tool names
        names = [_get_tool_name(t) for t in tools]
        assert "cluster_jobs" in names
        assert "cluster_status" in names
        assert "cluster_submit" in names
        assert "cluster_kill" in names
        assert "cluster_logs" in names
        assert "cluster_watch" in names

    @patch.object(lsf_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_get_tools_with_full_kwargs(self, mock_config):
        """get_tools() with all kwargs wires cluster_watch correctly."""
        mock_notify = MagicMock()
        mock_find = MagicMock()
        tools = lsf_mod.get_tools(
            caller_name="TestAgent",
            send_notification=mock_notify,
            find_agent=mock_find,
        )
        assert len(tools) == 6
        # cluster_watch should be the last tool
        watch = tools[-1]
        assert _get_tool_name(watch) == "cluster_watch"


class TestSLURMGetTools:
    """Test slurm.py get_tools() contract."""

    @patch.object(slurm_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_get_tools_no_kwargs(self, mock_config):
        """get_tools() with no kwargs returns tool list without crashing."""
        tools = slurm_mod.get_tools()
        assert len(tools) == 6
        names = [_get_tool_name(t) for t in tools]
        assert "cluster_jobs" in names
        assert "cluster_watch" in names

    @patch.object(slurm_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_get_tools_with_full_kwargs(self, mock_config):
        """get_tools() with all kwargs wires cluster_watch correctly."""
        mock_notify = MagicMock()
        mock_find = MagicMock()
        tools = slurm_mod.get_tools(
            caller_name="TestAgent",
            send_notification=mock_notify,
            find_agent=mock_find,
        )
        assert len(tools) == 6


# ---------------------------------------------------------------------------
# cluster_watch graceful degradation
# ---------------------------------------------------------------------------


class TestClusterWatchDegradation:
    """cluster_watch returns error when send_notification is None."""

    @patch.object(lsf_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_lsf_watch_without_notification(self, mock_config):
        """LSF cluster_watch without send_notification → graceful error."""
        tools = lsf_mod.get_tools()  # No kwargs → send_notification=None
        watch = [t for t in tools if _get_tool_name(t) == "cluster_watch"][0]

        # Run the async tool
        result = asyncio.run(_call_tool(watch, {"job_id": "123"}))
        assert result["isError"] is True
        assert "not available" in result["content"][0]["text"].lower()

    @patch.object(slurm_mod, "_get_config", return_value={"ssh_target": "", "watch_poll_interval": 5})
    def test_slurm_watch_without_notification(self, mock_config):
        """SLURM cluster_watch without send_notification → graceful error."""
        tools = slurm_mod.get_tools()
        watch = [t for t in tools if _get_tool_name(t) == "cluster_watch"][0]
        result = asyncio.run(_call_tool(watch, {"job_id": "456"}))
        assert result["isError"] is True


# ---------------------------------------------------------------------------
# _load_config tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Test _load_config reads sibling YAML file."""

    def test_load_existing_yaml(self, tmp_path):
        """_load_config reads YAML sibling of tool file."""
        tool_py = tmp_path / "lsf.py"
        tool_py.write_text("# dummy\n", encoding="utf-8")
        yaml_file = tmp_path / "lsf.yaml"
        yaml_file.write_text("ssh_target: login.example.com\nwatch_poll_interval: 15\n", encoding="utf-8")

        config = _cluster_mod._load_config(tool_py)
        assert config["ssh_target"] == "login.example.com"
        assert config["watch_poll_interval"] == 15

    def test_load_missing_yaml(self, tmp_path):
        """_load_config returns empty dict when YAML doesn't exist."""
        tool_py = tmp_path / "lsf.py"
        tool_py.write_text("# dummy\n", encoding="utf-8")
        config = _cluster_mod._load_config(tool_py)
        assert config == {}

    def test_load_empty_yaml(self, tmp_path):
        """_load_config returns empty dict for empty YAML file."""
        tool_py = tmp_path / "tool.py"
        tool_py.write_text("# dummy\n", encoding="utf-8")
        yaml_file = tmp_path / "tool.yaml"
        yaml_file.write_text("", encoding="utf-8")
        config = _cluster_mod._load_config(tool_py)
        assert config == {}


# ---------------------------------------------------------------------------
# Response helper tests
# ---------------------------------------------------------------------------


class TestResponseHelpers:
    """Test _text_response, _json_response, _error_response."""

    def test_text_response(self):
        resp = _cluster_mod._text_response("hello")
        assert resp == {"content": [{"type": "text", "text": "hello"}]}
        assert "isError" not in resp

    def test_error_response(self):
        resp = _cluster_mod._error_response("bad thing")
        assert resp["isError"] is True
        assert resp["content"][0]["text"] == "bad thing"

    def test_json_response(self):
        data = {"key": "value", "num": 42}
        resp = _cluster_mod._json_response(data)
        parsed = json.loads(resp["content"][0]["text"])
        assert parsed == data


# ---------------------------------------------------------------------------
# SSH execution tests (mocked)
# ---------------------------------------------------------------------------


class TestRunSSH:
    """Test _run_ssh local and SSH modes."""

    @patch("subprocess.run")
    def test_local_execution(self, mock_run):
        """Empty ssh_target → run locally."""
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        stdout, stderr, rc = _cluster_mod._run_ssh("bjobs -w", ssh_target="")
        assert rc == 0
        assert stdout == "ok"
        # Should not contain SSH command parts
        call_cmd = mock_run.call_args[0][0]
        assert "ssh" not in call_cmd.lower() or call_cmd == "bjobs -w"

    @patch("subprocess.run")
    @patch("os.makedirs")
    def test_ssh_execution(self, mock_makedirs, mock_run):
        """Non-empty ssh_target → wraps command in SSH."""
        mock_run.return_value = MagicMock(stdout="remote_ok", stderr="", returncode=0)
        stdout, stderr, rc = _cluster_mod._run_ssh(
            "bjobs -w", ssh_target="login.example.com", profile="/misc/lsf/conf/profile.lsf"
        )
        assert stdout == "remote_ok"
        call_cmd = mock_run.call_args[0][0]
        assert "ssh" in call_cmd
        assert "login.example.com" in call_cmd
        assert "profile.lsf" in call_cmd


# ---------------------------------------------------------------------------
# Terminal statuses
# ---------------------------------------------------------------------------


class TestTerminalStatuses:
    """Verify terminal status sets."""

    def test_lsf_terminal_statuses(self):
        assert "DONE" in lsf_mod._TERMINAL_STATUSES
        assert "EXIT" in lsf_mod._TERMINAL_STATUSES

    def test_slurm_terminal_statuses(self):
        expected = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"}
        assert expected == slurm_mod._TERMINAL_STATUSES
