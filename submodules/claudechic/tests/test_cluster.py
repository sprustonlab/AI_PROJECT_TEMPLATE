"""Tests for claudechic LSF cluster tools (claudechic/cluster.py).

Coverage:
    1. _parse_bjobs_wide()       — real-output fixtures, edge cases
    2. _collapse_lsf_lines()     — continuation vs section-header indent
    3. _parse_bjobs_detail()     — running job, DONE job, multi-line command wrap
    4. _submit_job()             — command-building: env-var injection, bsub flags
    5. _run_lsf() / SSH          — local vs SSH dispatch via shutil.which mock
    6. _list_jobs/_get_job_status/_kill_job — happy-path and error-path
    7. _watch_lsf_exit/_run_watch — watch mechanism (pytest-asyncio)
    8. Config resolution          — env var, config file, defaults
    9. LSF integration            — real cluster (skipped when bsub not in PATH)
"""

from __future__ import annotations

import shutil
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from claudechic.cluster import (
    PYTHONUNBUFFERED_VAR,
    _collapse_lsf_lines,
    _get_conda_envs_dirs,
    _get_job_status,
    _get_lsf_profile,
    _get_ssh_target,
    _get_watch_poll_interval,
    _kill_job,
    _list_jobs,
    _lsf_available,
    _parse_bjobs_detail,
    _parse_bjobs_wide,
    _run_lsf,
    _run_watch,
    _submit_job,
    _watch_lsf_exit,
)


# ---------------------------------------------------------------------------
# Real-output fixtures captured from Janelia cluster (LSF 10.x)
# ---------------------------------------------------------------------------

BJOBS_WIDE_TWO_JOBS = """\
JOBID      USER    STAT  QUEUE      FROM_HOST   EXEC_HOST   JOB_NAME   SUBMIT_TIME
148752751 moharb  RUN   interactive e02u30      4*h07u02    /bin/bash  Mar 15 17:53
148755848 moharb  RUN   gpu_l4     h07u02      8*e10u12    prism_gmm_unet_k1 Mar 15 18:22
"""

BJOBS_WIDE_NO_JOBS = "No unfinished job found\n"

BJOBS_WIDE_HEADER_ONLY = (
    "JOBID      USER    STAT  QUEUE      FROM_HOST   EXEC_HOST   JOB_NAME   SUBMIT_TIME\n"
)

BJOBS_DETAIL_RUNNING = """\
Job <148755848>, Job Name <prism_gmm_unet_k1>, User <moharb>, Project <spruston
                          >, Application <serial>, Status <RUN>, Queue <gpu_l4>
                          , Command <PYTHONUNBUFFERED=1 conda run -n decod
                          e_prism prism-experiment --config config/experiments/
                          figure2/bench_sigma7k_gmm_warmstart_unet_k1.yaml>, Sh
                          are group charged </moharb>, Esub <default>
Sun Mar 15 18:22:37 2026: Submitted from host <h07u02>, CWD <$HOME/DECODE-PRISM
                          >, Output File <logs/gmm_warmstart/gmm_unet_k1_148755
                          848.out>, Error File <logs/gmm_warmstart/gmm_unet_k1_
                          148755848.err>, 8 Task(s), Requested Resources < rusa
                          ge[mem=122880,]>, Requested GPU <num=1:mode=exclusive
                          _process>;
Sun Mar 15 18:22:37 2026: Started 8 Task(s) on Host(s) <8*e10u12>, Allocated 8
                          Slot(s) on Host(s) <8*e10u12>, Execution Home </group
                          s/spruston/home/moharb>, Execution CWD </groups/sprus
                          ton/home/moharb/DECODE-PRISM>;
Sun Mar 15 20:02:32 2026: Resource usage collected.
                          The CPU time used is 31964 seconds.
                          MEM: 13.5 Gbytes;  SWAP: 0 Mbytes;  NTHREAD: 573
                          PGID: 676207;  PIDs: 676207 676262 676264 676890

 RUNLIMIT
 360.0 min

 MEMLIMIT
    120 G

 MEMORY USAGE:
 MAX MEM: 13.5 Gbytes;  AVG MEM: 13.2 Gbytes; MEM Efficiency: 11.26%
"""

BJOBS_DETAIL_DONE = """\
Job <148755855>, Job Name <prism_gmm_unet_k2>, User <moharb>, Project <spruston
                          >, Application <serial>, Status <DONE>, Queue <gpu_l4
                          >, Command <PYTHONUNBUFFERED=1 conda run -n deco
                          de_prism prism-experiment --config config/experiments
                          /figure2/bench_sigma7k_gmm_warmstart_unet_k2.yaml>, S
                          hare group charged </moharb>, Esub <default>
Sun Mar 15 18:22:41 2026: Submitted from host <h07u02>, CWD <$HOME/DECODE-PRISM
                          >, Output File <logs/gmm_warmstart/gmm_unet_k2_148755
                          855.out>, Error File <logs/gmm_warmstart/gmm_unet_k2_
                          148755855.err>, 8 Task(s), Requested Resources < rusa
                          ge[mem=122880,]>, Requested GPU <num=1:mode=exclusive
                          _process>;
Sun Mar 15 18:22:41 2026: Started 8 Task(s) on Host(s) <8*e10u12>, Allocated 8
                          Slot(s) on Host(s) <8*e10u12>, Execution Home </group
                          s/spruston/home/moharb>, Execution CWD </groups/sprus
                          ton/home/moharb/DECODE-PRISM>;
Sun Mar 15 19:58:21 2026: Done successfully. The CPU time used is 42453.1 secon
                          ds.

 RUNLIMIT
 360.0 min

 MEMLIMIT
    120 G

 MEMORY USAGE:
 MAX MEM: 14 Gbytes;  AVG MEM: 13.6 Gbytes; MEM Efficiency: 11.73%
"""

BJOBS_DETAIL_NOT_FOUND = "Job <99999999> is not found\n"

BSUB_SUCCESS_OUTPUT = "Job <99999> is submitted to queue <gpu_l4>.\n"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _fake_run_result(stdout: str, stderr: str = "", rc: int = 0) -> SimpleNamespace:
    """Minimal stand-in for subprocess.CompletedProcess."""
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)


# ===========================================================================
# 1. _parse_bjobs_wide
# ===========================================================================


class TestParseBjobsWide:
    def test_two_jobs_count(self):
        jobs = _parse_bjobs_wide(BJOBS_WIDE_TWO_JOBS)
        assert len(jobs) == 2

    def test_job_fields_present(self):
        jobs = _parse_bjobs_wide(BJOBS_WIDE_TWO_JOBS)
        required = {
            "job_id", "user", "status", "queue", "from_host",
            "exec_host", "job_name", "submit_time",
        }
        for job in jobs:
            assert required == set(job.keys()), f"Missing fields in {job}"

    def test_first_job_parsed_correctly(self):
        jobs = _parse_bjobs_wide(BJOBS_WIDE_TWO_JOBS)
        j = jobs[0]
        assert j["job_id"] == "148752751"
        assert j["user"] == "moharb"
        assert j["status"] == "RUN"
        assert j["queue"] == "interactive"
        assert j["from_host"] == "e02u30"
        assert j["exec_host"] == "4*h07u02"
        assert j["job_name"] == "/bin/bash"
        assert j["submit_time"] == "Mar 15 17:53"

    def test_second_job_parsed_correctly(self):
        jobs = _parse_bjobs_wide(BJOBS_WIDE_TWO_JOBS)
        j = jobs[1]
        assert j["job_id"] == "148755848"
        assert j["queue"] == "gpu_l4"
        assert j["exec_host"] == "8*e10u12"
        assert j["job_name"] == "prism_gmm_unet_k1"
        assert j["submit_time"] == "Mar 15 18:22"

    def test_no_jobs_message_returns_empty_list(self):
        assert _parse_bjobs_wide(BJOBS_WIDE_NO_JOBS) == []

    def test_header_only_returns_empty_list(self):
        assert _parse_bjobs_wide(BJOBS_WIDE_HEADER_ONLY) == []

    def test_empty_string_returns_empty_list(self):
        assert _parse_bjobs_wide("") == []

    def test_blank_lines_skipped(self):
        noisy = "\n\n" + BJOBS_WIDE_TWO_JOBS + "\n\n"
        assert len(_parse_bjobs_wide(noisy)) == 2

    def test_pend_status_parsed(self):
        pend_line = (
            "JOBID      USER    STAT  QUEUE      FROM_HOST   EXEC_HOST   JOB_NAME   SUBMIT_TIME\n"
            "100000001 moharb  PEND  gpu_l4     h07u02      -           my_job     Mar 15 09:00\n"
        )
        jobs = _parse_bjobs_wide(pend_line)
        assert len(jobs) == 1
        assert jobs[0]["status"] == "PEND"


# ===========================================================================
# 2. _collapse_lsf_lines
# ===========================================================================


class TestCollapseLsfLines:
    def test_empty_input(self):
        assert _collapse_lsf_lines("") == ""

    def test_no_continuation_unchanged(self):
        text = "Job <123>, Status <RUN>\n"
        assert _collapse_lsf_lines(text) == text.rstrip("\n")

    def test_section_headers_preserved_as_separate_lines(self):
        text = "Some line\n RUNLIMIT\n 360.0 min\n"
        collapsed = _collapse_lsf_lines(text)
        assert "RUNLIMIT" in collapsed
        lines = collapsed.splitlines()
        assert any("RUNLIMIT" in ln for ln in lines)
        runlimit_line = next(ln for ln in lines if "RUNLIMIT" in ln)
        assert "360.0" not in runlimit_line

    def test_mid_word_break_reconstructed(self):
        raw = (
            "Command <conda run -n decod\n"
            "                          e_prism train.py>\n"
        )
        collapsed = _collapse_lsf_lines(raw)
        assert "decode_prism" in collapsed
        assert "decod e_prism" not in collapsed

    def test_path_split_across_lines_reconstructed(self):
        raw = (
            "Command <python --config config/experiments/\n"
            "                          figure2/bench.yaml>\n"
        )
        collapsed = _collapse_lsf_lines(raw)
        assert "config/experiments/figure2/bench.yaml" in collapsed

    def test_multiple_continuation_lines(self):
        raw = (
            "Start <part1\n"
            "                          part2\n"
            "                          part3>\n"
        )
        collapsed = _collapse_lsf_lines(raw)
        assert "Start <part1part2part3>" in collapsed

    def test_section_header_after_continuation_block(self):
        raw = (
            "Job <123>, Status <RUN>, Queue <gpu_l4\n"
            "                          >, Command <some cmd>\n"
            " RUNLIMIT\n"
            " 360.0 min\n"
        )
        collapsed = _collapse_lsf_lines(raw)
        lines = collapsed.splitlines()
        assert any(ln.strip() == "RUNLIMIT" for ln in lines)


# ===========================================================================
# 3. _parse_bjobs_detail
# ===========================================================================


class TestParseBjobsDetail:
    def test_running_job_id(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["job_id"] == "148755848"

    def test_running_job_name(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["job_name"] == "prism_gmm_unet_k1"

    def test_running_status(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["status"] == "RUN"

    def test_running_queue(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["queue"] == "gpu_l4"

    def test_running_exec_host(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["exec_host"] == "8*e10u12"

    def test_running_submit_time(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["submit_time"] == "Sun Mar 15 18:22:37 2026"

    def test_running_cpu_time(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["cpu_time_seconds"] == 31964

    def test_running_mem_gb(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["mem_gb"] == pytest.approx(13.5)

    def test_running_max_mem_gb(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["max_mem_gb"] == pytest.approx(13.5)

    def test_running_run_limit(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        assert d["run_limit_min"] == pytest.approx(360.0)

    def test_running_command_reconstructed(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        cmd = d["command"]
        assert cmd is not None
        assert "decode_prism" in cmd
        assert "decod e_prism" not in cmd
        assert "config/experiments/figure2/bench_sigma7k_gmm_warmstart_unet_k1.yaml" in cmd

    def test_done_status(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_DONE, "148755855")
        assert d["status"] == "DONE"

    def test_done_job_name(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_DONE, "148755855")
        assert d["job_name"] == "prism_gmm_unet_k2"

    def test_done_cpu_time(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_DONE, "148755855")
        assert d["cpu_time_seconds"] == 42453

    def test_done_max_mem_integer(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_DONE, "148755855")
        assert d["max_mem_gb"] == pytest.approx(14.0)

    def test_done_run_limit(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_DONE, "148755855")
        assert d["run_limit_min"] == pytest.approx(360.0)

    def test_done_command_reconstructed(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_DONE, "148755855")
        cmd = d["command"]
        assert "decode_prism" in cmd
        assert "config/experiments/figure2/bench_sigma7k_gmm_warmstart_unet_k2.yaml" in cmd

    def test_all_keys_present_running(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_RUNNING, "148755848")
        expected_keys = {
            "job_id", "job_name", "status", "queue", "exec_host",
            "submit_time", "cpu_time_seconds", "mem_gb", "max_mem_gb",
            "run_limit_min", "command",
        }
        assert expected_keys == set(d.keys())

    def test_all_keys_present_done(self):
        d = _parse_bjobs_detail(BJOBS_DETAIL_DONE, "148755855")
        expected_keys = {
            "job_id", "job_name", "status", "queue", "exec_host",
            "submit_time", "cpu_time_seconds", "mem_gb", "max_mem_gb",
            "run_limit_min", "command",
        }
        assert expected_keys == set(d.keys())


# ===========================================================================
# 4. _submit_job — command building
# ===========================================================================


class TestSubmitJobCommandBuilding:
    """Patch _run_lsf to capture the bsub command string without hitting LSF."""

    @pytest.fixture(autouse=True)
    def capture_bsub_cmd(self, monkeypatch):
        self._captured: list[str] = []

        def fake_run_lsf(cmd: str, timeout: int = 60):
            self._captured.append(cmd)
            return BSUB_SUCCESS_OUTPUT, "", 0

        monkeypatch.setattr("claudechic.cluster._run_lsf", fake_run_lsf)

    def _last_cmd(self) -> str:
        assert self._captured, "No command was captured"
        return self._captured[-1]

    def test_pythonunbuffered_always_prepended(self):
        _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                     command="conda run -n decode_prism python train.py")
        assert PYTHONUNBUFFERED_VAR in self._last_cmd()

    def test_pythonunbuffered_for_non_conda(self):
        _submit_job(queue="local", cpus=4, walltime="2:00",
                     command="python myscript.py")
        assert PYTHONUNBUFFERED_VAR in self._last_cmd()

    def test_pythonunbuffered_appears_before_command(self):
        _submit_job(queue="local", cpus=1, walltime="1:00",
                     command="python myscript.py")
        cmd = self._last_cmd()
        unbuf_pos = cmd.find(PYTHONUNBUFFERED_VAR)
        user_pos = cmd.find("myscript.py")
        assert unbuf_pos < user_pos

    def test_conda_envs_dirs_added_for_conda_run(self, monkeypatch):
        monkeypatch.setenv("CONDA_ENVS_DIRS", "/test/envs")
        _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                     command="conda run -n decode_prism prism-experiment --config c.yaml")
        assert "CONDA_ENVS_DIRS=/test/envs" in self._last_cmd()

    def test_conda_envs_dirs_not_added_for_non_conda(self):
        _submit_job(queue="local", cpus=4, walltime="2:00",
                     command="python myscript.py")
        assert "CONDA_ENVS_DIRS" not in self._last_cmd()

    def test_bsub_env_flag_never_used(self):
        _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                     command="conda run -n decode_prism prism-experiment --config c.yaml",
                     job_name="mytest", gpus=1)
        assert "-env" not in self._last_cmd()

    def test_gpu_flag_present_when_gpus_gt_0(self):
        _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                     command="python train.py", gpus=1)
        assert "-gpu" in self._last_cmd()
        assert "num=1" in self._last_cmd()

    def test_gpu_flag_absent_when_gpus_eq_0(self):
        _submit_job(queue="local", cpus=4, walltime="2:00",
                     command="python train.py", gpus=0)
        assert "-gpu" not in self._last_cmd()

    def test_multi_gpu_flag(self):
        _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                     command="python train.py", gpus=4)
        assert "num=4" in self._last_cmd()

    def test_job_name_passed_with_j_flag(self):
        _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                     command="python train.py", job_name="my_exp")
        cmd = self._last_cmd()
        assert "-J" in cmd
        assert "my_exp" in cmd

    def test_no_j_flag_when_job_name_empty(self):
        _submit_job(queue="local", cpus=4, walltime="2:00",
                     command="python train.py", job_name="")
        assert "-J" not in self._last_cmd()

    def test_stdout_path(self):
        _submit_job(queue="local", cpus=4, walltime="2:00",
                     command="python train.py", stdout_path="logs/job.out")
        cmd = self._last_cmd()
        assert "-o" in cmd
        assert "logs/job.out" in cmd

    def test_stderr_path(self):
        _submit_job(queue="local", cpus=4, walltime="2:00",
                     command="python train.py", stderr_path="logs/job.err")
        cmd = self._last_cmd()
        assert "-e" in cmd
        assert "logs/job.err" in cmd

    def test_queue_flag(self):
        _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                     command="python train.py")
        cmd = self._last_cmd()
        assert "-q" in cmd
        assert "gpu_l4" in cmd

    def test_cmd_starts_with_bsub(self):
        _submit_job(queue="local", cpus=1, walltime="1:00",
                     command="python train.py")
        assert self._last_cmd().startswith("bsub")

    def test_returns_job_id(self):
        result = _submit_job(queue="gpu_l4", cpus=8, walltime="48:00",
                              command="python train.py")
        assert result["job_id"] == "99999"

    def test_bsub_failure_raises(self, monkeypatch):
        monkeypatch.setattr(
            "claudechic.cluster._run_lsf",
            lambda cmd, timeout=60: ("", "Queue not found", 1),
        )
        with pytest.raises(RuntimeError, match="bsub failed"):
            _submit_job(queue="bad", cpus=1, walltime="1:00",
                         command="python train.py")


# ===========================================================================
# 5. SSH detection
# ===========================================================================


class TestSSHDetection:
    def test_local_lsf_runs_directly(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster.shutil.which", lambda x: "/usr/bin/bsub")
        mock_run = MagicMock(return_value=_fake_run_result("output", "", 0))
        monkeypatch.setattr("claudechic.cluster.subprocess.run", mock_run)

        _run_lsf("bjobs -w 2>&1")

        called_cmd = mock_run.call_args[0][0]
        assert "ssh" not in called_cmd
        assert "bjobs -w 2>&1" in called_cmd

    def test_no_lsf_wraps_in_ssh(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster.shutil.which", lambda x: None)
        mock_run = MagicMock(return_value=_fake_run_result("output", "", 0))
        monkeypatch.setattr("claudechic.cluster.subprocess.run", mock_run)

        _run_lsf("bjobs -w 2>&1")

        called_cmd = mock_run.call_args[0][0]
        assert "ssh" in called_cmd

    def test_ssh_uses_configured_target(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster.shutil.which", lambda x: None)
        monkeypatch.setenv("LSF_SSH_TARGET", "mylogin.example.com")
        mock_run = MagicMock(return_value=_fake_run_result("", "", 0))
        monkeypatch.setattr("claudechic.cluster.subprocess.run", mock_run)

        _run_lsf("bjobs -w")

        called_cmd = mock_run.call_args[0][0]
        assert "mylogin.example.com" in called_cmd

    def test_ssh_sources_lsf_profile(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster.shutil.which", lambda x: None)
        mock_run = MagicMock(return_value=_fake_run_result("", "", 0))
        monkeypatch.setattr("claudechic.cluster.subprocess.run", mock_run)

        _run_lsf("bjobs -w")

        called_cmd = mock_run.call_args[0][0]
        # Default profile path
        assert "/misc/lsf/conf/profile.lsf" in called_cmd

    def test_return_values_propagated(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster.shutil.which", lambda x: "/usr/bin/bsub")
        monkeypatch.setattr(
            "claudechic.cluster.subprocess.run",
            lambda *a, **kw: _fake_run_result("hello", "warn", 42),
        )
        stdout, stderr, rc = _run_lsf("bjobs -w")
        assert stdout == "hello"
        assert stderr == "warn"
        assert rc == 42


# ===========================================================================
# 6. Core operations (sync layer)
# ===========================================================================


class TestListJobs:
    def test_returns_list(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster._run_lsf",
                            lambda cmd, **kw: (BJOBS_WIDE_TWO_JOBS, "", 0))
        assert len(_list_jobs()) == 2

    def test_no_jobs_returns_empty(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster._run_lsf",
                            lambda cmd, **kw: (BJOBS_WIDE_NO_JOBS, "", 0))
        assert _list_jobs() == []

    def test_failure_raises(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster._run_lsf",
                            lambda cmd, **kw: ("", "LSF down", 255))
        with pytest.raises(RuntimeError):
            _list_jobs()


class TestGetJobStatus:
    def test_running_job(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster._run_lsf",
                            lambda cmd, **kw: (BJOBS_DETAIL_RUNNING, "", 0))
        d = _get_job_status("148755848")
        assert d["status"] == "RUN"

    def test_not_found_raises(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster._run_lsf",
                            lambda cmd, **kw: (BJOBS_DETAIL_NOT_FOUND, "", 0))
        with pytest.raises(ValueError, match="not found"):
            _get_job_status("99999999")


class TestKillJob:
    def test_success(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster._run_lsf",
                            lambda cmd, **kw: ("Job <123> terminated\n", "", 0))
        result = _kill_job("123")
        assert result["success"] is True

    def test_failure_raises(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster._run_lsf",
                            lambda cmd, **kw: ("", "Permission denied", 255))
        with pytest.raises(RuntimeError):
            _kill_job("123")


# ===========================================================================
# 7. Watch mechanism
# ===========================================================================


class TestWatchLsfExit:
    """Test the low-level _watch_lsf_exit coroutine."""

    @pytest.mark.asyncio
    async def test_returns_on_done(self, monkeypatch):
        """Should return immediately when job status is DONE."""
        call_count = 0

        def fake_get_status(job_id):
            nonlocal call_count
            call_count += 1
            return {"job_id": job_id, "status": "DONE", "job_name": "test",
                    "cpu_time_seconds": 100, "max_mem_gb": 8.0}

        monkeypatch.setattr("claudechic.cluster._get_job_status", fake_get_status)

        result = await _watch_lsf_exit("123", poll_interval=0)
        assert result["status"] == "DONE"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_returns_on_exit(self, monkeypatch):
        call_count = 0

        def fake_get_status(job_id):
            nonlocal call_count
            call_count += 1
            return {"job_id": job_id, "status": "EXIT", "job_name": "test"}

        monkeypatch.setattr("claudechic.cluster._get_job_status", fake_get_status)

        result = await _watch_lsf_exit("123", poll_interval=0)
        assert result["status"] == "EXIT"

    @pytest.mark.asyncio
    async def test_polls_until_terminal(self, monkeypatch):
        """Should poll multiple times if job is still running."""
        statuses = iter(["RUN", "RUN", "DONE"])

        def fake_get_status(job_id):
            return {"job_id": job_id, "status": next(statuses), "job_name": "test"}

        monkeypatch.setattr("claudechic.cluster._get_job_status", fake_get_status)

        result = await _watch_lsf_exit("123", poll_interval=0)
        assert result["status"] == "DONE"

    @pytest.mark.asyncio
    async def test_handles_job_disappearing(self, monkeypatch):
        """If bjobs raises (job disappeared), return UNKNOWN status."""
        def fake_get_status(job_id):
            raise ValueError(f"Job {job_id} not found")

        monkeypatch.setattr("claudechic.cluster._get_job_status", fake_get_status)

        result = await _watch_lsf_exit("123", poll_interval=0)
        assert result["status"] == "UNKNOWN"


class TestRunWatch:
    """Test the high-level _run_watch coroutine."""

    @pytest.mark.asyncio
    async def test_notifies_agent_on_done(self, monkeypatch):
        """Should call send_notification when job completes."""
        monkeypatch.setattr(
            "claudechic.cluster._get_job_status",
            lambda job_id: {"job_id": job_id, "status": "DONE",
                            "job_name": "my_train", "cpu_time_seconds": 3600,
                            "max_mem_gb": 12.0},
        )

        mock_agent = MagicMock()
        notifications = []

        def mock_send(agent, message, **kwargs):
            notifications.append((agent, message))

        def mock_find(name):
            return mock_agent, None

        await _run_watch(
            job_id="123",
            condition="lsf_exit",
            caller_name="TestAgent",
            send_notification=mock_send,
            find_agent=mock_find,
            poll_interval=0,
        )

        assert len(notifications) == 1
        agent, msg = notifications[0]
        assert agent is mock_agent
        assert "123" in msg
        assert "my_train" in msg
        assert "completed successfully" in msg
        assert "1.0h" in msg  # 3600s = 1.0h
        assert "12.0 GB" in msg

    @pytest.mark.asyncio
    async def test_notifies_agent_on_exit(self, monkeypatch):
        monkeypatch.setattr(
            "claudechic.cluster._get_job_status",
            lambda job_id: {"job_id": job_id, "status": "EXIT",
                            "job_name": "failed_job"},
        )

        notifications = []

        def mock_send(agent, message, **kwargs):
            notifications.append(message)

        await _run_watch(
            job_id="456",
            condition="lsf_exit",
            caller_name="TestAgent",
            send_notification=mock_send,
            find_agent=lambda name: (MagicMock(), None),
            poll_interval=0,
        )

        assert len(notifications) == 1
        assert "FAILED" in notifications[0]

    @pytest.mark.asyncio
    async def test_handles_missing_agent(self, monkeypatch):
        """Should not crash if the calling agent is gone."""
        monkeypatch.setattr(
            "claudechic.cluster._get_job_status",
            lambda job_id: {"job_id": job_id, "status": "DONE", "job_name": "x"},
        )

        # Agent not found
        await _run_watch(
            job_id="789",
            condition="lsf_exit",
            caller_name="GoneAgent",
            send_notification=MagicMock(),
            find_agent=lambda name: (None, "not found"),
            poll_interval=0,
        )
        # Should not raise

    @pytest.mark.asyncio
    async def test_no_caller_name_logs_only(self, monkeypatch):
        """With no caller_name, should complete without sending notification."""
        monkeypatch.setattr(
            "claudechic.cluster._get_job_status",
            lambda job_id: {"job_id": job_id, "status": "DONE", "job_name": "x"},
        )

        mock_send = MagicMock()
        await _run_watch(
            job_id="999",
            condition="lsf_exit",
            caller_name=None,
            send_notification=mock_send,
            find_agent=MagicMock(),
            poll_interval=0,
        )

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_condition_returns_early(self):
        """Unknown condition should log error and return without crash."""
        mock_send = MagicMock()
        await _run_watch(
            job_id="111",
            condition="unknown_thing",
            caller_name="TestAgent",
            send_notification=mock_send,
            find_agent=MagicMock(),
            poll_interval=0,
        )
        mock_send.assert_not_called()


# ===========================================================================
# 8. Config resolution
# ===========================================================================


class TestClusterConfig:
    def test_ssh_target_from_env(self, monkeypatch):
        monkeypatch.setenv("LSF_SSH_TARGET", "custom.host.com")
        assert _get_ssh_target() == "custom.host.com"

    def test_ssh_target_default(self, monkeypatch):
        monkeypatch.delenv("LSF_SSH_TARGET", raising=False)
        # With no config, should return default
        monkeypatch.setattr("claudechic.cluster.CONFIG", {})
        assert _get_ssh_target() == "submit.int.janelia.org"

    def test_lsf_profile_from_env(self, monkeypatch):
        monkeypatch.setenv("LSF_PROFILE", "/custom/profile.lsf")
        assert _get_lsf_profile() == "/custom/profile.lsf"

    def test_lsf_profile_default(self, monkeypatch):
        monkeypatch.delenv("LSF_PROFILE", raising=False)
        monkeypatch.setattr("claudechic.cluster.CONFIG", {})
        assert _get_lsf_profile() == "/misc/lsf/conf/profile.lsf"

    def test_conda_envs_dirs_from_env(self, monkeypatch):
        monkeypatch.setenv("CONDA_ENVS_DIRS", "/my/envs")
        assert _get_conda_envs_dirs() == "/my/envs"

    def test_watch_poll_interval_default(self, monkeypatch):
        monkeypatch.setattr("claudechic.cluster.CONFIG", {})
        assert _get_watch_poll_interval() == 30

    def test_watch_poll_interval_from_config(self, monkeypatch):
        monkeypatch.setattr(
            "claudechic.cluster.CONFIG",
            {"cluster": {"watch_poll_interval": 60}},
        )
        assert _get_watch_poll_interval() == 60

    def test_ssh_target_from_config(self, monkeypatch):
        monkeypatch.delenv("LSF_SSH_TARGET", raising=False)
        monkeypatch.setattr(
            "claudechic.cluster.CONFIG",
            {"cluster": {"ssh_target": "fromconfig.host.com"}},
        )
        assert _get_ssh_target() == "fromconfig.host.com"

    def test_env_var_takes_precedence_over_config(self, monkeypatch):
        monkeypatch.setenv("LSF_SSH_TARGET", "fromenv.host.com")
        monkeypatch.setattr(
            "claudechic.cluster.CONFIG",
            {"cluster": {"ssh_target": "fromconfig.host.com"}},
        )
        assert _get_ssh_target() == "fromenv.host.com"


# ===========================================================================
# 9. LSF integration tests — require real bsub in PATH
# ===========================================================================

_lsf_skip = pytest.mark.skipif(
    shutil.which("bsub") is None,
    reason="LSF not available (bsub not in PATH)",
)


@_lsf_skip
class TestLSFIntegration:
    """Integration tests against the real cluster — no mocks.

    Pattern #1 (Contract-free test doubles): These tests verify that parser
    fixtures match what the live cluster actually emits.
    """

    def test_lsf_available_returns_true(self):
        assert _lsf_available() is True

    def test_bjobs_w_returns_zero_exit_code(self):
        stdout, stderr, rc = _run_lsf("bjobs -w 2>&1")
        assert rc == 0, f"bjobs -w returned rc={rc}: {stdout!r} {stderr!r}"

    def test_bjobs_output_is_parseable(self):
        stdout, _, _ = _run_lsf("bjobs -w 2>&1")
        jobs = _parse_bjobs_wide(stdout)
        assert isinstance(jobs, list)

    def test_list_jobs_returns_list(self):
        jobs = _list_jobs()
        assert isinstance(jobs, list)

    def test_real_bjobs_header_columns(self):
        stdout, _, rc = _run_lsf("bjobs -w 2>&1")
        assert rc == 0
        header = stdout.splitlines()[0] if stdout.strip() else ""
        if "JOBID" in header:
            for col in ("JOBID", "USER", "STAT", "QUEUE", "JOB_NAME"):
                assert col in header

    def test_real_jobs_have_expected_keys(self):
        jobs = _list_jobs()
        if not jobs:
            pytest.skip("No jobs in queue")
        required = {"job_id", "user", "status", "queue", "from_host",
                     "exec_host", "job_name", "submit_time"}
        for job in jobs:
            assert not (required - set(job.keys())), f"Missing keys: {job}"

    def test_real_job_status_is_known(self):
        jobs = _list_jobs()
        if not jobs:
            pytest.skip("No jobs in queue")
        known = {"RUN", "PEND", "DONE", "EXIT", "USUSP", "SSUSP",
                 "WAIT", "ZOMBI", "UNKWN"}
        for job in jobs:
            assert job["status"] in known, f"Unknown status: {job['status']}"

    def test_round_trip_consistency(self):
        stdout, _, _ = _run_lsf("bjobs -w 2>&1")
        direct = _parse_bjobs_wide(stdout)
        via_tool = _list_jobs()
        assert len(via_tool) == len(direct)
