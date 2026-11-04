"""Step 2 읽기 전용 지급내역 미리보기 화면: 확인한 범위만 표시, 로딩·중복 실행 방지, 오류/경고/참고 구분, 비밀번호 3회, 변경 무효화, 개인정보 비노출."""
import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLabel, QLineEdit, QProgressBar, QTableView, QTableWidget, QTreeView  # noqa: E402

from scholarship_payment.app.convert import finish  # noqa: E402
from scholarship_payment.ui import preview as pv  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402
from scholarship_payment.ui.navigation import Step  # noqa: E402
from scholarship_payment.ui.runner import ManualRunner  # noqa: E402

from prep_helpers import PW, encrypt, flip_byte_keep_size_and_mtime  # noqa: E402

CARRY = ((2, 8 * 60, "9999년08월"), (3, 90, "9999년08월"))


def texts(w):
    return " ".join(x.text() for x in w.findChildren(QLabel))


def open_window(make_context, settings, runner=None):
    w = MainWindow(context=make_context(settings=settings, runner=runner))
    w.show()
    return w


def go_step2(w, src):
    w.step1.model.set_source(src)
    if isinstance(w.context.runner, ManualRunner):
        w.context.runner.run_all()                                           # Step 1 의 구조 검사를 끝낸다
    assert w.next_button.isEnabled()
    w.next_button.click()
    return w


@pytest.fixture
def win(qapp, make_context, ready_settings):
    w = open_window(make_context, ready_settings)
    yield w
    w.close()


# ---------- 정상 미리보기: 실제 확인한 값만 ----------
def test_entering_step2_prepares_and_shows_only_measured_values(win, make_input):
    go_step2(win, make_input(n=4))
    s, p = win.step2.session, win.step2
    assert win.navigator.current == Step.REVIEW and s.state == pv.READY
    assert p.month_value.text() == "9999년 09월" and p.count_value.text() == "4명" and p.total_value.text() == f"{s.summary.total_amount:,}원"
    assert p.date_value.text() == "2099.10.07" and p.program_value.text().startswith("대청교")
    assert p.result_badge.text() == "확인한 범위에서 차단 오류 없음" and p.result_badge.property("badge") == "verified"


def test_scope_lists_separate_what_was_checked_from_what_was_not(win, make_input):
    go_step2(win, make_input(n=3))
    checked, unchecked = win.step2.scope_checked.text(), win.step2.scope_unchecked.text()
    assert "은행코드" in checked and "학번 중복" in checked
    assert "출력 템플릿의 구조" in unchecked and "엑셀 파일 생성" in unchecked and "저장 폴더" in unchecked


def test_no_unverified_claims_no_student_table_no_scores(win, make_input):
    go_step2(win, make_input(n=4))
    t = texts(win.step2) + " " + win.footer_hint.text() + " " + win.next_button.text()
    for banned in ("정상 연결", "변환 준비 완료", "생성 완료", "점수", "100%", "SHA", "무결", "안전 변환", "남은 시간", "예상"):
        assert banned not in t
    assert not [c for kind in (QTableView, QTableWidget, QTreeView, QAbstractItemView) for c in win.step2.findChildren(kind)]


def test_no_student_values_or_paths_appear_anywhere_on_screen(win, make_input, tmp_path):
    src = make_input(n=4)
    go_step2(win, src)
    row = win.step2.session.prepared._validated.rows[0].row
    t = texts(win.step2) + " ".join(x.text() for x in win.step2.findChildren(QLineEdit))
    for secret in (row.student_id, row.name, row.account_no, str(src), str(tmp_path)):
        assert secret and secret not in t


def test_generate_button_is_visible_but_disabled_in_phase3(win, make_input):
    go_step2(win, make_input(n=3))
    assert win.step2.session.state == pv.READY
    assert win.next_button.isVisible() and not win.next_button.isEnabled() and win.next_button.text() == "지급명단 생성"
    assert "제공되지 않" in win.next_button.toolTip() and not win.navigator.can_next()
    assert win.footer_hint.text()


def test_displayed_count_and_total_equal_the_file_finish_would_create(win, make_input, out_dir):
    go_step2(win, make_input(n=5))
    p = win.step2.session.prepared
    res = finish(p, out_dir)
    from openpyxl import load_workbook
    wris = load_workbook(res.output_path)["WRIS"]
    amounts = [wris.cell(r, 5).value for r in range(2, wris.max_row + 1) if wris.cell(r, 5).value is not None]
    assert win.step2.count_value.text() == f"{len(amounts)}명" and win.step2.total_value.text() == f"{sum(amounts):,}원"


# ---------- 로딩 · 중복 실행 방지 ----------
def test_loading_shows_indeterminate_progress_without_estimates_and_blocks_actions(qapp, make_context, ready_settings, make_input):
    r = ManualRunner()
    w = open_window(make_context, ready_settings, r)
    r.run_all()
    go_step2(w, make_input(n=3))
    bar = w.step2.progress
    assert isinstance(bar, QProgressBar) and (bar.minimum(), bar.maximum()) == (0, 0) and not w.step2.progress_box.isHidden()
    assert "확인하는 중" in w.step2.progress_label.text() and "초" not in w.step2.progress_label.text() and "%" not in w.step2.progress_label.text()
    assert not w.step2.retry_button.isEnabled() and w.step2.result_box.isHidden()
    w.close()


def test_entering_again_while_preparing_does_not_start_a_second_job(qapp, make_context, ready_settings, make_input):
    r = ManualRunner()
    w = open_window(make_context, ready_settings, r)
    r.run_all()
    go_step2(w, make_input(n=3))
    jobs = len(r.pending)
    w.step2.enter(w.model.snapshot())
    w.step2.retry_button.click()
    assert len(r.pending) == jobs
    r.run_all()
    assert w.step2.session.state == pv.READY
    w.close()


def test_back_while_preparing_discards_late_result_and_forward_prepares_anew(qapp, make_context, ready_settings, make_input):
    r = ManualRunner()
    w = open_window(make_context, ready_settings, r)
    r.run_all()
    go_step2(w, make_input(n=3))
    w.back_button.click()
    r.run_all()                                                              # 늦게 도착한 결과
    assert w.navigator.current == Step.FILE and w.step2.session.state == pv.IDLE and w.step2.session.prepared is None
    w.next_button.click()
    assert w.step2.session.state == pv.PREPARING
    r.run_all()
    assert w.step2.session.state == pv.READY
    w.close()


# ---------- 오류 · 경고 · 참고 ----------
def test_blocking_errors_are_listed_with_korean_title_action_rows_and_block_generation(win, make_input):
    go_step2(win, make_input(n=5, mutate=lambda ws: ws.__setitem__("F7", ws["F5"].value)))
    p = win.step2
    assert p.session.state == pv.FAILED and p.result_box.isHidden() and not win.next_button.isEnabled()
    rows = p.issue_rows()
    dup = next(r for r in rows if r.code == "DUPLICATE_STUDENT_ID")
    assert dup.severity == "error" and "같은 학번이 여러 행에 있습니다" in dup.title.text() and "확인하세요" in dup.action.text() and dup.location.text() == "행 5, 7"
    assert "DUPLICATE_STUDENT_ID" in dup.code_label.text()
    assert p.headline.text().startswith("차단 오류 1종")


def test_notes_and_warnings_are_separate_from_errors(win, make_input):
    go_step2(win, make_input(n=4, extra=CARRY))
    p = win.step2
    kinds = {(r.severity, r.code) for r in p.issue_rows()}
    assert ("note", "STUDENT_MERGED_ROWS") in kinds and not [k for k in kinds if k[0] == "error"]
    assert p.session.state == pv.READY and p.result_badge.property("badge") == "verified"
    assert "참고 " in p.headline.text() and "차단 오류" not in p.headline.text()


def test_missing_bank_names_are_shown_for_fixing(qapp, make_context, ready_settings, make_input):
    w = open_window(make_context, ready_settings)
    go_step2(w, make_input(n=3, mutate=lambda s: [s.__setitem__(f"T{r}", "표에없는가상은행") for r in (3, 4)]))
    assert w.step2.session.state == pv.FAILED and "표에없는가상은행" in w.step2.bank_label.text() and not w.step2.bank_label.isHidden()
    w.close()


def test_policy_problem_found_at_step2_is_reported_with_guidance(qapp, make_context, ready_settings, make_input, policy_file):
    w = open_window(make_context, ready_settings)
    w.step1.model.set_source(make_input(n=3))
    policy_file.write_text("{}", encoding="utf-8")                          # Step 1 검사 뒤 정책 파일이 망가짐
    w.next_button.click()                                                    # 다음 직전 재확인 → 이동하지 않거나, 이동하면 Step 2 에서 보고
    on_step2 = w.navigator.current == Step.REVIEW
    rows = w.step2.issue_rows() if on_step2 else []
    assert (not on_step2) or any(r.code.startswith("POLICY_") for r in rows)
    w.close()


# ---------- 비밀번호(최대 3회) ----------
@pytest.fixture
def enc_win(qapp, make_context, ready_settings, make_input, tmp_path):
    w = open_window(make_context, ready_settings)
    go_step2(w, encrypt(make_input(n=3), tmp_path / "enc.xlsx"))
    yield w
    w.close()


def test_password_panel_appears_only_for_encrypted_file_and_masks_input(enc_win, win, make_input):
    p = enc_win.step2
    assert p.session.state == pv.NEED_PASSWORD and not p.password_box.isHidden() and p.password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert "3회" in p.password_attempts.text() and p.result_box.isHidden() and not enc_win.next_button.isEnabled()
    go_step2(win, make_input(n=3))
    assert win.step2.password_box.isHidden()                                  # 일반 파일은 묻지 않는다


def test_wrong_then_correct_password_and_field_is_cleared_after_each_submit(enc_win):
    p = enc_win.step2
    p.password_edit.setText("틀림1")
    p.password_ok.click()
    assert p.password_edit.text() == "" and "맞지 않습니다" in p.password_error.text() and "2회" in p.password_attempts.text()
    p.password_edit.setText(PW)
    p.password_ok.click()
    assert p.session.state == pv.READY and p.password_box.isHidden() and p.password_edit.text() == ""
    assert PW not in texts(enc_win) + repr(vars(p.session))


def test_three_wrong_passwords_lock_input_until_leaving_the_step(enc_win):
    p = enc_win.step2
    for i in range(3):
        p.password_edit.setText(f"틀림{i}")
        p.password_ok.click()
    assert p.session.state == pv.LOCKED and not p.password_edit.isEnabled() and not p.password_ok.isEnabled() and not p.retry_button.isVisible()
    assert "3번 틀려" in p.message_label.text()
    enc_win.back_button.click()
    enc_win.next_button.click()
    assert enc_win.step2.session.state == pv.NEED_PASSWORD and "3회" in enc_win.step2.password_attempts.text()   # 이전 단계에서 돌아오면 다시 3회


def test_cancel_password_then_retry_asks_again_and_keeps_attempt_count(enc_win):
    p = enc_win.step2
    p.password_edit.setText("틀림")
    p.password_ok.click()
    p.password_cancel.click()
    assert p.session.state == pv.CANCELLED and "취소했습니다" in p.message_label.text() and p.retry_button.isVisible()
    p.retry_button.click()
    assert p.session.state == pv.NEED_PASSWORD and "2회" in p.password_attempts.text()
    p.password_edit.setText(PW)
    p.password_ok.click()
    assert p.session.state == pv.READY


def test_enter_key_submits_password_and_tab_order_is_edit_ok_cancel(enc_win):
    p = enc_win.step2
    p.password_edit.setText(PW)
    QTest.keyClick(p.password_edit, Qt.Key.Key_Return)
    assert p.session.state == pv.READY


def test_password_tab_order(enc_win):
    p = enc_win.step2
    chain, w = [], p.password_edit
    for _ in range(30):
        chain.append(w)
        w = w.nextInFocusChain()
        if w is p.password_edit:
            break
    order = [x for x in chain if x in (p.password_edit, p.password_ok, p.password_cancel)]
    assert order == [p.password_edit, p.password_ok, p.password_cancel]


# ---------- 파일 변경 → 무효화 ----------
def test_file_change_invalidates_the_preview_and_never_regenerates_automatically(qapp, make_context, ready_settings, make_input):
    r = ManualRunner()
    w = open_window(make_context, ready_settings, r)
    r.run_all()
    src = make_input(n=3)
    w.step1.model.set_source(src)
    r.run_all()
    w.next_button.click()
    r.run_all()
    p = w.step2
    assert p.session.state == pv.READY
    flip_byte_keep_size_and_mtime(src)
    p.refresh_freshness()
    r.run_all()
    assert p.session.state == pv.INVALIDATED and p.result_box.isHidden() and "바뀌었습니다" in p.message_label.text() and "원본 파일" in p.message_label.text()
    assert not w.next_button.isEnabled() and p.retry_button.isVisible() and r.pending == []
    flip_byte_keep_size_and_mtime(src)                                       # 원래대로 되돌린 뒤 사용자가 직접 다시 확인
    p.retry_button.click()
    r.run_all()
    assert p.session.state == pv.READY and not p.result_box.isHidden()
    w.close()


def test_window_activation_triggers_a_freshness_check_only_on_step2(win, make_input, monkeypatch):
    src = make_input(n=3)
    go_step2(win, src)
    flip_byte_keep_size_and_mtime(src)
    monkeypatch.setattr(win, "isActiveWindow", lambda: True)
    win.changeEvent(QEvent(QEvent.Type.ActivationChange))
    assert win.step2.session.state == pv.INVALIDATED


def test_back_from_step2_clears_summary_and_does_not_keep_stale_state(win, make_input):
    go_step2(win, make_input(n=3))
    win.back_button.click()
    assert win.navigator.current == Step.FILE and win.step2.session.summary is None and win.step2.result_box.isHidden()
    assert win.next_button.text() == "다음: 지급내역 확인"


# ---------- 읽기 전용 ----------
def test_step2_creates_no_files_and_leaves_inputs_untouched(win, make_input, tmp_path, out_dir):
    import hashlib
    from pathlib import Path
    src = make_input(n=3)
    h = hashlib.sha256(Path(src).read_bytes()).hexdigest()
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    go_step2(win, src)
    win.step2.refresh_freshness()
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before and hashlib.sha256(Path(src).read_bytes()).hexdigest() == h and list(out_dir.iterdir()) == []


def test_layout_renders_at_minimum_size_and_body_scrolls(win, make_input):
    go_step2(win, make_input(n=4, extra=CARRY))
    win.resize(800, 600)
    QApplication.processEvents()
    assert not win.grab().isNull() and win.step2.width() >= 700


def test_failed_state_offers_an_explicit_recheck_button_and_it_restarts_from_scratch(qapp, make_context, ready_settings, make_input, tmp_path):
    w = open_window(make_context, ready_settings)
    src = make_input(n=5, mutate=lambda ws: ws.__setitem__("F7", ws["F5"].value))
    go_step2(w, src)
    p = w.step2
    assert p.session.state == pv.FAILED and p.retry_button.isVisibleTo(w) and p.retry_button.isEnabled()
    fixed = make_input(n=5)                                                 # 사용자가 같은 경로에 올바른 파일을 다시 저장했다고 가정
    from pathlib import Path
    Path(src).write_bytes(Path(fixed).read_bytes())
    p.retry_button.click()
    assert p.session.state == pv.READY and p.result_box.isVisibleTo(w)
    w.close()


# ---------- 추가 검증: 암호 파일·비동기 상태·비밀번호 비노출 ----------
def test_selecting_another_file_while_an_encrypted_file_is_being_checked_ignores_the_old_result(qapp, make_context, ready_settings, make_input, tmp_path):
    r = ManualRunner()
    w = open_window(make_context, ready_settings, r)
    r.run_all()
    enc = encrypt(make_input(n=3), tmp_path / "enc.xlsx")
    plain = make_input(n=3)
    w.step1.model.set_source(enc)                                            # 암호 파일의 구조 검사가 대기 중
    w.step1.model.set_source(plain)                                          # 검사가 끝나기 전에 다른 파일 선택
    r.run(1)
    r.run(0)                                                                 # 이전(암호 파일) 결과가 늦게 도착
    assert w.step1.model.paths["source"] == str(plain) and w.step1.model.state("source").note is None
    assert "암호가 걸린 파일로 보입니다" not in w.step1.source_message.text() and w.next_button.isEnabled()
    w.close()


def test_back_while_waiting_for_password_discards_everything_and_next_asks_again_from_scratch(enc_win):
    p = enc_win.step2
    p.password_edit.setText("틀림")
    p.password_ok.click()
    p.password_edit.setText("입력중이던-비밀번호")
    enc_win.back_button.click()
    assert enc_win.navigator.current == Step.FILE and p.session.state == pv.IDLE and p.password_edit.text() == "" and p.session.attempts == 0
    enc_win.next_button.click()
    assert p.session.state == pv.NEED_PASSWORD and "3회" in p.password_attempts.text()


def test_password_submitted_then_back_and_forward_old_result_cannot_overwrite_the_new_preview(qapp, make_context, ready_settings, make_input, tmp_path):
    r = ManualRunner()
    w = open_window(make_context, ready_settings, r)
    r.run_all()
    go_step2(w, encrypt(make_input(n=3), tmp_path / "enc.xlsx"))
    r.run_all()
    r.pending.clear()
    p = w.step2
    p.password_edit.setText(PW)
    p.password_ok.click()                                                    # 비밀번호 작업이 대기열에 있다
    w.back_button.click()
    w.next_button.click()                                                    # 새 미리보기 시작(암호 파일이므로 다시 비밀번호 요청)
    r.run(0)                                                                 # 이전 작업(올바른 비밀번호)이 늦게 끝나도
    assert p.session.state in (pv.PREPARING, pv.NEED_PASSWORD) and p.session.summary is None
    r.run_all()
    assert p.session.state == pv.NEED_PASSWORD and p.session.summary is None  # 비밀번호는 다시 입력받는다(세션에 보관하지 않음)
    w.close()


def test_password_never_reaches_settings_file_errors_logs_or_output(enc_win, caplog, capsys):
    import logging
    p = enc_win.step2
    with caplog.at_level(logging.DEBUG):
        p.password_edit.setText("틀린-비밀번호-xyz")
        p.password_ok.click()
        p.password_edit.setText(PW)
        p.password_ok.click()
    assert p.session.state == pv.READY
    store = enc_win.context.store
    blobs = [texts(enc_win), repr(vars(p.session)), repr(p.session.prepared), repr(p.session.summary), caplog.text, capsys.readouterr().out + capsys.readouterr().err]
    if store.path.exists():
        blobs.append(store.path.read_text(encoding="utf-8"))
    for secret in (PW, "틀린-비밀번호-xyz"):
        assert not [b for b in blobs if secret in b]


def test_ui_text_never_claims_the_password_is_erased_from_memory(win):
    import inspect
    from scholarship_payment.ui import preview, step2
    shown = texts(win.step2) + step2.CHECKED_TEXT + step2.UNCHECKED_TEXT + " ".join(step2.MESSAGES.values()) + win.step2.password_hint.text()
    code = inspect.getsource(step2) + inspect.getsource(preview)
    for claim in ("메모리에서 삭제", "메모리에서 지", "소거", "완전히 지", "흔적 없이"):
        assert claim not in shown and claim not in code


def test_unreadable_input_is_reported_as_unreadable_not_as_changed(qapp, make_context, ready_settings, make_input, monkeypatch):
    from scholarship_payment.app import convert as conv
    w = open_window(make_context, ready_settings)
    src = make_input(n=3)
    go_step2(w, src)
    real = conv.fingerprint_file
    monkeypatch.setattr(conv, "fingerprint_file", lambda path: (_ for _ in ()).throw(PermissionError("denied")) if str(path) == str(src) else real(path))
    w.step2.refresh_freshness()
    p = w.step2
    assert p.session.state == pv.INVALIDATED and p.session.changed == ("source",) and p.session.changed_codes == {"source": "INPUT_FILE_UNREADABLE"}
    assert "읽을 수 없습니다" in p.message_label.text() and "읽을 수 없는 파일: 원본 파일" in p.message_label.text() and str(src) not in p.message_label.text()
    w.close()
