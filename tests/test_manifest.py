"""tcomp.data.manifest 与 scripts/s0_audit.py 的单元测试（合成数据，不需要集群）。"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from tcomp.data import manifest as mf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import s0_audit  # noqa: E402


def make_video(path: Path, n_frames: int = 30, fps: int = 10) -> None:
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    with av.open(str(path), "w") as c:
        s = c.add_stream("mpeg4", rate=fps)
        s.width, s.height, s.pix_fmt = 64, 48, "yuv420p"
        for i in range(n_frames):
            img = np.full((48, 64, 3), (i * 8) % 255, dtype=np.uint8)
            for p in s.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                c.mux(p)
        for p in s.encode():
            c.mux(p)


@pytest.fixture
def raw(tmp_path):
    r = tmp_path / "raw"
    (r / "projA" / "videos").mkdir(parents=True)
    (r / "projA" / "trials.csv").write_text("subj,video,dur,replay\n1,v1,3,3.5\n2,v1,3,3.9\n")
    make_video(r / "projA" / "videos" / "v1.mp4")
    (r / "projA" / ".complete").touch()
    (r / "projB").mkdir()
    with zipfile.ZipFile(r / "projB" / "stim.zip", "w") as z:
        z.writestr("stim/a.mp4", b"fake")
        z.writestr("data/trials.xlsx", b"fake")
        z.writestr("__MACOSX/stim/._a.mp4", b"junk")
    (r / "projB" / "readme.pdf").write_bytes(b"%PDF")
    return r


def test_classify():
    assert mf.classify("a/B.MP4") == "video"
    assert mf.classify("x.csv") == "table"
    assert mf.classify("analysis.R") == "script"
    assert mf.classify("x.zip") == "archive"
    assert mf.classify("x.weird") == "other"


def test_sha256_deterministic_and_sensitive(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"abc")
    # sha256("abc") 的标准测试向量（FIPS 180-2）
    assert mf.sha256(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert mf.sha256(f) == mf.sha256(f)
    f.write_bytes(b"abd")
    assert mf.sha256(f) != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_probe_video(tmp_path):
    v = tmp_path / "v.mp4"
    make_video(v, n_frames=30, fps=10)
    meta = mf.probe_video(v)
    assert "probe_error" not in meta
    assert meta["width"] == 64 and meta["height"] == 48
    assert meta["fps"] == pytest.approx(10)
    assert meta["duration_s"] == pytest.approx(3.0, abs=0.15)


def test_probe_video_bad_file_records_error(tmp_path):
    v = tmp_path / "bad.mp4"
    v.write_bytes(b"not a video")
    assert "probe_error" in mf.probe_video(v)


def test_build_manifest_and_inventory(raw):
    files = mf.build_manifest(raw)
    paths = {r["path"] for r in files}
    assert paths == {"projA/trials.csv", "projA/videos/v1.mp4", "projB/stim.zip", "projB/readme.pdf"}
    csv = next(r for r in files if r["path"] == "projA/trials.csv")
    assert csv["table"]["columns"] == ["subj", "video", "dur", "replay"]
    assert csv["table"]["n_rows"] == 2
    z = next(r for r in files if r["kind"] == "archive")
    assert {m["name"] for m in z["archive"]["members"]} == {"stim/a.mp4", "data/trials.xlsx"}

    inv = mf.project_inventory(files)
    checks = mf.presence_checks(inv, ["projA", "projB", "projC"])
    assert checks["projA"]["has_video"] and checks["projA"]["has_table"]
    assert checks["projB"]["has_video"] and checks["projB"]["has_table"]  # 来自压缩包成员
    assert checks["projC"] == {"downloaded": False, "has_video": False, "has_table": False}


def test_build_manifest_does_not_modify_raw(raw):
    before = {p: p.read_bytes() for p in raw.rglob("*") if p.is_file()}
    mf.build_manifest(raw)
    after = {p: p.read_bytes() for p in raw.rglob("*") if p.is_file()}
    assert before == after


def test_verify_manifest(raw):
    old = mf.build_manifest(raw)
    assert mf.verify_manifest(old, mf.build_manifest(raw))["ok"]

    (raw / "projA" / "trials.csv").write_text("changed\n")
    (raw / "projB" / "readme.pdf").unlink()
    (raw / "projA" / "extra.csv").write_text("a\n1\n")
    (raw / "projNew").mkdir()
    (raw / "projNew" / "t.csv").write_text("a\n1\n")
    v = mf.verify_manifest(old, mf.build_manifest(raw))
    assert not v["ok"]
    assert v["modified"] == ["projA/trials.csv"]
    assert v["missing"] == ["projB/readme.pdf"]
    assert v["added_in_known_projects"] == ["projA/extra.csv"]
    assert v["added_new_projects"] == ["projNew/t.csv"]


def _site(tmp_path, raw) -> Path:
    cfg = tmp_path / "site.yaml"
    cfg.write_text(
        f"paths: {{raw: {raw}}}\nseeds: [42]\n"
        "osf_projects:\n  projA: {role: dev}\n  projB: {role: test_zero_shot}\n  projZ: {role: optional}\n")
    return cfg


def test_s0_audit_end_to_end(raw, tmp_path):
    cfg, out, man = _site(tmp_path, raw), tmp_path / "out", tmp_path / "manifest.json"
    args = ["--config", str(cfg), "--out-dir", str(out), "--manifest", str(man), "--run-id", "t"]
    assert s0_audit.main(args) == 0
    checks = json.loads((out / "checks.json").read_text())
    assert checks["required_projects"] == ["projA", "projB"]
    assert checks["s0a_pass"] is True
    assert checks["raw_unchanged"] is None  # 第一次运行没有旧清单
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["stage"] == "S0" and meta["run_id"] == "t"

    # 第二次运行：raw 未变 → 通过
    assert s0_audit.main(args) == 0
    assert json.loads((out / "checks.json").read_text())["raw_unchanged"]["ok"] is True

    # raw 被改动 → 返回 1，且不覆盖已登记的清单
    old_manifest = man.read_text()
    (raw / "projA" / "trials.csv").write_text("tampered\n")
    assert s0_audit.main(args) == 1
    assert man.read_text() == old_manifest
    assert json.loads((out / "checks.json").read_text())["s0a_pass"] is False
