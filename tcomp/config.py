"""读取 configs/site.yaml。所有站点相关的值只从这里来。"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_site(path: str | Path = REPO_ROOT / "configs" / "site.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # osf 项目编号可能被 YAML 解析成数字或科学计数，统一成字符串
    cfg["osf_projects"] = {str(k): v for k, v in cfg.get("osf_projects", {}).items()}
    return cfg
