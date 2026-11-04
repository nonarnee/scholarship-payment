"""Step 1 화면: 필수 입력·상태 표시·Navigator 연동·DropZone·백그라운드 검증·키보드·개인정보."""
import threading
import time

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from scholarship_payment.config import user_settings as us  # noqa: E402
from scholarship_payment.ui import validators as v  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402
from scholarship_payment.ui.navigation import Step  # noqa: E402
from scholarship_payment.ui.runner import ManualRunner  # noqa: E402


pytestmark = pytest.mark.filterwarnings("ignore:Function.*QDragEnterEvent.*:DeprecationWarning")


def make_window(make_context, **kw):
    ctx = make_context(**kw)
    w = MainWindow(context=ctx)
    w.show()
    return w, ctx


@pytest.fixture
def win(qapp, make_context):
    w, ctx = make_window(make_context)
    yield w
    w.close()


@pytest.fixture
def ready_win(qapp, make_context, ready_settings):
    w, ctx = make_window(make_context, settings=ready_settings)
    yield w
    w.close()


def texts(w):
    return " ".join(x.text() for x in w.findChildren(QLabel))


def urls_mime(*paths):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return m


def drop(zone, *paths):
    m = urls_mime(*paths)
    zone.dragEnterEvent(QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    state = zone.property("state")
    zone.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    return state


# ---------- 구조 ----------
def test_step1_widgets_and_defaults(win):
    p = win.step1
    assert [p.program_combo.itemText(i) for i in range(3)] == ["대청교 (대학생 청소년교육지원)", "다문화·탈북학생 멘토링", "AI멘토링"]
    assert p.date_edit.text() == "2099.10.07" and p.program_combo.currentIndex() == 0
    for name in ("pick_button", "reset_button", "out_dir_button", "settings_button", "replace_button"):
        assert getattr(p, name).isEnabled() or name == "reset_button"
    assert p.drop_zone.acceptDrops() and win.stack.currentIndex() == 0


def test_next_is_blocked_until_every_required_input_is_ok_and_labelled_for_step2(win):
    assert not win.next_button.isEnabled() and win.next_button.text() == "다음: 지급내역 확인"
    assert "선택하지 않았습니다" in texts(win.step1)


def test_full_valid_selection_enables_next_and_navigates_to_step2(ready_win, make_input, chooser):
    w = ready_win
    chooser.answers["source"].append(str(make_input(n=2)))
    w.step1.pick_button.click()
    assert w.next_button.isEnabled() and w.navigator.can_next()
    w.next_button.click()
    assert w.navigator.current == Step.REVIEW and w.stack.currentIndex() == 1
    w.back_button.click()
    assert w.navigator.current == Step.FILE and w.step1.model.paths["source"] is not None     # 돌아와도 선택 유지


def test_cancelled_file_dialog_changes_nothing(ready_win, chooser):
    ready_win.step1.pick_button.click()
    assert ready_win.step1.model.paths["source"] is None and not ready_win.next_button.isEnabled()


def test_reset_clears_source_and_blocks_next(ready_win, make_input, chooser):
    chooser.answers["source"].append(str(make_input(n=2)))
    ready_win.step1.pick_button.click()
    ready_win.step1.reset_button.click()
    assert ready_win.step1.model.paths["source"] is None and not ready_win.next_button.isEnabled()
    assert "선택하지 않았습니다" in texts(ready_win.step1)


def test_invalid_date_blocks_next_with_message(ready_win, make_input, chooser):
    chooser.answers["source"].append(str(make_input(n=2)))
    ready_win.step1.pick_button.click()
    ready_win.step1.date_edit.setText("2099-10-07")
    assert not ready_win.next_button.isEnabled() and "YYYY.MM.DD" in ready_win.step1.date_error.text() and not ready_win.step1.date_error.isHidden()
    ready_win.step1.date_edit.setText("2099.10.09")
    assert ready_win.next_button.isEnabled() and ready_win.step1.date_error.isHidden()


def test_program_change_resets_source_and_shows_that_programs_status(ready_win, make_input, chooser):
    chooser.answers["source"].append(str(make_input(n=2)))
    ready_win.step1.pick_button.click()
    ready_win.step1.program_combo.setCurrentIndex(2)
    p = ready_win.step1
    assert p.model.program == "ai" and p.model.paths["source"] is None and not ready_win.next_button.isEnabled()
    assert p.template_badge.text() == "설정 필요" and p.policy_badge.text() == "설정 필요"
    p.program_combo.setCurrentIndex(0)
    assert p.template_badge.property("badge") == "verified" and p.model.paths["source"] is None


def test_folder_button_sets_session_folder_without_persisting(ready_win, tmp_path, chooser):
    other = tmp_path / "other"
    other.mkdir()
    chooser.answers["folder"].append(str(other))
    ready_win.step1.out_dir_button.click()
    assert ready_win.step1.out_dir_field.text() == str(other)
    assert us.load(ready_win.step1.model.store.path).settings.paths("daechung").out_dir != str(other)


# ---------- 상태 표현: 검증하지 않은 것을 정상·완료로 쓰지 않는다 ----------
def test_badges_describe_what_was_actually_checked(ready_win, make_input, chooser):
    p = ready_win.step1
    chooser.answers["source"].append(str(make_input(n=2)))
    p.pick_button.click()
    assert p.source_badge.text() == "엑셀 형식 확인됨 (내용은 아직 읽지 않음)" and p.source_badge.property("badge") == "verified"
    assert p.template_badge.text() == "WRIS 머리글 확인됨" and p.policy_badge.text() == "정책 형식 확인됨"
    banned = ("파싱 완료", "건 감지", "ENGINE READY", "Local Isolated", "CONFIG_ID", "개 열 매핑", "100%", "변환 준비 완료", "정상 연결", "SHA-256", "Noto")
    assert not [b for b in banned if b in texts(ready_win)]


def test_encrypted_looking_file_shows_caution_but_still_allows_next(ready_win, tmp_path, chooser):
    enc = tmp_path / "enc.xlsx"
    enc.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 64)
    chooser.answers["source"].append(str(enc))
    ready_win.step1.pick_button.click()
    assert "암호가 걸린 파일로 보입니다" in ready_win.step1.source_message.text() and ready_win.next_button.isEnabled()


def test_bad_source_shows_reason_and_blocks(ready_win, tmp_path, chooser):
    bad = tmp_path / "x.xlsx"
    bad.write_bytes(b"not a zip")
    chooser.answers["source"].append(str(bad))
    ready_win.step1.pick_button.click()
    assert ready_win.step1.source_badge.property("badge") == "error" and "손상" in ready_win.step1.source_message.text() and not ready_win.next_button.isEnabled()


def test_source_info_shows_name_size_and_path_to_the_user_only(ready_win, make_input, chooser):
    src = make_input(n=2)
    chooser.answers["source"].append(str(src))
    ready_win.step1.pick_button.click()
    p = ready_win.step1
    assert p.file_name.text() == src.name and p.file_path.full_text() == str(src) and "KB" in p.file_size.text() or "B" in p.file_size.text()


# ---------- DropZone ----------
def test_drop_single_xlsx_is_accepted(ready_win, make_input):
    state = drop(ready_win.step1.drop_zone, make_input(n=2))
    assert state == "active" and ready_win.step1.model.paths["source"] and ready_win.next_button.isEnabled()
    assert ready_win.step1.drop_zone.property("state") == "idle"


@pytest.mark.parametrize("kind,msg", [("multi", "한 개"), ("csv", ".xlsx"), ("dir", "폴더"), ("missing", "찾을 수 없")])
def test_drop_rejections_show_reason_and_do_not_select(ready_win, make_input, tmp_path, kind, msg):
    good = make_input(n=2)
    csv = tmp_path / "a.csv"
    csv.write_bytes(b"x")
    args = {"multi": (good, good), "csv": (csv,), "dir": (tmp_path,), "missing": (tmp_path / "없음.xlsx",)}[kind]
    state = drop(ready_win.step1.drop_zone, *args)
    assert state == "reject" and ready_win.step1.model.paths["source"] is None and msg in ready_win.step1.source_message.text()
    assert not ready_win.next_button.isEnabled()


def test_drop_non_file_payload_is_ignored_and_leave_resets_state(ready_win):
    z = ready_win.step1.drop_zone
    m = QMimeData()
    m.setText("그냥 글자")
    ev = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    z.dragEnterEvent(ev)
    assert not ev.isAccepted() and z.property("state") == "idle"
    keep = urls_mime("/x/a.xlsx")                            # 이벤트는 QMimeData 를 소유하지 않으므로 살려 둔다
    z.dragEnterEvent(QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, keep, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    z.dragLeaveEvent(QDragLeaveEvent())
    assert z.property("state") == "idle"


def test_second_valid_drop_replaces_the_previous_selection(ready_win, make_input, synthetic, tmp_path):
    a = make_input(n=2)
    drop(ready_win.step1.drop_zone, a)
    b = tmp_path / "b.xlsx"
    b.write_bytes(a.read_bytes())
    drop(ready_win.step1.drop_zone, b)
    assert ready_win.step1.model.paths["source"] == str(b)


# ---------- 백그라운드 검증 ----------
def test_stale_result_never_overwrites_the_latest_selection_in_the_ui(qapp, make_context, ready_settings, make_input, tmp_path):
    runner = ManualRunner()
    w, ctx = make_window(make_context, runner=runner, settings=ready_settings)
    runner.run_all()
    good, bad = make_input(n=2), tmp_path / "bad.xlsx"
    bad.write_bytes(b"zzz")
    w.step1.model.set_source(good)
    w.step1.model.set_source(bad)
    assert w.step1.source_badge.text() == "구조 확인 중…" and not w.next_button.isEnabled()
    runner.run(1)
    runner.run(0)
    assert w.step1.source_badge.property("badge") == "error" and not w.next_button.isEnabled()
    w.close()


def test_real_thread_runner_keeps_ui_responsive_and_delivers_on_main_thread(qapp, make_context, ready_settings, make_input, monkeypatch):
    from scholarship_payment.ui.qt_runner import QtRunner

    gate, started, seen = threading.Event(), threading.Event(), {}
    real = v.heavy

    def slow(kind, path):
        if kind == "source":
            started.set()
            seen["worker"] = threading.current_thread()
            gate.wait(5)
        return real(kind, path)

    monkeypatch.setattr(v, "heavy", slow)
    runner = QtRunner()
    w, ctx = make_window(make_context, runner=runner, settings=ready_settings)
    deadline = time.time() + 5
    while runner.pending() and time.time() < deadline:
        QApplication.processEvents()
    w.step1.model.set_source(make_input(n=2))
    assert started.wait(5)
    t0 = time.time()
    for _ in range(50):
        QApplication.processEvents()                       # 검사가 막혀 있어도 이벤트 처리는 계속된다
    assert time.time() - t0 < 2 and w.step1.source_badge.text() == "구조 확인 중…" and not w.next_button.isEnabled()
    gate.set()
    deadline = time.time() + 5
    while not w.next_button.isEnabled() and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert w.next_button.isEnabled() and seen["worker"] is not threading.main_thread()
    runner.shutdown()
    w.close()


# ---------- 설정 상태 안내 ----------
def test_recovered_settings_notice_is_shown_without_internal_paths(qapp, make_context, tmp_path):
    ctx = make_context()
    ctx.store.path.parent.mkdir(parents=True, exist_ok=True)
    ctx.store.path.write_text("{broken", encoding="utf-8")
    from scholarship_payment.ui.state import SettingsStore
    ctx.store = SettingsStore(ctx.store.path)
    w = MainWindow(context=ctx)
    w.show()
    n = w.step1.notice_label.text()
    assert not w.step1.notice.isHidden() and "기본값" in n and "settings.json.bak" in n and str(tmp_path) not in n
    w.close()


def test_no_notice_when_settings_are_fine(win):
    assert win.step1.notice.isHidden()


# ---------- 키보드 · 개인정보 ----------
def test_tab_order_reaches_every_control_in_reading_order(win):
    p = win.step1
    chain, w0 = [], p.settings_button
    w = w0
    for _ in range(40):
        chain.append(w)
        w = w.nextInFocusChain()
        if w is w0:
            break
    order = [x for x in chain if x in (p.settings_button, p.program_combo, p.date_edit, p.pick_button, p.reset_button, p.out_dir_button, p.replace_button, win.back_button, win.next_button)]
    assert order == [p.settings_button, p.program_combo, p.date_edit, p.pick_button, p.reset_button, p.out_dir_button, p.replace_button, win.back_button, win.next_button]
    assert not p.drop_zone.focusPolicy() & Qt.FocusPolicy.TabFocus


def test_buttons_are_keyboard_activatable(ready_win, make_input, chooser):
    chooser.answers["source"].append(str(make_input(n=2)))
    assert ready_win.step1.pick_button.focusPolicy() & Qt.FocusPolicy.TabFocus
    QTest.keyClick(ready_win.step1.pick_button, Qt.Key.Key_Space)          # 마우스 없이 Space 로 누른다
    assert ready_win.step1.model.paths["source"] is not None


def test_page_texts_contain_no_personal_data_and_no_network_modules(win):
    import re
    import sys
    assert not re.search(r"[0-9]{6}-[0-9]{7}|@[a-z0-9-]+\.(com|kr)", texts(win))
    assert not [m for m in sys.modules if m.startswith("PySide6.QtNetwork")]


def test_grab_renders_at_minimum_size(win):
    win.resize(800, 600)
    QApplication.processEvents()
    assert not win.grab().isNull() and win.step1.width() >= 700
    assert isinstance(win.step1, QWidget)


# ---------- 막힌 이유 요약(푸터): 접힌 영역 아래의 상태를 못 봐도 이유를 알 수 있게 ----------
def test_footer_lists_what_is_still_needed_and_clears_when_ready(ready_win, make_input, chooser):
    w = ready_win
    assert w.footer_hint.text() == "필요: 원본 파일"
    w.step1.date_edit.setText("x")
    assert w.footer_hint.text() == "필요: 원본 파일, 기준일"
    chooser.answers["source"].append(str(make_input(n=2)))
    w.step1.pick_button.click()
    w.step1.date_edit.setText("2099.10.08")
    assert w.footer_hint.text() == "" and w.next_button.isEnabled()


def test_footer_names_template_and_policy_when_unconfigured(win):
    assert win.footer_hint.text() == "필요: 원본 파일, 저장 폴더, 템플릿, 정책 파일"


def test_footer_hint_is_hidden_on_other_steps(ready_win, make_input, chooser):
    chooser.answers["source"].append(str(make_input(n=2)))
    ready_win.step1.pick_button.click()
    ready_win.next_button.click()
    assert "필요:" not in ready_win.footer_hint.text()                       # Step 1 의 '필요: …' 안내는 Step 2 에 남지 않는다


def test_file_icon_says_xlsx(win):
    assert any(x.text() == "XLSX" for x in win.step1.findChildren(QLabel))


# ---------- 추가 회귀: 선택 이후 파일이 바뀌면 다음 단계로 넘어가지 않는다 ----------
def test_next_click_rechecks_and_blocks_when_file_was_replaced_after_success(ready_win, make_input, chooser):
    w = ready_win
    src = make_input(n=2)
    chooser.answers["source"].append(str(src))
    w.step1.pick_button.click()
    assert w.next_button.isEnabled()
    src.write_bytes(b"replaced by something else")           # 검사 뒤 같은 경로의 내용이 바뀜
    w.next_button.click()
    assert w.navigator.current == Step.FILE and not w.next_button.isEnabled()
    assert w.step1.source_badge.property("badge") == "error" and "손상" in w.step1.source_message.text()


def test_next_click_blocks_when_file_was_deleted_after_success(ready_win, make_input, chooser):
    w = ready_win
    src = make_input(n=2)
    chooser.answers["source"].append(str(src))
    w.step1.pick_button.click()
    src.unlink()
    w.next_button.click()
    assert w.navigator.current == Step.FILE and "찾을 수 없습니다" in w.step1.source_message.text() and w.footer_hint.text() == "필요: 원본 파일"


def test_next_click_does_not_wait_for_nor_skip_pending_checks(qapp, make_context, ready_settings, make_input):
    runner = ManualRunner()
    w, ctx = make_window(make_context, runner=runner, settings=ready_settings)
    w.step1.model.set_source(make_input(n=2))
    assert not w.next_button.isEnabled()                     # 검사가 끝나기 전에는 눌 수 없다
    w.next_button.click()
    assert w.navigator.current == Step.FILE
    runner.run_all()
    assert w.next_button.isEnabled()
    w.close()


def test_late_result_after_program_switch_does_not_enable_next(qapp, make_context, ready_settings, make_input):
    runner = ManualRunner()
    w, ctx = make_window(make_context, runner=runner, settings=ready_settings)
    runner.run_all()
    w.step1.model.set_source(make_input(n=2))
    w.step1.program_combo.setCurrentIndex(2)                 # 검사 중에 사업 전환
    runner.run_all()
    assert w.step1.model.paths["source"] is None and not w.next_button.isEnabled() and w.step1.source_badge.isHidden()
    w.close()


# ---------- 저장 폴더: 사전 확인일 뿐 보장하지 않는다 ----------
def test_unwritable_looking_folder_shows_reference_note_and_does_not_block(ready_win, make_input, chooser, monkeypatch):
    monkeypatch.setattr(v.os, "access", lambda p, mode: False)
    chooser.answers["source"].append(str(make_input(n=2)))
    ready_win.step1.pick_button.click()
    ready_win.step1.model.set_out_dir(ready_win.step1.model.paths["out_dir"])
    msg = ready_win.step1.out_dir_message.text()
    assert ready_win.next_button.isEnabled() and "참고용" in msg and "변환할 때 확인" in msg


def test_folder_message_never_promises_saving(ready_win):
    msg = ready_win.step1.out_dir_message.text()
    assert "변환할 때 확인" in msg and "저장할 수 있습니다" not in msg and "쓰기 가능" not in msg


# ---------- 설정 저장 실패 안내는 실제 상태를 따른다 ----------
def test_persist_failure_notice_appears_on_program_switch_and_clears_after_a_successful_save(qapp, make_context, ready_settings, monkeypatch):
    w, ctx = make_window(make_context, settings=ready_settings)
    real = us.os.replace
    monkeypatch.setattr(us.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    w.step1.program_combo.setCurrentIndex(1)
    assert not w.step1.notice.isHidden() and "저장하지 못" in w.step1.notice_label.text()
    monkeypatch.setattr(us.os, "replace", real)
    w.step1.program_combo.setCurrentIndex(0)
    assert w.step1.notice.isHidden()
    assert us.load(ctx.store.path).settings == ctx.store.settings                        # 저장 상태 = 세션 상태
    w.close()
