"""Docker sandbox for running untrusted shell commands.

Every command runs in a fresh, throwaway container with:

* ``--network none``        — no egress, no exfiltration, no cloud metadata
* ``--read-only`` root FS   — immutable image; writes only to tmpfs / workspace
* current host UID:GID      — file permissions work naturally on bind mounts
* ``--cap-drop ALL``        — strips dangerous Linux capabilities
* ``no-new-privileges``     — blocks setuid escalation
* CPU / memory / pids limits — prevents resource exhaustion
* ``ulimit nofile/fsize``   — prevents fd exhaustion and file bombs
* ``--rm``                  — ephemeral; no state between runs
* hard subprocess timeout   — kills runaway commands and cleans up the container

Running as the current host user (rather than nobody) means the container can
read/write project files normally. The read-only root FS, dropped capabilities,
no network, and resource limits still provide a strong boundary: the agent
cannot modify system files, exfiltrate data, or exhaust host resources.

Containers share the host kernel, so this is a strong boundary against the
*agent*, not against a kernel exploit. For genuinely hostile multi-tenant
workloads, pair with gVisor or a microVM.

The ``workdir`` is validated to be within the current working directory so the
sandbox can never mount ``/etc``, ``/``, or other sensitive host paths.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass

from animas import Context, Service

from .utils.text import decode_text

DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_TIMEOUT = 30
DEFAULT_MEMORY = "256m"
DEFAULT_CPUS = "0.5"
DEFAULT_PIDS_LIMIT = 64
OUTPUT_CAP = 8192  # bytes per stream
KILL_TIMEOUT = 5  # seconds to wait for docker kill/rm on cleanup

# Process-wide sandbox policy. Sandboxed by default; the CLI sets this
# explicitly from --no-sandbox so the tool and the flag share one source of
# truth instead of a side-channel environment variable.
_sandbox_enabled = True


def set_sandbox_enabled(enabled: bool) -> None:
    """Set whether run_command executes inside the Docker sandbox."""
    global _sandbox_enabled
    _sandbox_enabled = bool(enabled)


def sandbox_enabled() -> bool:
    """Return whether run_command currently executes sandboxed."""
    return _sandbox_enabled


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def _safe_workdir(workdir: str) -> str:
    """Return an absolute path for *workdir*, confined to the CWD tree.

    Raises ValueError if the resolved path escapes the current working
    directory, preventing the sandbox from mounting sensitive host paths
    such as ``/etc`` or ``/``.
    """
    cwd = os.path.abspath(os.getcwd())
    target = os.path.abspath(os.path.join(cwd, workdir))
    if target != cwd and not target.startswith(cwd + os.sep):
        raise ValueError(
            f"workdir {workdir!r} resolves to {target}, which is outside "
            f"the current working directory {cwd!r}"
        )
    return target


def _current_uid_gid() -> str:
    """Return a UID:GID string for the container's --user flag.

    On POSIX, use the current user so bind-mount permissions work naturally.
    On Windows (no ``os.getuid``), omit the explicit user and let the image's
    default apply — Docker Desktop maps the host user automatically.
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is not None and getgid is not None:
        return f"{getuid()}:{getgid()}"
    return ""  # caller omits --user when empty


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
    uid_gid = _current_uid_gid()
    user_flag = ["--user", uid_gid] if uid_gid else []
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
            *user_flag,
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
            "--ulimit",
            "nofile=256:256",
            "--ulimit",
            "fsize=52428800",
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
    the named container is killed and removed to avoid orphans. If the Docker
    CLI or daemon is unavailable, returns an error result (fail closed).
    """
    try:
        resolved_workdir = _safe_workdir(workdir)
    except ValueError as error:
        return SandboxResult(
            stdout="",
            stderr=str(error),
            exit_code=1,
            timed_out=False,
        )

    docker_cmd, container_name = _build_docker_cmd(
        command=command,
        timeout=timeout,
        workdir=resolved_workdir,
        image=image,
        memory=memory,
        cpus=cpus,
        pids_limit=pids_limit,
    )
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
    except FileNotFoundError:
        return SandboxResult(
            stdout="",
            stderr=(
                "Error: docker CLI not found. Install Docker to use run_command. "
                "See https://docs.docker.com/engine/install/"
            ),
            exit_code=127,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as error:
        _kill_container(container_name)
        stdout = decode_text(getattr(error, "stdout", None))
        stderr = decode_text(getattr(error, "stderr", None))
        return SandboxResult(
            stdout=_cap(stdout),
            stderr=_cap(stderr),
            exit_code=124,
            timed_out=True,
        )


def _kill_container(name: str) -> None:
    """Best-effort kill + remove of a sandbox container on timeout."""
    subprocess.run(["docker", "kill", name], capture_output=True, timeout=KILL_TIMEOUT)
    subprocess.run(
        ["docker", "rm", "-f", name], capture_output=True, timeout=KILL_TIMEOUT
    )


def _cap(text: str) -> str:
    if len(text) > OUTPUT_CAP:
        return text[:OUTPUT_CAP] + f"\n[output capped at {OUTPUT_CAP} bytes]"
    return text


class SandboxService(Service):
    """Process-confinement capability mounted as ``ctx.sandbox``.

    Delegates to :func:`run_in_sandbox`; the function stays available for
    direct use and tests. Consumers call ``ctx.sandbox.run(...)``.
    """

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "sandbox")

    def run(
        self,
        command: str,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        workdir: str = ".",
        image: str = DEFAULT_IMAGE,
        memory: str = DEFAULT_MEMORY,
        cpus: str = DEFAULT_CPUS,
        pids_limit: int = DEFAULT_PIDS_LIMIT,
    ) -> SandboxResult:
        """Run *command* inside a throwaway Docker container."""
        return run_in_sandbox(
            command,
            timeout=timeout,
            workdir=workdir,
            image=image,
            memory=memory,
            cpus=cpus,
            pids_limit=pids_limit,
        )
