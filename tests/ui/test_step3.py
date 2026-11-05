"""Step 3 생성·결과 화면: 전용 워커, 중복 실행·이동·창 닫기 차단, 성공/경고 성공/실패 유형별 화면, 파일 변경 재검토, 폴더 변경 재시도, 개인정보.
합격 기준: 출력 폴더에 이전 파일이 있을 수 있으므로 '폴더가 비어 있다'가 아니라 '기존 파일은 그대로이고 이번 작업이 새 최종 파일·임시 파일을 남기지 않았다'를 본다."""
import hashlib
import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from scholarship_payment.app import convert as conv  # noqa: E402
from scholarship_payment.app import workflow as wf  # noqa: E402
from scholarship_payment.config.user_settings import UserSettings  # noqa: E402
from scholarship_payment.ui import generation as gn  # noqa: E402
from scholarship_payment.ui import preview as pv  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402
from scholarship_payment.ui.navigation import Step  # noqa: E402
from scholarship_payment.ui.qt_runner import QtRunner  # noqa: E402
from scholarship_payment.ui.runner import ManualRunner  # noqa: E402

from prep_helpers import PW, TEMPLATE, encrypt, flip_byte_keep_size_and_mtime  # noqa: E402
from xlsx_dump import diff, dump  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
NAME = "지급명단_DAECHUNG_9999_09.xlsx"


def texts(w):
    return " ".join(x.text() for x in w.findChildren(QLabel))


def listing(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(folder).iterdir()}


def make_win(make_context, settings, gen_runner=None, runner=None, actions=None):
    ctx = make_context(settings=settings, runner=runner, generation_runner=gen_runner, actions=actions)
    w = MainWindow(context=ctx)
    w.show()
    return w, ctx


def to_step2(w, src):
    w.step1.model.set_source(src)
    if isinstance(w.context.runner, ManualRunner):
        w.context.runner.run_all()
    w.next_button.click()
    if isinstance(w.context.runner, ManualRunner):
        w.context.runner.run_all()
    assert w.navigator.current == Step.REVIEW and w.step2.session.state == pv.READY
    return w


def generate(w):
    assert w.next_button.isEnabled()
    w.next_button.click()


@pytest.fixture
def inline(qapp, make_context, ready_settings):
    w, ctx = make_win(make_context, ready_settings)
    yield w
    w.close()


@pytest.fixture
def manual(qapp, make_context, ready_settings):
    r = ManualRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=r)
    yield w, r
    w.generation.close()
    w.close()


# ---------- 시작: 전용 워커 · 중복 실행 ----------
def test_generate_button_is_enabled_only_when_preview_is_ready_and_labelled(inline, make_input):
    assert not inline.next_button.isEnabled()
    to_step2(inline, make_input(n=3))
    assert inline.next_button.isEnabled() and inline.next_button.text() == "지급명단 생성" and inline.next_button.toolTip() == ""


def test_generation_runs_on_its_own_worker_and_shows_indeterminate_progress(manual, make_input, out_dir):
    w, r = manual
    to_step2(w, make_input(n=3))
    before = listing(out_dir)
    generate(w)
    assert w.context.gen_runner is r and w.context.gen_runner is not w.context.runner
    s3 = w.step3
    assert w.navigator.current == Step.RESULT and w.generation.state == gn.GENERATING and len(r.pending) == 1 and listing(out_dir) == before
    assert not s3.progress_box.isHidden() and (s3.progress.minimum(), s3.progress.maximum()) == (0, 0) and s3.result_box.isHidden()
    for banned in ("%", "초", "남은", "예상", "소요"):
        assert banned not in s3.progress_label.text()


def test_double_click_creates_exactly_one_file_and_calls_finish_once(manual, make_input, out_dir, monkeypatch):
    w, r = manual
    calls = []
    real = wf.finish
    monkeypatch.setattr(wf, "finish", lambda p, d: (calls.append(1), real(p, d))[1])
    to_step2(w, make_input(n=3))
    w.next_button.click()
    w.next_button.click()                                                    # 두 번째 클릭(이미 Step 3)
    w.step3.enter(w.step2._selection)
    w.generation.start(w.step2.session.prepared, out_dir)
    assert len(r.pending) == 1
    r.run_all()
    assert len(calls) == 1 and [p.name for p in out_dir.iterdir()] == [NAME] and w.generation.state == gn.SUCCESS


def test_real_worker_thread_keeps_gui_responsive_and_delivers_on_main_thread(qapp, make_context, ready_settings, make_input, out_dir, monkeypatch):
    gate, started, seen = threading.Event(), threading.Event(), {}
    real = wf.finish

    def slow(p, d):
        seen["worker"] = threading.current_thread()
        started.set()
        gate.wait(5)
        return real(p, d)

    monkeypatch.setattr(wf, "finish", slow)
    runner = QtRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=runner)
    callback_threads = []
    w.generation.on_change(lambda: callback_threads.append(threading.current_thread()))      # 완료 콜백(상태 변경 알림)이 실행되는 스레드
    to_step2(w, make_input(n=3))
    generate(w)
    assert started.wait(5)
    t0 = time.time()
    for _ in range(50):
        QApplication.processEvents()
    assert time.time() - t0 < 2 and w.generation.state == gn.GENERATING
    gate.set()
    deadline = time.time() + 5
    while w.generation.busy and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert w.generation.state == gn.SUCCESS and seen["worker"] is not threading.main_thread() and [p.name for p in out_dir.iterdir()] == [NAME]
    assert callback_threads and all(t is threading.main_thread() for t in callback_threads)              # 완료 콜백은 모두 메인(GUI) 스레드에서 실행됐다
    w.close()


# ---------- 생성 중 이동·창 닫기 차단 ----------
def test_navigation_is_blocked_while_generating(manual, make_input):
    w, r = manual
    to_step2(w, make_input(n=3))
    generate(w)
    assert w.navigator.locked and not w.back_button.isEnabled() and not w.next_button.isVisible()
    assert w.navigator.go(Step.REVIEW) is False and w.navigator.go(Step.FILE) is False and w.navigator.back() is False
    w.back_button.click()
    assert w.navigator.current == Step.RESULT and w.generation.state == gn.GENERATING


def test_closing_is_blocked_while_generating_without_touching_the_worker(qapp, make_context, ready_settings, make_input, out_dir, monkeypatch):
    gate, started = threading.Event(), threading.Event()
    real = wf.finish
    monkeypatch.setattr(wf, "finish", lambda p, d: (started.set(), gate.wait(5), real(p, d))[2])
    runner = QtRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=runner)
    to_step2(w, make_input(n=3))
    generate(w)
    assert started.wait(5)
    ev = QCloseEvent()
    w.closeEvent(ev)
    assert not ev.isAccepted() and w.isVisible() and runner.pending() == 1 and w.generation.busy         # 닫기가 워커·세션을 건드리지 않는다
    assert "닫을 수 없" in w.statusBar().currentMessage() and "닫을 수 없" in w.step3.close_notice.text() and not w.step3.close_notice.isHidden()
    assert w.close() is False and w.isVisible()                                                          # 실제 close() 도 거부된다
    gate.set()
    deadline = time.time() + 5
    while w.generation.busy and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert w.generation.state == gn.SUCCESS and [p.name for p in out_dir.iterdir()] == [NAME]            # 작업은 끝까지 정상 완료
    ev2 = QCloseEvent()
    w.closeEvent(ev2)
    assert ev2.isAccepted()                                                                              # 끝난 뒤에는 닫을 수 있다


def test_window_can_be_closed_after_failure_and_after_success(qapp, make_context, ready_settings, make_input, tmp_path):
    for broken in (False, True):
        w, ctx = make_win(make_context, ready_settings)
        to_step2(w, make_input(n=3))
        if broken:
            import shutil
            shutil.rmtree(tmp_path / "out")
        generate(w)
        assert (w.generation.state == gn.FAILED) == broken
        ev = QCloseEvent()
        w.closeEvent(ev)
        assert ev.isAccepted()
        (tmp_path / "out").mkdir(exist_ok=True)


def test_late_result_after_close_does_not_touch_destroyed_widgets(manual, make_input):
    w, r = manual
    to_step2(w, make_input(n=3))
    generate(w)
    w.generation.close()                                                     # 닫힘 처리(창이 사라진 상황)
    w.step3.deleteLater()
    QApplication.processEvents()
    r.run_all()                                                              # 늦게 도착한 결과: 예외 없이 무시
    assert w.generation.outcome is None


# ---------- 성공 화면: 실제 값만 ----------
def test_success_view_shows_only_measured_values(inline, make_input, out_dir):
    to_step2(inline, make_input(n=4))
    prepared = inline.step2.session.prepared
    generate(inline)
    s3 = inline.step3
    out = out_dir / NAME
    assert inline.generation.state == gn.SUCCESS and out.is_file()
    assert s3.file_name_value.text() == NAME and s3.folder_value.full_text() == str(out_dir)
    assert s3.count_value.text() == "4명" and s3.total_value.text() == f"{prepared.total_amount:,}원" and s3.time_value.text() == "2099-10-07 12:34:56"
    assert s3.size_value.text().split()[0].replace(".", "").isdigit() and s3.template_value.text() == Path(inline.model.paths["template"]).name
    assert "출력 재검증 통과" in s3.verify_label.text() and s3.result_badge.property("badge") == "verified" and s3.name_notice.isHidden()
    assert s3.failure_box.isHidden() and not s3.result_box.isHidden() and not s3.new_button.isHidden()
    t = texts(s3)
    for banned in ("정확도", "점수", "실명", "예상", "소요", "진행률", "SHA", "무결", "100%", "정상 연결"):
        assert banned not in t
    assert not [b for b in s3.findChildren(type(s3.new_button)) if "파일 열기" in b.text()]


def test_success_with_warnings_has_its_own_state_badge_and_rows(qapp, make_context, ready_settings, make_input, monkeypatch):
    import dataclasses
    real = conv.finish
    monkeypatch.setattr(wf, "finish", lambda p, d: dataclasses.replace(real(p, d), warnings=(conv.ValidationError("SPLIT_AMOUNT_MISMATCH", "grant_interest", 4),)))
    w, ctx = make_win(make_context, ready_settings)
    to_step2(w, make_input(n=3))
    generate(w)
    s3 = w.step3
    assert w.generation.state == gn.SUCCESS_WITH_WARNINGS and s3.result_badge.property("badge") == "caution" and "경고" in s3.result_badge.text()
    assert [(r.severity, r.code) for r in s3.issue_rows()] == [("warning", "SPLIT_AMOUNT_MISMATCH")] and "출력 재검증 통과" in s3.verify_label.text()
    w.close()


def test_notes_are_listed_without_changing_the_state_label(inline, make_input):
    to_step2(inline, make_input(n=4, extra=((2, 480, "9999년08월"), (3, 90, "9999년08월"))))
    generate(inline)
    assert inline.generation.state == gn.SUCCESS and {r.severity for r in inline.step3.issue_rows()} == {"note"}


def test_generated_file_from_the_ui_equals_the_golden_output_and_counts_match(qapp, make_context, make_input, out_dir):
    from scholarship_payment.config.policy import SYNTHETIC_POLICY
    from scholarship_payment.config.policy_file import load_policy
    pol = ROOT / "templates" / "synthetic_policy.json"
    assert load_policy(pol) == SYNTHETIC_POLICY                              # 골든이 쓴 정책과 같은 값의 정책 파일
    settings = UserSettings(last_program="daechung").with_paths("daechung", template_path=str(TEMPLATE), policy_path=str(pol), out_dir=str(out_dir))
    inline, _ = make_win(make_context, settings)
    to_step2(inline, make_input(n=5))
    prepared = inline.step2.session.prepared
    generate(inline)
    out = out_dir / NAME
    golden = json.loads((ROOT / "tests" / "fixtures" / "golden" / "daechung_plain.json").read_text(encoding="utf-8"))
    got = dump(out)
    assert diff({**got, **{k: golden[k] for k in ("filename", "count", "warnings", "notes")}}, golden) == []
    from openpyxl import load_workbook
    wris = load_workbook(out)["WRIS"]
    amounts = [wris.cell(r, 5).value for r in range(2, wris.max_row + 1) if wris.cell(r, 5).value is not None]
    assert inline.step3.count_value.text() == f"{len(amounts)}명" and inline.step3.total_value.text() == f"{sum(amounts):,}원" == f"{prepared.total_amount:,}원"
    inline.close()


def test_same_name_in_folder_shows_the_actual_new_name_and_keeps_existing_files(inline, make_input, out_dir):
    (out_dir / NAME).write_bytes(b"existing result")
    before = listing(out_dir)
    to_step2(inline, make_input(n=3))
    generate(inline)
    s3 = inline.step3
    after = listing(out_dir)
    assert s3.file_name_value.text() == NAME.replace(".xlsx", "_2.xlsx") and not s3.name_notice.isHidden() and "그대로" in s3.name_notice.text()
    assert {k: v for k, v in after.items() if k in before} == before and len(set(after) - set(before)) == 1


def test_leftover_temp_files_are_reported_generally_and_never_deleted(inline, make_input, out_dir):
    (out_dir / ".~old_run.xlsx").write_bytes(b"leftover")
    to_step2(inline, make_input(n=3))
    generate(inline)
    s3 = inline.step3
    assert not s3.leftover_notice.isHidden() and "1개" in s3.leftover_notice.text() and "자동으로 지우지 않" in s3.leftover_notice.text()
    assert (out_dir / ".~old_run.xlsx").read_bytes() == b"leftover"
    assert ".~old_run" not in texts(s3)                                                                  # 파일 이름은 보여 주지 않는다(일반 안내)


def test_no_leftover_notice_when_there_are_none(inline, make_input):
    to_step2(inline, make_input(n=3))
    generate(inline)
    assert inline.step3.leftover_notice.isHidden()


# ---------- 성공 이후: 잠금 · 재생성 차단 · 새 변환 ----------
def test_after_success_navigation_stays_locked_and_the_same_prepared_cannot_be_used_again(inline, make_input, out_dir):
    src = make_input(n=3)
    to_step2(inline, src)
    generate(inline)
    assert inline.navigator.locked and not inline.back_button.isEnabled() and inline.navigator.go(Step.REVIEW) is False
    assert inline.step2.session.state == pv.CONSUMED and inline.step2.session.prepared is None
    assert inline.generation.start(inline.step2.session.prepared, out_dir) is False
    inline.step3.enter(inline.step2._selection)
    assert [p.name for p in out_dir.iterdir()] == [NAME]


def test_open_folder_and_copy_path_use_the_injected_actions_and_failure_is_not_a_generation_failure(qapp, make_context, ready_settings, make_input, out_dir):
    from conftest import FakeActions
    actions = FakeActions()
    w, ctx = make_win(make_context, ready_settings, actions=actions)
    to_step2(w, make_input(n=3))
    generate(w)
    s3 = w.step3
    s3.open_folder_button.click()
    s3.copy_path_button.click()
    assert actions.opened == [str(out_dir)] and actions.copied == [str(out_dir / NAME)] and "복사했습니다" in s3.action_status.text()
    actions.open_ok = False
    s3.open_folder_button.click()
    assert "열지 못했습니다" in s3.action_status.text() and w.generation.state == gn.SUCCESS and (out_dir / NAME).is_file()
    actions.copy_ok = False
    s3.copy_path_button.click()
    assert "복사하지 못했습니다" in s3.action_status.text() and w.generation.state == gn.SUCCESS
    w.close()


def test_new_conversion_resets_everything_and_allows_a_second_conversion(inline, make_input, out_dir):
    to_step2(inline, make_input(n=3))
    generate(inline)
    inline.step3.new_button.click()
    assert inline.navigator.current == Step.FILE and not inline.navigator.locked and inline.generation.state == gn.IDLE
    assert inline.step2.session.state == pv.IDLE and inline.step1.model.paths["source"] is None and not inline.next_button.isEnabled()
    to_step2(inline, make_input(n=3))
    generate(inline)
    assert sorted(p.name for p in out_dir.iterdir()) == [NAME, NAME.replace(".xlsx", "_2.xlsx")]


def test_policy_edited_after_preview_blocks_generation_and_creates_nothing(manual, make_input, out_dir, policy_file):
    """정책 JSON 을 수정(저장)한 뒤에는 그 전의 확인 결과(Prepared)로 지급명단을 만들 수 없다."""
    from scholarship_payment.config import policy_edit as pe
    w, r = manual
    to_step2(w, make_input(n=3))
    generate(w)
    before = listing(out_dir)
    sess = pe.open_for_edit(policy_file, "daechung")
    assert pe.save_policy_replace(sess, pe.edited_data(sess, {**{k: sess.data[k] for k in pe.USER_KEYS}, "wins_work_name": "수정뒤"})).changed
    r.run_all()
    p = w.step2
    assert w.navigator.current == Step.REVIEW and p.session.state == pv.INVALIDATED and p.session.invalid_reason == pv.REASON_FILES_CHANGED
    assert "정책 파일" in p.message_label.text() and "만들지 않았습니다" in p.message_label.text()
    assert listing(out_dir) == before and not [x for x in out_dir.iterdir() if x.name.startswith(".~")]      # 새 최종 파일도 임시 파일도 없다
    assert not w.next_button.isEnabled() and p.retry_button.isVisibleTo(w)


def test_new_conversion_is_refused_while_generating(manual, make_input):
    w, r = manual
    to_step2(w, make_input(n=3))
    generate(w)
    assert not w.step3.new_button.isEnabled()                                # 버튼도 비활성이다
    w.start_new_conversion()                                                 # 그래도 직접 호출되면 창이 거부한다
    w.restart_from_file_selection()
    assert w.generation.busy and w.navigator.current == Step.RESULT and w.navigator.locked and w.step2.session.state == pv.READY


# ---------- 파일 변경 · 읽기 불가 → 미리보기 무효화 · 재검토 ----------
def test_source_changed_before_generation_runs_creates_nothing_and_returns_to_step2_for_recheck(manual, make_input, out_dir):
    w, r = manual
    src = make_input(n=3)
    to_step2(w, src)
    generate(w)
    before = listing(out_dir)
    flip_byte_keep_size_and_mtime(src)
    r.run_all()
    p = w.step2
    assert w.navigator.current == Step.REVIEW and p.session.state == pv.INVALIDATED and p.session.invalid_reason == pv.REASON_FILES_CHANGED
    assert listing(out_dir) == before and "만들지 않았습니다" in p.message_label.text() and "바뀐 파일: 원본 파일" in p.message_label.text()
    assert p.retry_button.isVisibleTo(w) and not w.next_button.isEnabled() and r.pending == [] and not w.navigator.locked
    flip_byte_keep_size_and_mtime(src)                                       # 사용자가 의도한 상태로 되돌린 뒤
    p.retry_button.click()                                                    # 명시적으로 다시 확인
    assert p.session.state == pv.READY
    generate(w)
    r.run_all()
    assert w.generation.state == gn.SUCCESS and [x.name for x in out_dir.iterdir()] == [NAME]


def test_unreadable_source_is_reported_as_unreadable_and_creates_nothing(manual, make_input, out_dir, monkeypatch):
    w, r = manual
    src = make_input(n=3)
    to_step2(w, src)
    generate(w)
    real = conv.fingerprint_file
    monkeypatch.setattr(conv, "fingerprint_file", lambda path: (_ for _ in ()).throw(PermissionError("denied")) if str(path) == str(src) else real(path))
    r.run_all()
    assert w.step2.session.state == pv.INVALIDATED and "읽을 수 없는 파일: 원본 파일" in w.step2.message_label.text() and list(out_dir.iterdir()) == []


def test_encrypted_source_asks_for_the_password_again_after_invalidation(qapp, make_context, ready_settings, make_input, tmp_path, out_dir):
    r = ManualRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=r)
    enc = encrypt(make_input(n=3), tmp_path / "enc.xlsx")
    w.step1.model.set_source(enc)
    w.next_button.click()
    w.step2.password_edit.setText(PW)
    w.step2.password_ok.click()
    assert w.step2.session.state == pv.READY
    generate(w)
    flip_byte_keep_size_and_mtime(enc)
    r.run_all()
    assert w.step2.session.state == pv.INVALIDATED
    flip_byte_keep_size_and_mtime(enc)
    w.step2.retry_button.click()
    assert w.step2.session.state == pv.NEED_PASSWORD and "3회" in w.step2.password_attempts.text()      # 세션에 보관하지 않으므로 다시 입력
    assert PW not in texts(w) + repr(vars(w.step2.session)) and list(out_dir.iterdir()) == []
    w.generation.close()
    w.close()


# ---------- 템플릿 레이아웃 오류 ----------
@pytest.fixture
def bad_template_win(qapp, make_context, ready_settings, policy_file, out_dir, tmp_path):
    from openpyxl import load_workbook
    bad = tmp_path / "bad_layout.xlsx"
    wb = load_workbook(TEMPLATE)
    del wb["WINS"]
    wb.save(bad)
    settings = UserSettings(last_program="daechung").with_paths("daechung", template_path=str(bad), policy_path=str(policy_file), out_dir=str(out_dir))
    w, ctx = make_win(make_context, settings)
    yield w
    w.close()


def test_template_layout_error_is_shown_on_step3_with_settings_and_review_paths(bad_template_win, make_input, out_dir, monkeypatch):
    w = bad_template_win
    opened = []
    monkeypatch.setattr(w.step1, "open_settings", lambda: opened.append(1))
    (out_dir / "existing.xlsx").write_bytes(b"keep")
    before = listing(out_dir)
    to_step2(w, make_input(n=3))
    generate(w)
    s3 = w.step3
    assert w.generation.state == gn.FAILED and w.generation.failure_kind == gn.KIND_TEMPLATE and w.navigator.current == Step.RESULT
    assert [(r.severity, r.code) for r in s3.issue_rows()] == [("error", "TEMPLATE_LAYOUT")] and "처음 확인" in s3.failure_note.text()
    assert s3.settings_button.isVisibleTo(w) and s3.restart_button.isVisibleTo(w) and not s3.folder_box.isVisibleTo(w) and not s3.retry_button.isVisibleTo(w)
    assert "만들지 않았습니다" in s3.failure_note.text() and listing(out_dir) == before
    assert "성공" not in s3.failure_headline.text() and not s3.result_box.isVisibleTo(w)
    s3.settings_button.click()
    assert opened == [1]
    assert w.step2.session.state == pv.INVALIDATED and w.step2.session.invalid_reason == pv.REASON_GENERATION_FAILED     # 같은 확인 결과로 다시 만들 수 없다


def test_back_from_template_failure_shows_step2_review_required(bad_template_win, make_input):
    w = bad_template_win
    to_step2(w, make_input(n=3))
    generate(w)
    w.back_button.click()
    assert w.navigator.current == Step.REVIEW and w.step2.session.state == pv.INVALIDATED and "다시 확인" in w.step2.message_label.text() and w.step2.retry_button.isVisibleTo(w)
    assert not w.next_button.isEnabled()                                                              # 같은 확인 결과로는 다시 만들 수 없다


def test_restart_button_returns_to_file_selection_keeping_the_selection(bad_template_win, make_input):
    w = bad_template_win
    src = make_input(n=3)
    to_step2(w, src)
    generate(w)
    w.step3.restart_button.click()
    assert w.navigator.current == Step.FILE and w.step1.model.paths["source"] == str(src) and not w.navigator.locked
    assert w.generation.state == gn.IDLE and w.step2.session.state == pv.IDLE


# ---------- 저장 폴더 오류: 같은 Prepared 로 폴더를 바꿔 재시도 ----------
def test_folder_error_allows_changing_folder_and_retrying_with_the_same_prepared(qapp, make_context, ready_settings, make_input, tmp_path, out_dir, monkeypatch):
    prepares = []
    real_prepare = wf.prepare
    monkeypatch.setattr(wf, "prepare", lambda *a, **k: (prepares.append(1), real_prepare(*a, **k))[1])
    w, ctx = make_win(make_context, ready_settings)
    to_step2(w, make_input(n=3))
    n_prepare = len(prepares)
    out_dir.rmdir()                                                          # 미리보기 후 저장 폴더가 사라짐
    generate(w)
    s3 = w.step3
    assert w.generation.state == gn.FAILED and w.generation.failure_kind == gn.KIND_FOLDER and w.generation.can_retry
    assert [(r.severity, r.code) for r in s3.issue_rows()] == [("error", "OUTPUT_DIR_MISSING")] and s3.folder_box.isVisibleTo(w) and s3.retry_button.isVisibleTo(w)
    assert not s3.settings_button.isVisibleTo(w) and "만들지 않았습니다" in s3.failure_note.text() and not out_dir.exists()
    new_dir = tmp_path / "other_out"
    new_dir.mkdir()
    ctx.chooser.answers["folder"].append(str(new_dir))
    s3.change_folder_button.click()
    assert s3.folder_field.text() == str(new_dir) and w.generation.state == gn.FAILED and list(new_dir.iterdir()) == []      # 폴더를 바꿨다고 성공이 되지 않는다
    s3.retry_button.click()
    assert w.generation.state == gn.SUCCESS and [p.name for p in new_dir.iterdir()] == [NAME] and len(prepares) == n_prepare       # 원본을 다시 읽지 않았다
    assert s3.folder_value.full_text() == str(new_dir)
    w.close()


def test_invalid_replacement_folder_is_refused_and_keeps_the_failure(qapp, make_context, ready_settings, make_input, tmp_path, out_dir):
    w, ctx = make_win(make_context, ready_settings)
    to_step2(w, make_input(n=3))
    out_dir.rmdir()
    generate(w)
    ctx.chooser.answers["folder"].append(str(tmp_path / "also_missing"))
    w.step3.change_folder_button.click()
    assert w.generation.state == gn.FAILED and "찾을 수 없습니다" in w.step3.folder_message.text() and w.generation.out_dir == str(out_dir)
    w.close()


def test_retry_rechecks_fingerprints_and_returns_to_step2_if_a_file_changed(qapp, make_context, ready_settings, make_input, tmp_path, out_dir):
    w, ctx = make_win(make_context, ready_settings)
    src = make_input(n=3)
    to_step2(w, src)
    out_dir.rmdir()
    generate(w)
    new_dir = tmp_path / "other_out"
    new_dir.mkdir()
    ctx.chooser.answers["folder"].append(str(new_dir))
    w.step3.change_folder_button.click()
    flip_byte_keep_size_and_mtime(src)                                       # 재시도 전에 원본이 바뀜
    w.step3.retry_button.click()
    assert w.navigator.current == Step.REVIEW and w.step2.session.state == pv.INVALIDATED and list(new_dir.iterdir()) == []
    w.close()


@pytest.mark.parametrize("how,code", [("permission", "OUTPUT_PERMISSION"), ("io", "OUTPUT_IO")])
def test_permission_and_io_errors_are_folder_errors_with_catalog_text_and_no_new_files(how, code, qapp, make_context, ready_settings, make_input, out_dir, monkeypatch):
    w, ctx = make_win(make_context, ready_settings)
    (out_dir / "existing.xlsx").write_bytes(b"keep")
    to_step2(w, make_input(n=3))
    before = listing(out_dir)
    if how == "permission":
        monkeypatch.setattr(tempfile, "mkstemp", lambda *a, **k: (_ for _ in ()).throw(PermissionError("denied")))
    else:
        from openpyxl import Workbook
        monkeypatch.setattr(Workbook, "save", lambda self, *a, **k: (_ for _ in ()).throw(OSError(5, "io")))
    generate(w)
    s3 = w.step3
    assert w.generation.failure_kind == gn.KIND_FOLDER and s3.issue_rows()[0].code == code and s3.retry_button.isVisibleTo(w) and listing(out_dir) == before
    monkeypatch.undo()
    s3.retry_button.click()
    assert w.generation.state == gn.SUCCESS and len(listing(out_dir)) == 2
    w.close()


def test_back_from_folder_failure_keeps_the_preview_and_does_not_create_a_second_job(qapp, make_context, ready_settings, make_input, out_dir):
    r = ManualRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=r)
    to_step2(w, make_input(n=3))
    out_dir.rmdir()
    generate(w)
    r.run_all()
    assert w.generation.can_retry
    w.back_button.click()
    assert w.navigator.current == Step.REVIEW and w.step2.session.state == pv.READY
    jobs = len(r.pending)
    w.next_button.click()
    assert w.navigator.current == Step.RESULT and w.generation.state == gn.FAILED and w.step3.retry_button.isVisibleTo(w) and len(r.pending) == jobs
    w.generation.close()
    w.close()


# ---------- 출력 재검증 실패 · 예기치 않은 오류 ----------
def test_output_verification_failure_is_not_a_folder_error_and_cannot_be_retried(qapp, make_context, ready_settings, make_input, out_dir, monkeypatch):
    w, ctx = make_win(make_context, ready_settings)
    (out_dir / NAME).write_bytes(b"existing result")
    to_step2(w, make_input(n=3))
    before = listing(out_dir)
    monkeypatch.setattr(conv, "verify_output", lambda *a, **k: (_ for _ in ()).throw(conv.ValidationFailed([conv.ValidationError("OUTPUT_TOTAL_MISMATCH", "amount", 9)])))
    generate(w)
    s3 = w.step3
    assert w.generation.failure_kind == gn.KIND_VERIFY and s3.issue_rows()[0].code == "OUTPUT_TOTAL_MISMATCH"
    assert not s3.retry_button.isVisibleTo(w) and not s3.folder_box.isVisibleTo(w) and s3.restart_button.isVisibleTo(w) and "공개하지 않았습니다" in s3.failure_note.text()
    assert listing(out_dir) == before and w.step2.session.state == pv.INVALIDATED and "출력 재검증 통과" not in texts(s3)
    w.close()


def test_unexpected_exception_is_contained_and_no_path_is_shown_or_logged(qapp, make_context, ready_settings, make_input, out_dir, monkeypatch, caplog, capsys):
    import logging
    w, ctx = make_win(make_context, ready_settings)
    to_step2(w, make_input(n=3))
    monkeypatch.setattr(wf, "finish", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"boom {out_dir}/학생홍길동.xlsx")))
    with caplog.at_level(logging.DEBUG):
        generate(w)
    s3 = w.step3
    assert w.generation.failure_kind == gn.KIND_UNEXPECTED and "저장 폴더를 확인" in s3.failure_note.text() and s3.restart_button.isVisibleTo(w)
    shown = texts(s3)
    cap = capsys.readouterr()
    assert "홍길동" not in shown + caplog.text + cap.out + cap.err and str(out_dir) not in caplog.text + cap.out + cap.err
    w.close()


def test_ui_render_error_after_success_does_not_misclassify_the_created_file_as_failed(qapp, make_context, ready_settings, make_input, out_dir, monkeypatch):
    r = ManualRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=r)
    to_step2(w, make_input(n=3))
    generate(w)
    w.generation.on_change(lambda: (_ for _ in ()).throw(RuntimeError("ui bug")))      # 화면 쪽 리스너가 결과 반영 중 오류를 낸다
    with pytest.raises(RuntimeError):
        r.run_all()
    assert w.generation.state == gn.SUCCESS and (out_dir / NAME).is_file() and w.generation.failure_kind is None
    w.generation.close()
    w.close()


# ---------- 개인정보 · 키보드 ----------
def test_no_student_values_or_logs_in_any_step3_state(qapp, make_context, ready_settings, make_input, out_dir, caplog, capsys):
    import logging
    w, ctx = make_win(make_context, ready_settings)
    src = make_input(n=4)
    to_step2(w, src)
    row = w.step2.session.prepared._validated.rows[0].row
    with caplog.at_level(logging.DEBUG):
        generate(w)
        w.step3.copy_path_button.click()
    cap = capsys.readouterr()
    shown = texts(w.step3)
    for secret in (row.student_id, row.name, row.account_no, str(src)):
        assert secret and secret not in shown + caplog.text + cap.out + cap.err
    assert str(out_dir) not in caplog.text + cap.out + cap.err
    w.close()


def test_result_buttons_are_reachable_in_order_and_activatable_with_space(qapp, make_context, ready_settings, make_input, out_dir):
    from conftest import FakeActions
    actions = FakeActions()
    w, ctx = make_win(make_context, ready_settings, actions=actions)
    to_step2(w, make_input(n=3))
    generate(w)
    s3 = w.step3
    chain, x = [], s3.open_folder_button
    for _ in range(30):
        chain.append(x)
        x = x.nextInFocusChain()
        if x is s3.open_folder_button:
            break
    order = [c for c in chain if c in (s3.open_folder_button, s3.copy_path_button, s3.new_button)]
    assert order == [s3.open_folder_button, s3.copy_path_button, s3.new_button]
    QTest.keyClick(s3.copy_path_button, Qt.Key.Key_Space)
    assert actions.copied == [str(out_dir / NAME)]
    w.close()


def test_layout_renders_at_minimum_size_for_success_and_failure(qapp, make_context, ready_settings, make_input, out_dir):
    w, ctx = make_win(make_context, ready_settings)
    to_step2(w, make_input(n=4, extra=((2, 480, "9999년08월"),)))
    generate(w)
    w.resize(800, 600)
    QApplication.processEvents()
    assert not w.grab().isNull() and w.step3.width() >= 700
    w.close()


def test_default_context_uses_separate_workers_for_checks_and_generation(qapp):
    from scholarship_payment.ui.context import AppContext
    ctx = AppContext.default()
    assert isinstance(ctx.runner, QtRunner) and isinstance(ctx.generation_runner, QtRunner) and ctx.runner is not ctx.generation_runner and ctx.gen_runner is ctx.generation_runner
    ctx.runner.shutdown()
    ctx.generation_runner.shutdown()


def test_after_a_failed_generation_a_fresh_review_allows_generating_again(qapp, make_context, ready_settings, make_input, out_dir, monkeypatch):
    w, ctx = make_win(make_context, ready_settings)
    src = make_input(n=3)
    to_step2(w, src)
    with monkeypatch.context() as m:
        m.setattr(conv, "verify_output", lambda *a, **k: (_ for _ in ()).throw(conv.ValidationFailed([conv.ValidationError("OUTPUT_MISMATCH", "x", 5)])))
        generate(w)
    assert w.generation.failure_kind == gn.KIND_VERIFY and w.step2.session.state == pv.INVALIDATED
    w.back_button.click()
    w.step2.retry_button.click()                                             # 사용자가 명시적으로 다시 확인
    assert w.step2.session.state == pv.READY
    generate(w)
    assert w.generation.state == gn.SUCCESS and [p.name for p in out_dir.iterdir()] == [NAME]            # 실패한 작업은 파일을 남기지 않았고, 새 확인 결과로 만든 것은 1개
    w.close()


# ---------- 경계조건: 실제 워커 스레드에서의 예외·닫힘 ----------
def _wait_until(cond, seconds=5):
    deadline = time.time() + seconds
    while not cond() and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return cond()


@pytest.mark.parametrize("how", ["raises", "runner_converts_to_foreign_object"])
def test_unexpected_exception_in_a_real_worker_releases_generating_and_the_window_can_close(how, qapp, make_context, ready_settings, make_input, out_dir, caplog, capsys):
    import logging
    runner = QtRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=runner)
    to_step2(w, make_input(n=3))
    before = listing(out_dir)

    def boom(prepared, folder, now=None):
        raise RuntimeError(f"boom {folder}/학생홍길동.xlsx")

    w.generation._finish_fn = boom
    if how == "runner_converts_to_foreign_object":
        w.generation._finish_fn = lambda prepared, folder, now=None: object()                 # 작업 함수가 엉뚱한 객체를 돌려줌
    with caplog.at_level(logging.DEBUG):
        generate(w)
        assert _wait_until(lambda: not w.generation.busy)
    assert w.generation.state == gn.FAILED and w.generation.failure_kind == gn.KIND_UNEXPECTED and not w.navigator.locked and w.back_button.isEnabled()
    assert not w.step3.progress_box.isVisibleTo(w) and w.step3.failure_box.isVisibleTo(w) and listing(out_dir) == before
    cap = capsys.readouterr()
    assert "홍길동" not in texts(w.step3) + caplog.text + cap.out + cap.err and str(out_dir) not in caplog.text + cap.out + cap.err
    ev = QCloseEvent()
    w.closeEvent(ev)
    assert ev.isAccepted()                                                                        # 예외 뒤에도 정상적으로 닫을 수 있다


def test_result_arriving_after_the_session_is_closed_touches_no_widget_and_raises_nothing(qapp, make_context, ready_settings, make_input, out_dir, monkeypatch):
    gate, started = threading.Event(), threading.Event()
    real = wf.finish
    monkeypatch.setattr(wf, "finish", lambda p, d: (started.set(), gate.wait(5), real(p, d))[2])
    errors = []
    monkeypatch.setattr("sys.excepthook", lambda *a: errors.append(a))
    runner = QtRunner()
    w, ctx = make_win(make_context, ready_settings, gen_runner=runner)
    to_step2(w, make_input(n=3))
    generate(w)
    assert started.wait(5)
    renders = []
    w.generation.on_change(lambda: renders.append(1))
    n = len(renders)
    w.generation.close()                                                                          # 창이 이미 닫힌 상황(강제 소멸 시나리오)
    w.step3.deleteLater()
    QApplication.processEvents()
    gate.set()
    runner.shutdown(5000)                                                                         # 작업이 끝나길 기다린다
    for _ in range(50):
        QApplication.processEvents()
    assert len(renders) == n and errors == []                                                     # 늦은 콜백은 위젯을 건드리지 않고 예외도 없다
    assert [p.name for p in out_dir.iterdir()] == [NAME]                                          # (작업 자체는 끝까지 정상 완료)
