"""The single Git subprocess seam shared across Git operations.

Every Git invocation in the app runs through ``run_git``: no shell, a process
timeout, and ``CalledProcessError``/``TimeoutExpired`` translated to ``GitError``
with any token redacted from captured output. ``GitCommands`` builds token-bearing
authentication and delegates here; the generation workspace runs local, token-free
Git the same way.
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.errors.git_errors import GitError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitResult:
    """Captured standard output and error from a successful Git command."""

    stdout: str
    stderr: str


def run_git(*args: str, cwd: Path, env: dict | None = None, token: str | None = None) -> GitResult:
    """Run a Git command without a shell and translate process failures to ``GitError``.

    The single subprocess seam for every Git invocation in the app. ``token``, when
    supplied, is redacted from captured failures before the error reaches logs; it
    is never placed on the command line — authentication rides ``env``.
    """
    command = " ".join(args[:2])
    logger.info("Running Git command=%s cwd=%s authenticated=%s", command, cwd, token is not None)
    try:
        result = subprocess.run(
            [*args], cwd=cwd.resolve(), timeout=120, text=True, check=True, shell=False, capture_output=True, env=env if env is not None else os.environ.copy()
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Git command timed out command=%s cwd=%s", command, cwd)
        raise GitError("Git command timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Git command failed").strip()
        if token:
            detail = detail.replace(token, "[REDACTED]")
        logger.error("Git command failed command=%s cwd=%s return_code=%s", command, cwd, exc.returncode)
        raise GitError(detail[:1000]) from exc

    logger.info("Git command completed command=%s cwd=%s", command, cwd)
    return GitResult(stdout=result.stdout.strip(), stderr=result.stderr.strip())
