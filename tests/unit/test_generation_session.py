"""생성(Phase 4) 상태 기계와 실패 분류(Qt 무관). 합성 데이터만 사용한다.
합격 기준 주의: 출력 폴더에 이전 파일이 있을 수 있으므로 '폴더가 비어 있다'가 아니라 '이번 작업이 새 최종 파일·임시 파일을 남기지 않았고 기존 파일은 그대로다'를 본다."""
import dataclasses
import hashlib
import logging
import os
import tempfile
from pathlib import Path

import pytest

from scholarship_payment.app import convert as conv
from scholarship_payment.app import workflow as wf
from scholarship_payment.app.convert import prepare
from scholarship_payment.io import safe_save
from scholarship_payment.ui import generation as gn
from scholarship_payment.ui import preview as pv
from scholarship_payment.ui.runner import InlineRunner, ManualRunner
from prep_helpers import TEMPLATE, flip_byte_keep_size_and_mtime
from xlsx_dump import diff, dump

BASE = "2099.10.07"
NAME = "지급명단_DAECHUNG_9999_09.xlsx"
CARRY = ((2, 8 * 60, "9999년08월"), (3, 90, "9999년08월"))


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def tpl(tmp_path):
    p = tmp_path / "tpl.xlsx"
    p.write_bytes(TEMPLATE.read_bytes())
    return p


def prep(src, tpl, **kw):
    return prepare("daechung", src, tpl, base_date=BASE, **kw)


def listing(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(folder).iterdir()}


def session(runner=None):
    return gn.GenerationSession(runner or InlineRunner())


# ---------- 성공 · 경고 포함 성공 ----------
def test_success_reports_actual_values_and_consumes_the_prepared(make_input, tpl, out):
    p = prep(make_input(n=4), tpl)
    s = session()
    assert s.start(p, out) and s.state == gn.SUCCESS
    o = s.outcome
    assert o.status == "ok" and o.count == 4 and o.total_amount == p.total_amount and Path(o.output_path).name == NAME and Path(o.output_path).parent == out
    assert o.size_bytes == os.stat(o.output_path).st_size > 0 and o.finished_at and o.template_name == tpl.name and not o.name_changed
    assert s.start(p, out) is False and len(list(out.iterdir())) == 1          # 같은 Prepared 로 다시 만들 수 없다


def test_success_with_warnings_is_a_separate_state(make_input, tpl, out, monkeypatch):
    p = prep(make_input(n=3), tpl)
    p2 = dataclasses.replace(p, warnings=(conv.Issue("SPLIT_AMOUNT_MISMATCH", "grant_interest", 4),))
    s = session()
    s.start(p2, out)
    assert s.state == gn.SUCCESS_WITH_WARNINGS and [g.code for g in s.outcome.warnings] == ["SPLIT_AMOUNT_MISMATCH"]


def test_notes_alone_do_not_make_it_a_warning_success(make_input, tpl, out):
    s = session()
    s.start(prep(make_input(n=4, extra=CARRY), tpl), out)
    assert s.state == gn.SUCCESS and {g.code for g in s.outcome.notes} >= {"STUDENT_MERGED_ROWS"} and s.outcome.warnings == ()


def test_generated_file_equals_the_golden_output(make_input, tpl, out):
    from test_golden_equivalence import load_golden
    s = session()
    s.start(prep(make_input(n=5), tpl), out)
    got = dump(s.outcome.output_path)
    golden = load_golden("daechung_plain")
    assert diff({**got, **{k: golden[k] for k in ("filename", "count", "warnings", "notes")}}, golden) == []


def test_same_name_in_folder_gets_a_safe_new_name_and_existing_files_are_untouched(make_input, tpl, out):
    (out / NAME).write_bytes(b"existing result")
    (out / ".~old_run.xlsx").write_bytes(b"leftover from a previous run")
    before = listing(out)
    s = session()
    s.start(prep(make_input(n=3), tpl), out)
    after = listing(out)
    assert s.state == gn.SUCCESS and Path(s.outcome.output_path).name == NAME.replace(".xlsx", "_2.xlsx") and s.outcome.name_changed
    assert {k: v for k, v in after.items() if k in before} == before                      # 기존 파일(임시 잔여물 포함)은 그대로
    assert set(after) - set(before) == {Path(s.outcome.output_path).name}               # 새 파일은 최종 파일 1개뿐
    assert s.outcome.leftover_temp == 1                                                 # 이전 실행의 잔여 임시 파일은 알리기만 한다


def test_leftover_temp_files_are_never_deleted_on_success_or_failure(make_input, tpl, out):
    (out / ".~old_run.xlsx").write_bytes(b"x")
    s = session()
    s.start(prep(make_input(n=3), tpl), out)
    s2 = session()
    s2.start(prep(make_input(n=3), tpl), out / "missing")
    assert (out / ".~old_run.xlsx").read_bytes() == b"x"


# ---------- 파일 변경 · 읽기 불가: 만들지 않고 무효화 ----------
@pytest.mark.parametrize("which", ["source", "template"])
def test_changed_input_blocks_generation_and_requests_review(which, make_input, tpl, out):
    src = make_input(n=3)
    p = prep(src, tpl)
    before = listing(out)
    flip_byte_keep_size_and_mtime({"source": src, "template": tpl}[which])
    s = session()
    s.start(p, out)
    assert s.state == gn.INVALIDATED and s.outcome.status == "changed" and s.outcome.changed_codes == {which: "INPUT_FILE_CHANGED"}
    assert listing(out) == before and s.start(p, out) is False and s.retry() is False       # 자동 재생성·재시도 없음


def test_unreadable_input_is_invalidated_with_its_own_code(make_input, tpl, out, monkeypatch):
    src = make_input(n=3)
    p = prep(src, tpl)
    real = conv.fingerprint_file
    monkeypatch.setattr(conv, "fingerprint_file", lambda path: (_ for _ in ()).throw(PermissionError("denied")) if os.fspath(path) == os.fspath(src) else real(path))
    s = session()
    s.start(p, out)
    assert s.state == gn.INVALIDATED and s.outcome.changed_codes == {"source": "INPUT_FILE_UNREADABLE"} and list(out.iterdir()) == []


# ---------- 템플릿 레이아웃 오류 ----------
def test_template_layout_error_is_a_failure_kind_template_and_creates_nothing(make_input, tmp_path, out):
    from openpyxl import load_workbook
    bad = tmp_path / "bad.xlsx"
    wb = load_workbook(TEMPLATE)
    del wb["WINS"]
    wb.save(bad)
    p = prep(make_input(n=3), bad)                                                     # prepare 는 레이아웃을 보장하지 않는다
    s = session()
    s.start(p, out)
    assert s.state == gn.FAILED and s.failure_kind == gn.KIND_TEMPLATE and s.outcome.errors[0].code == "TEMPLATE_LAYOUT"
    assert list(out.iterdir()) == [] and not s.can_retry                                # 같은 Prepared 재시도 불가(템플릿을 고쳐 다시 확인해야 함)


# ---------- 저장 폴더 오류: 같은 Prepared 로 재시도 ----------
def test_missing_folder_is_a_folder_failure_and_retry_reuses_the_prepared_after_recheck(make_input, tpl, tmp_path, out):
    p = prep(make_input(n=3), tpl)
    missing = tmp_path / "gone"
    s = session()
    s.start(p, missing)
    assert s.state == gn.FAILED and s.failure_kind == gn.KIND_FOLDER and s.outcome.errors[0].code == "OUTPUT_DIR_MISSING" and s.can_retry and not missing.exists()
    assert s.retry(out) and s.state == gn.SUCCESS and s.outcome.count == 3 and Path(s.outcome.output_path).parent == out


def test_retry_rechecks_fingerprints_so_a_changed_file_invalidates_instead_of_generating(make_input, tpl, tmp_path, out):
    src = make_input(n=3)
    p = prep(src, tpl)
    s = session()
    s.start(p, tmp_path / "gone")
    flip_byte_keep_size_and_mtime(src)                                                  # 실패 후 재시도 전에 원본이 바뀜
    before = listing(out)
    s.retry(out)
    assert s.state == gn.INVALIDATED and listing(out) == before


def test_changing_the_folder_is_not_a_preview_validation(make_input, tpl, tmp_path, out):
    s = session()
    s.start(prep(make_input(n=3), tpl), tmp_path / "gone")
    assert s.set_out_dir(out).ok and s.out_dir == str(out) and s.state == gn.FAILED     # 폴더만 바꿨을 뿐 상태는 그대로(성공 처리 아님)
    assert not s.set_out_dir(tmp_path / "also_gone").ok and s.out_dir == str(out)       # 없는 폴더는 받지 않는다


@pytest.mark.parametrize("how,code", [("permission", "OUTPUT_PERMISSION"), ("io", "OUTPUT_IO"), ("exhausted", "OUTPUT_NAME_EXHAUSTED")])
def test_folder_error_kinds_are_distinguished_and_leave_no_new_files(how, code, make_input, tpl, out, monkeypatch):
    p = prep(make_input(n=3), tpl)
    (out / "existing.xlsx").write_bytes(b"keep me")
    before = listing(out)
    if how == "permission":
        monkeypatch.setattr(tempfile, "mkstemp", lambda *a, **k: (_ for _ in ()).throw(PermissionError("denied")))
    elif how == "io":
        from openpyxl import Workbook
        monkeypatch.setattr(Workbook, "save", lambda self, *a, **k: (_ for _ in ()).throw(OSError(5, "io error")))
    else:
        monkeypatch.setattr(safe_save, "_publish", lambda tmp, final: False)
    s = session()
    s.start(p, out)
    assert s.state == gn.FAILED and s.failure_kind == gn.KIND_FOLDER and s.outcome.errors[0].code == code and s.can_retry
    assert listing(out) == before                                                         # 새 최종 파일·임시 파일 없음, 기존 파일 그대로


# ---------- 출력 재검증 실패: 저장 폴더 오류와 구분, 자동 재시도 불허 ----------
def test_output_verification_failure_is_not_a_folder_error_and_publishes_nothing(make_input, tpl, out, monkeypatch):
    (out / NAME).write_bytes(b"existing result")
    before = listing(out)
    p = prep(make_input(n=3), tpl)
    monkeypatch.setattr(conv, "verify_output", lambda *a, **k: (_ for _ in ()).throw(conv.ValidationFailed([conv.ValidationError("OUTPUT_TOTAL_MISMATCH", "amount", 9)])))
    s = session()
    s.start(p, out)
    assert s.state == gn.FAILED and s.failure_kind == gn.KIND_VERIFY and s.outcome.errors[0].code == "OUTPUT_TOTAL_MISMATCH" and not s.can_retry
    assert listing(out) == before and s.retry() is False and s.start(p, out) is False


def test_unexpected_exception_is_contained_without_leaking_text(make_input, tpl, out, monkeypatch, caplog):
    monkeypatch.setattr(wf, "finish", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"boom at {out}/학생홍길동.xlsx")))
    s = session()
    with caplog.at_level(logging.DEBUG):
        s.start(prep(make_input(n=3), tpl), out)
    assert s.state == gn.FAILED and s.failure_kind == gn.KIND_UNEXPECTED and not s.can_retry and caplog.text == ""
    assert "홍길동" not in repr(s.outcome) + repr(vars(s)) and str(out) not in repr(s.outcome)


# ---------- 중복 실행 · 잠금 · 오래된/닫힌 콜백 ----------
def test_duplicate_start_while_generating_submits_one_job_and_creates_one_file(make_input, tpl, out):
    r = ManualRunner()
    s = session(r)
    p = prep(make_input(n=3), tpl)
    assert s.start(p, out) and s.busy and s.state == gn.GENERATING
    assert s.start(p, out) is False and s.retry() is False and len(r.pending) == 1
    r.run_all()
    assert s.state == gn.SUCCESS and len(list(out.iterdir())) == 1


def test_reset_is_the_only_way_to_start_again_after_success(make_input, tpl, out):
    s = session()
    s.start(prep(make_input(n=3), tpl), out)
    s.reset()
    assert s.state == gn.IDLE and s.outcome is None
    assert s.start(prep(make_input(n=3), tpl), out) and s.state == gn.SUCCESS and len(list(out.iterdir())) == 2


def test_reset_while_generating_is_refused(make_input, tpl, out):
    r = ManualRunner()
    s = session(r)
    s.start(prep(make_input(n=3), tpl), out)
    assert s.reset() is False and s.busy


def test_late_result_after_close_is_ignored_and_listeners_are_not_called(make_input, tpl, out):
    r = ManualRunner()
    s = session(r)
    calls = []
    s.on_change(lambda: calls.append(s.state))
    s.start(prep(make_input(n=3), tpl), out)
    n = len(calls)
    s.close()                                                                            # 창이 닫히며 연결이 끊김
    r.run_all()
    assert len(calls) == n and s.state == gn.GENERATING and s.outcome is None            # 닫힌 뒤 늦게 온 결과는 반영하지 않는다


def test_state_is_set_before_listeners_so_a_ui_error_cannot_misclassify_a_created_file(make_input, tpl, out):
    r = ManualRunner()
    s = session(r)
    s.on_change(lambda: (_ for _ in ()).throw(RuntimeError("ui bug")) if s.state == gn.SUCCESS else None)
    s.start(prep(make_input(n=3), tpl), out)
    with pytest.raises(RuntimeError):
        r.run_all()
    assert s.state == gn.SUCCESS and s.outcome.status == "ok" and Path(s.outcome.output_path).is_file()


def test_size_stat_failure_does_not_turn_success_into_failure(make_input, tpl, out, monkeypatch):
    real = os.stat
    state = {"after": False}
    real_finish = conv.finish

    def finish_then_break_stat(prepared, folder):
        r = real_finish(prepared, folder)
        state["after"] = True
        return r

    monkeypatch.setattr(wf, "finish", finish_then_break_stat)
    monkeypatch.setattr(wf.os, "stat", lambda p, *a, **k: (_ for _ in ()).throw(PermissionError("denied")) if state["after"] else real(p, *a, **k))
    s = session()
    s.start(prep(make_input(n=3), tpl), out)
    assert s.state == gn.SUCCESS and s.outcome.size_bytes is None and Path(s.outcome.output_path).name == NAME


# ---------- 미리보기 세션 연계 ----------
def test_preview_session_can_be_invalidated_and_consumed(make_input, tpl, tmp_path):
    from prep_helpers import make_policy
    from scholarship_payment.ui.state import Step1Selection
    pol = make_policy(tmp_path)
    s = pv.PreviewSession(InlineRunner())
    s.start(Step1Selection("daechung", BASE, str(make_input(n=3)), "/x", str(tpl), str(pol)))
    assert s.state == pv.READY
    prepared = s.prepared
    s.invalidate("generation_failed")
    assert s.state == pv.INVALIDATED and s.prepared is None and s.invalid_reason == "generation_failed"
    s.start(Step1Selection("daechung", BASE, str(make_input(n=3)), "/x", str(tpl), str(pol)))
    assert s.state == pv.READY
    s.consume()
    assert s.state == pv.CONSUMED and s.prepared is None and s.summary is None and prepared is not None


def test_generation_result_repr_has_no_paths_or_student_values(make_input, tpl, out):
    s = session()
    p = prep(make_input(n=3), tpl)
    s.start(p, out)
    row = p._validated.rows[0].row
    attrs = {k: v for k, v in vars(s).items() if k not in ("out_dir", "_listeners")}      # out_dir 은 재시도에 필요한 사용자 선택값(repr 로 노출되지 않음)
    text = repr(s.outcome) + repr(s) + repr(attrs)
    for secret in (str(out), str(tpl), row.name, row.student_id, row.account_no):
        assert secret not in text


def test_after_success_even_a_different_prepared_needs_an_explicit_reset(make_input, tpl, out):
    s = session()
    s.start(prep(make_input(n=3), tpl), out)
    other = prep(make_input(n=4), tpl)
    assert s.start(other, out) is False and len(list(out.iterdir())) == 1          # '새 변환'(reset) 없이는 어떤 확인 결과로도 다시 만들 수 없다
    assert s.reset() and s.start(other, out) and len(list(out.iterdir())) == 2


# ---------- 경계조건: 워커에서 예상하지 못한 예외가 나도 GENERATING 이 풀린다 ----------
@pytest.mark.parametrize("how", ["raises", "wrong_type", "none"])
def test_unexpected_failure_inside_the_worker_never_leaves_generating_stuck(how, make_input, tpl, out, caplog):
    """finish_fn 자체가 예외를 내거나(run_finish 바깥), 러너가 예외를 다른 객체(FieldState)로 바꿔 돌려주거나, None 이 와도 FAILED(unexpected)로 정리된다."""
    from scholarship_payment.ui import validators as v

    def finish_fn(prepared, folder, now=None):
        if how == "raises":
            raise RuntimeError(f"boom {folder}/학생홍길동.xlsx")
        return v.FieldState(v.ERROR, "CHECK_FAILED") if how == "wrong_type" else None

    s = gn.GenerationSession(InlineRunner(), finish_fn=finish_fn)
    before = listing(out)
    with caplog.at_level(logging.DEBUG):
        assert s.start(prep(make_input(n=3), tpl), out)
    assert s.state == gn.FAILED and s.failure_kind == gn.KIND_UNEXPECTED and not s.busy and not s.can_retry and caplog.text == ""
    assert "홍길동" not in repr(s.outcome) + repr(s) and str(out) not in repr(s.outcome) and listing(out) == before
    assert s.reset() and s.state == gn.IDLE                                        # 정상적으로 다시 시작할 수 있는 상태로 돌아온다


def test_runner_returning_a_foreign_object_directly_is_contained(make_input, tpl, out):
    r = ManualRunner()
    s = session(r)
    s.start(prep(make_input(n=3), tpl), out)
    r.pending[0][1](object())                                                      # 러너가 엉뚱한 객체를 콜백에 넘김
    assert s.state == gn.FAILED and s.failure_kind == gn.KIND_UNEXPECTED and not s.busy
