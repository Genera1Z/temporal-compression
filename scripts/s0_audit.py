"""S0a：原始数据清单与齐全性检查（执行规范 §3、§6 S0）。

下载由 run.sh 完成；本脚本只读取 site.yaml 中 paths.raw 下的文件。
产出：
  data/manifest.json            校验和与元数据（之后每次运行都与之比对，确保 raw 未被改动）
  results/S0/manifest.json      同上（随 results 分支回传）
  results/S0/inventory.json     按项目汇总：文件类型计数、各表格列名
  results/S0/checks.json        必需项目是否有视频和表格；raw 是否被改动
  results/S0/run_meta.json      git commit、配置、种子
S0b（复现原文均值）在看过 inventory.json 之后再实现。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tcomp.config import REPO_ROOT, load_site  # noqa: E402
from tcomp.data import manifest as mf  # noqa: E402
from tcomp.provenance import git_commit, run_meta  # noqa: E402


def dump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(REPO_ROOT / "configs" / "site.yaml"))
    ap.add_argument("--run-id", default="local")
    ap.add_argument("--seed", type=int, default=None)  # S0 无随机性，仅记录
    ap.add_argument("--raw-dir", default=None, help="覆盖 site.yaml 的 paths.raw（测试用）")
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "results" / "S0"))
    ap.add_argument("--manifest", default=str(REPO_ROOT / "data" / "manifest.json"))
    args = ap.parse_args(argv)

    cfg = load_site(args.config)
    raw_dir = Path(args.raw_dir or cfg["paths"]["raw"])
    out_dir, man_path = Path(args.out_dir), Path(args.manifest)
    required = [pid for pid, v in cfg["osf_projects"].items() if v.get("role") != "optional"]

    files = mf.build_manifest(raw_dir)
    verify = None
    if man_path.exists():
        old = json.loads(man_path.read_text(encoding="utf-8"))
        verify = mf.verify_manifest(old["files"], files)
        if not verify["ok"]:
            print(f"❌ data/raw 与已登记的清单不一致：{verify}", file=sys.stderr)

    manifest = {"git_commit": git_commit(), "raw_dir": str(raw_dir), "files": files}
    inv = mf.project_inventory(files)
    checks = {"required_projects": required,
              "presence": mf.presence_checks(inv, required),
              "raw_unchanged": verify}
    checks["s0a_pass"] = (all(c["has_video"] and c["has_table"] for c in checks["presence"].values())
                          and (verify is None or verify["ok"]))

    if verify is None or verify["ok"]:
        dump(manifest, man_path)  # raw 被改动时保留旧清单作为证据
    dump(manifest, out_dir / "manifest.json")
    dump(inv, out_dir / "inventory.json")
    dump(checks, out_dir / "checks.json")
    dump(run_meta("S0", args.run_id, args.seed, cfg), out_dir / "run_meta.json")

    for pid, c in checks["presence"].items():
        print(f"{pid}: {c}")
    print(f"S0a pass: {checks['s0a_pass']}")
    if verify is not None and not verify["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
