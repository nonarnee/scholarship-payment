"""메인 창 뼈대: 크기·네이티브 제목 표시줄·네비게이션 연동·초점·개인정보 없음."""
import re
import sys

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QLabel, QScrollArea, QWidget  # noqa: E402

import scholarship_payment  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402
from scholarship_payment.ui.navigation import Step  # noqa: E402


@pytest.fixture
def win(qapp):
    w = MainWindow(available=QSize(1920, 1080))
    w.show()
    yield w
    w.close()


def test_default_and_minimum_size(win):
    assert (win.width(), win.height()) == (900, 650) and (win.minimumWidth(), win.minimumHeight()) == (800, 600)


def test_small_screen_clamps_height_to_available_area(qapp):
    w = MainWindow(available=QSize(910, 470))
    assert (w.width(), w.height()) == (900, 470) and w.minimumHeight() == 470


def test_uses_native_title_bar_and_version_title(win):
    assert not (win.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert win.windowTitle() == f"장학금 지급명단 변환 v{scholarship_payment.__version__}"


def test_body_is_scrollable(win):
    assert win.findChild(QScrollArea) is not None and win.findChild(QScrollArea).widgetResizable()


def test_status_bar_shows_version_and_network_notice(win):
    texts = [w.text() for w in win.statusBar().findChildren(QLabel)]
    assert f"v{scholarship_payment.__version__}" in texts and any("네트워크" in t for t in texts)


def test_footer_buttons_follow_navigator(win):
    assert not win.back_button.isEnabled() and not win.next_button.isEnabled()
    win.set_step_ready(Step.FILE, True)
    assert win.next_button.isEnabled()
    win.next_button.click()
    assert win.navigator.current is Step.REVIEW and win.back_button.isEnabled() and not win.next_button.isEnabled()
    assert win.stack.currentIndex() == 1 and win.stepper.state_of(0) == "done" and win.stepper.state_of(1) == "current"
    win.back_button.click()
    assert win.navigator.current is Step.FILE and win.stack.currentIndex() == 0


def test_tab_order_reaches_both_footer_buttons(win):
    win.set_step_ready(Step.FILE, True)
    win.next_button.click()
    win.set_step_ready(Step.REVIEW, True)
    chain, w = [], win.back_button
    for _ in range(40):
        chain.append(w)
        w = w.nextInFocusChain()
    assert win.next_button in chain and all(b.focusPolicy() == Qt.FocusPolicy.StrongFocus for b in (win.back_button, win.next_button))


def test_focus_style_exists_in_application_stylesheet(win, qapp):
    assert "2px solid" in qapp.styleSheet() and ":focus" in qapp.styleSheet()


def test_window_texts_contain_no_personal_data(win):
    texts = [w.text() for w in win.findChildren(QLabel)] + [b.text() for b in win.findChildren(QAbstractButton)]
    assert texts and not any(re.search(r"\d{8}|\*\*", t) for t in texts)


def test_grab_renders_pixels(win):
    img = win.grab()
    assert not img.isNull() and img.width() >= 900 and img.toImage().pixelColor(5, 5).isValid()


def test_no_network_modules_are_imported(win):
    assert not [m for m in sys.modules if m.startswith("PySide6.QtNetwork")]


def test_placeholder_pages_are_widgets_for_each_step(win):
    assert win.stack.count() == 3 and all(isinstance(win.stack.widget(i), QWidget) for i in range(3))
