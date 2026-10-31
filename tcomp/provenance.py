"""运行记录：git commit、配置、种子（执行规范 §0 第 4 条）。"""
from __future__ import annotations

import datetime as _dt
import os
import platform
import subprocess
import sys

from tcomp.config import REPO_ROOT


def git_commit() -> str:
    env = os.environ.get("GIT_COMMIT")  # run.sh 已计算（含 -dirty 标记）
    if env:
        return env
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO_ROOT, text=True
        ).strip()
        return sha + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def run_meta(stage: str, run_id: str, seed: int | None, config: dict) -> dict:
    return {
        "stage": stage,
        "run_id": run_id,
        "seed": seed,
        "git_commit": git_commit(),
        "utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "host": platform.node(),
        "python": sys.version.split()[0],
        "config": config,
    }
