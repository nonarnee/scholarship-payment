"""공통 위젯: 생성·상태·초점 정책."""
import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from scholarship_payment.ui.widgets import AppButton, Badge, Card, StepperBar  # noqa: E402


def test_card_has_object_name_and_body_layout(qapp):
    card = Card("제목")
    assert card.objectName() == "Card" and card.title_text() == "제목"
    assert card.body.contentsMargins().left() == 16


@pytest.mark.parametrize("kind", ["verified", "caution", "error", "info", "neutral"])
def test_badge_kinds(qapp, kind):
    b = Badge("텍스트", kind)
    assert b.property("badge") == kind and b.text() == "텍스트"
    b.set_kind("neutral")
    assert b.property("badge") == "neutral"


def test_badge_rejects_unknown_kind(qapp):
    with pytest.raises(ValueError):
        Badge("x", "bogus")


@pytest.mark.parametrize("variant", ["primary", "secondary", "destructive"])
def test_button_variants_are_keyboard_focusable_and_32px(qapp, variant):
    b = AppButton("확인", variant)
    assert b.property("variant") == variant and b.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert b.minimumHeight() == 32


def test_button_rejects_unknown_variant(qapp):
    with pytest.raises(ValueError):
        AppButton("x", "bogus")


def test_disabled_button_does_not_take_focus_or_clicks(qapp):
    b = AppButton("확인", "primary")
    hits = []
    b.clicked.connect(lambda: hits.append(1))
    b.setEnabled(False)
    b.click()
    assert hits == [] and not b.isEnabled()


def test_stepper_states_and_no_focus(qapp):
    s = StepperBar(["파일 선택", "지급내역 확인", "결과 생성"])
    s.set_state(current=1, done={0})
    assert [s.state_of(i) for i in range(3)] == ["done", "current", "todo"]
    assert s.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert all(w.focusPolicy() == Qt.FocusPolicy.NoFocus for w in s.findChildren(PySide6.QtWidgets.QLabel))
    assert s.label_texts() == ["파일 선택", "지급내역 확인", "결과 생성"]


def test_stepper_done_step_shows_check_and_others_show_numbers(qapp):
    s = StepperBar(["a", "b", "c"])
    s.set_state(current=2, done={0, 1})
    assert s.bead_texts() == ["✓", "✓", "3"]
