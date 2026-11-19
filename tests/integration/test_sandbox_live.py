"""Live integration tests for the Docker sandbox.

These tests require a running Docker daemon and are skipped otherwise.
They exercise every security property of home-swe-home's sandbox against a real
container runtime, not mocks.
"""

from __future__ import annotations

import subprocess

import pytest

from home_swe_home.sandbox import run_in_sandbox

_docker_available = (
    subprocess.run(["docker", "info"], capture_output=True).returncode == 0
)


@pytest.mark.skipif(not _docker_available, reason="Docker daemon not available")
class TestSandboxLive:
    def test_basic_command(self):
        r = run_in_sandbox("echo live-basic", timeout=10)
        assert r.stdout.strip() == "live-basic"
        assert r.exit_code == 0
        assert not r.timed_out

    def test_readonly_root(self):
        r = run_in_sandbox("touch /etc/should-fail", timeout=10)
        assert r.exit_code != 0

    def test_no_network(self):
        r = run_in_sandbox(
            'python3 -c "import socket; s=socket.socket(); s.settimeout(2); '
            "s.connect(('example.com',80))\"",
            timeout=10,
        )
        assert r.exit_code != 0

    def test_non_root_user(self):
        r = run_in_sandbox("id -u", timeout=10)
        assert r.stdout.strip() != "0"

    def test_capabilities_dropped(self):
        r = run_in_sandbox("mount -t tmpfs tmpfs /mnt", timeout=10)
        assert r.exit_code != 0
        assert "superuser" in r.stderr

    def test_memory_limit(self):
        r = run_in_sandbox('python3 -c "data=bytearray(500*1024*1024)"', timeout=20)
        assert r.exit_code != 0

    def test_timeout_kills_command(self):
        r = run_in_sandbox("sleep 100", timeout=2)
        assert r.timed_out is True
        assert r.exit_code == 124

    def test_no_orphaned_containers(self):
        run_in_sandbox("echo x", timeout=10)
        oc = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=sandbox-",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
        )
        orphans = [n for n in oc.stdout.strip().splitlines() if n]
        assert orphans == []

    def test_output_capped(self):
        r = run_in_sandbox("python3 -c \"print('x'*20000)\"", timeout=10)
        assert len(r.stdout) < 20000
        assert "capped" in r.stdout

    def test_workspace_writable(self):
        r = run_in_sandbox(
            "echo live-write > /workspace/live-integration.txt && "
            "cat /workspace/live-integration.txt",
            timeout=10,
        )
        assert r.stdout.strip() == "live-write"

    def test_error_propagation(self):
        r = run_in_sandbox("command-that-does-not-exist", timeout=10)
        assert r.exit_code != 0

    def test_workdir_escape_blocked(self):
        r = run_in_sandbox("echo x", workdir="/etc")
        assert r.exit_code == 1
        assert "outside the current working directory" in r.stderr

    def test_file_size_limit(self):
        r = run_in_sandbox(
            "python3 -c \"open('/workspace/bigfile','w').write('x'*(60*1024*1024))\"",
            timeout=15,
        )
        assert r.exit_code != 0

    def teardown_method(self):
        run_in_sandbox(
            "rm -f /workspace/live-integration.txt /workspace/bigfile",
            timeout=10,
        )
