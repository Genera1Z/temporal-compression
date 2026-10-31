"""原始数据清单：校验和、文件类型、视频元数据、表格列名（S0a）。

只读取 data/raw，从不写入（执行规范 §0 禁止事项）。
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path, PurePosixPath

VIDEO_EXT = {".mp4", ".avi", ".mov", ".webm", ".mkv", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv"}
TABLE_EXT = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".sav", ".dta", ".rds", ".rdata", ".json"}
SCRIPT_EXT = {".r", ".rmd", ".py", ".m", ".ipynb", ".jasp", ".js", ".psyexp", ".html", ".qmd"}
DOC_EXT = {".pdf", ".docx", ".doc", ".md", ".odt", ".pptx"}
ARCHIVE_EXT = {".zip"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}

SKIP_NAMES = {".complete", ".DS_Store"}
N_DISTINCT = 5      # 每列记录的不同取值个数（仅用于了解列含义）
MAX_STR = 60


def classify(name: str) -> str:
    ext = PurePosixPath(name.lower()).suffix
    for kind, exts in (("video", VIDEO_EXT), ("table", TABLE_EXT), ("script", SCRIPT_EXT),
                       ("doc", DOC_EXT), ("archive", ARCHIVE_EXT), ("image", IMAGE_EXT)):
        if ext in exts:
            return kind
    return "other"


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def probe_video(path: Path) -> dict:
    """容器层面的元数据；不解码全部帧。失败时记录错误而不是中断。"""
    try:
        import av
        with av.open(str(path)) as c:
            s = c.streams.video[0]
            dur = float(s.duration * s.time_base) if s.duration else (
                c.duration / 1e6 if c.duration else None)
            fps = float(s.average_rate) if s.average_rate else None
            return {"duration_s": dur, "fps": fps, "n_frames": s.frames or None,
                    "width": s.codec_context.width, "height": s.codec_context.height,
                    "codec": s.codec_context.name}
    except Exception as e:  # noqa: BLE001
        return {"probe_error": f"{type(e).__name__}: {e}"}


def _short(v) -> str:
    s = str(v)
    return s if len(s) <= MAX_STR else s[:MAX_STR] + "…"


def _frame_summary(df) -> dict:
    return {
        "n_rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "examples": {str(c): [_short(v) for v in df[c].dropna().unique()[:N_DISTINCT]]
                     for c in df.columns},
    }


def summarize_table(path: Path) -> dict:
    """读出列名、行数和每列少量示例值。失败时记录错误。"""
    import pandas as pd
    ext = path.suffix.lower()
    try:
        if ext in {".csv", ".tsv", ".txt"}:
            df = pd.read_csv(path, sep=None, engine="python")
            return _frame_summary(df)
        if ext in {".xlsx", ".xls"}:
            sheets = pd.read_excel(path, sheet_name=None)
            return {"sheets": {name: _frame_summary(df) for name, df in sheets.items()}}
        if ext == ".sav":
            return _frame_summary(pd.read_spss(path))
        if ext == ".dta":
            return _frame_summary(pd.read_stata(path))
        if ext == ".json":
            return _frame_summary(pd.read_json(path))
        return {"summary_error": f"unsupported table format {ext}"}
    except Exception as e:  # noqa: BLE001
        return {"summary_error": f"{type(e).__name__}: {e}"}


def summarize_zip(path: Path) -> dict:
    """只列出压缩包成员并分类，不解压（解压留到 S0b，写入 data/interim）。"""
    try:
        with zipfile.ZipFile(path) as z:
            members = [i for i in z.infolist() if not i.is_dir()
                       and not i.filename.startswith("__MACOSX/")]
            return {"members": [{"name": i.filename, "bytes": i.file_size,
                                 "kind": classify(i.filename)} for i in members]}
    except Exception as e:  # noqa: BLE001
        return {"summary_error": f"{type(e).__name__}: {e}"}


def describe_file(path: Path, raw_dir: Path) -> dict:
    rel = path.relative_to(raw_dir)
    rec = {"project": rel.parts[0], "path": rel.as_posix(), "bytes": path.stat().st_size,
           "sha256": sha256(path), "kind": classify(path.name)}
    if rec["kind"] == "video":
        rec["video"] = probe_video(path)
    elif rec["kind"] == "table":
        rec["table"] = summarize_table(path)
    elif rec["kind"] == "archive":
        rec["archive"] = summarize_zip(path)
    return rec


def iter_raw_files(raw_dir: Path, projects: list[str] | None = None):
    for proj in sorted(p for p in raw_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if projects is not None and proj.name not in projects:
            continue
        for f in sorted(proj.rglob("*")):
            if f.is_file() and f.name not in SKIP_NAMES:
                yield f


def build_manifest(raw_dir: Path, projects: list[str] | None = None) -> list[dict]:
    raw_dir = Path(raw_dir)
    return [describe_file(f, raw_dir) for f in iter_raw_files(raw_dir, projects)]


def verify_manifest(old_files: list[dict], new_files: list[dict]) -> dict:
    """对比两次清单。已登记项目里的改动、缺失、新增都算违规；新项目的文件算正常新增。"""
    old = {r["path"]: r for r in old_files}
    new = {r["path"]: r for r in new_files}
    known_projects = {r["project"] for r in old_files}
    modified = sorted(p for p in old.keys() & new.keys() if old[p]["sha256"] != new[p]["sha256"])
    missing = sorted(old.keys() - new.keys())
    added = sorted(new.keys() - old.keys())
    added_in_known = [p for p in added if new[p]["project"] in known_projects]
    return {"modified": modified, "missing": missing, "added_in_known_projects": added_in_known,
            "added_new_projects": [p for p in added if p not in added_in_known],
            "ok": not (modified or missing or added_in_known)}


def project_inventory(files: list[dict]) -> dict:
    """按项目汇总：直接文件与压缩包成员各有多少视频、表格。"""
    inv: dict[str, dict] = {}
    for r in files:
        p = inv.setdefault(r["project"], {"n_files": 0, "bytes": 0, "kinds": {},
                                          "kinds_in_archives": {}, "tables": {}})
        p["n_files"] += 1
        p["bytes"] += r["bytes"]
        p["kinds"][r["kind"]] = p["kinds"].get(r["kind"], 0) + 1
        for m in r.get("archive", {}).get("members", []):
            p["kinds_in_archives"][m["kind"]] = p["kinds_in_archives"].get(m["kind"], 0) + 1
        if "table" in r:
            t = r["table"]
            p["tables"][r["path"]] = (
                t.get("columns") or {k: v["columns"] for k, v in t.get("sheets", {}).items()}
                or t.get("summary_error"))
    return inv


def presence_checks(inv: dict, required: list[str]) -> dict:
    """S0a 的齐全性检查：每个必需项目至少有 1 个视频和 1 张表（直接或在压缩包里）。

    这只是必要条件；“逐试次数据齐全、能复现原文均值”在 S0b 检验。
    """
    out = {}
    for pid in required:
        p = inv.get(pid)
        if p is None:
            out[pid] = {"downloaded": False, "has_video": False, "has_table": False}
            continue
        n_vid = p["kinds"].get("video", 0) + p["kinds_in_archives"].get("video", 0)
        n_tab = p["kinds"].get("table", 0) + p["kinds_in_archives"].get("table", 0)
        out[pid] = {"downloaded": True, "n_video": n_vid, "n_table": n_tab,
                    "has_video": n_vid > 0, "has_table": n_tab > 0}
    return out
