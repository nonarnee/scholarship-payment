"""시트별 저장(분리 모드)의 흐름 계층: run_finish 분류·크기·이름, GenerationSession 의 모드 유지, 임시 폴더 안내. 합성 데이터만 사용한다."""
from pathlib import Path

import pytest

from scholarship_payment.app import workflow as wf
from scholarship_payment.app.convert import prepare
from scholarship_payment.ui import generation as gn
from scholarship_payment.ui.runner import InlineRunner
from prep_helpers import TEMPLATE

BASE = "2099.10.07"


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def prepared(make_input):
    return prepare("daechung", make_input(n=4), TEMPLATE, base_date=BASE)


def test_run_finish_split_reports_folder_and_three_files(prepared, out):
    o = wf.run_finish(prepared, out, split=True)
    stem = Path(prepared.filename).stem
    assert o.status == "ok" and o.split and Path(o.output_path) == out / stem and [Path(p).name for p in o.output_paths] == [f"{stem}_명단.xlsx", f"{stem}_WINS.xlsx", f"{stem}_WRIS.xlsx"]
    assert o.size_bytes == sum(Path(p).stat().st_size for p in o.output_paths) and o.requested_name == stem and not o.name_changed
    assert o.count == 4 and o.total_amount == prepared.total_amount


def test_run_finish_default_is_unchanged(prepared, out):
    o = wf.run_finish(prepared, out)
    assert o.status == "ok" and not o.split and o.output_paths == () and Path(o.output_path).name == prepared.filename and o.requested_name == prepared.filename


def test_split_name_collision_is_reported_as_a_changed_name(prepared, out):
    wf.run_finish(prepared, out, split=True)
    o = wf.run_finish(prepared, out, split=True)
    assert o.name_changed and Path(o.output_path).name.endswith("_2")


def test_split_folder_errors_are_classified_like_single_file(prepared, tmp_path):
    o = wf.run_finish(prepared, tmp_path / "없음", split=True)
    assert o.status == "failed" and o.kind == wf.KIND_FOLDER and {g.code for g in o.errors} == {"OUTPUT_DIR_MISSING"}


def test_leftover_run_folders_are_counted_and_never_deleted(prepared, out):
    (out / ".~run-abc123").mkdir()
    (out / ".~old.xlsx").write_bytes(b"x")
    o = wf.run_finish(prepared, out, split=True)
    assert o.leftover_temp == 2 and (out / ".~run-abc123").is_dir() and (out / ".~old.xlsx").exists()


def test_repr_has_no_paths(prepared, out):
    o = wf.run_finish(prepared, out, split=True)
    assert str(out) not in repr(o) and "WINS" not in repr(o)


# ---- GenerationSession
def test_session_default_calls_finish_without_split(prepared, out):
    calls = []

    def fake(p, folder, now=None, **kw):
        calls.append(kw)
        return wf.run_finish(p, folder, now, **kw)
    s = gn.GenerationSession(InlineRunner(), finish_fn=fake)
    s.start(prepared, out)
    assert calls == [{}] and s.state == gn.SUCCESS and not s.split


def test_session_split_passes_mode_and_keeps_it_for_folder_retry(prepared, tmp_path, out):
    calls = []

    def fake(p, folder, now=None, **kw):
        calls.append(kw)
        return wf.run_finish(p, folder, now, **kw)
    s = gn.GenerationSession(InlineRunner(), finish_fn=fake)
    s.start(prepared, tmp_path / "없음", split=True)
    assert s.state == gn.FAILED and s.can_retry and s.split
    assert s.set_out_dir(out).ok and s.retry()
    assert calls == [{"split": True}, {"split": True}] and s.state == gn.SUCCESS and s.outcome.split
    assert s.reset() and not s.split
