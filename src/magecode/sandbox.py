"""Docker sandbox for running untrusted shell commands.

Every command runs in a fresh, throwaway container with:

* ``--network none``        — no egress, no exfiltration, no cloud metadata
* ``--read-only`` root FS   — immutable image; writes only to tmpfs / workspace
* current host UID:GID      — file permissions work naturally on bind mounts
* ``--cap-drop ALL``        — strips dangerous Linux capabilities
* ``no-new-privileges``     — blocks setuid escalation
* CPU / memory / pids limits — prevents resource exhaustion
* ``--rm``                  — ephemeral; no state between runs
* hard subprocess timeout   — kills runaway commands and cleans up the container

Running as the current host user (rather than nobody) means the container can
read/write project files normally. The read-only root FS, dropped capabilities,
no network, and resource limits still provide a strong boundary: the agent
cannot modify system files, exfiltrate data, or exhaust host resources.

Containers share the host kernel, so this is a strong boundary against the
*agent*, not against a kernel exploit. For genuinely hostile multi-tenant
workloads, pair with gVisor or a microVM.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass

DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_TIMEOUT = 30
DEFAULT_MEMORY = "256m"
DEFAULT_CPUS = "0.5"
DEFAULT_PIDS_LIMIT = 64
OUTPUT_CAP = 8192  # bytes per stream


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def _build_docker_cmd(
    command: str,
    *,
    timeout: int,
    workdir: str,
    image: str,
    memory: str,
    cpus: str,
    pids_limit: int,
) -> tuple[list[str], str]:
    """Return (docker_cmd, container_name)."""
    name = f"sandbox-{uuid.uuid4().hex[:12]}"
    return (
        [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            memory,
            "--memory-swap",
            memory,
            "--cpus",
            cpus,
            "--pids-limit",
            str(pids_limit),
            "-v",
            f"{workdir}:/workspace:rw",
            "-w",
            "/workspace",
            image,
            "sh",
            "-c",
            command,
        ],
        name,
    )


def run_in_sandbox(
    command: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str = ".",
    image: str = DEFAULT_IMAGE,
    memory: str = DEFAULT_MEMORY,
    cpus: str = DEFAULT_CPUS,
    pids_limit: int = DEFAULT_PIDS_LIMIT,
) -> SandboxResult:
    """Run *command* inside a Docker sandbox and return the result.

    The container is removed on exit (``--rm``). If the subprocess times out,
    the named container is killed and removed to avoid orphans.
    """
    docker_cmd, container_name = _build_docker_cmd(
        command=command,
        timeout=timeout,
        workdir=workdir,
        image=image,
        memory=memory,
        cpus=cpus,
        pids_limit=pids_limit,
    )
    container_name = docker_cmd[4]  # the value after --name
    try:
        completed = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        return SandboxResult(
            stdout=_cap(completed.stdout),
            stderr=_cap(completed.stderr),
            exit_code=completed.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as error:
        _kill_container(container_name)
        stdout = _decode(getattr(error, "stdout", None))
        stderr = _decode(getattr(error, "stderr", None))
        return SandboxResult(
            stdout=_cap(stdout),
            stderr=_cap(stderr),
            exit_code=124,
            timed_out=True,
        )


def _kill_container(name: str) -> None:
    """Best-effort kill + remove of a sandbox container on timeout."""
    subprocess.run(["docker", "kill", name], capture_output=True)
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _cap(text: str) -> str:
    if len(text) > OUTPUT_CAP:
        return text[:OUTPUT_CAP] + f"\n[output capped at {OUTPUT_CAP} bytes]"
    return text
