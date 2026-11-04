"""디자인 토큰이 Stitch DESIGN.md 의 값과 일치하는지, 스타일시트가 오류 없이 적용되는지 확인한다."""
import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402

from scholarship_payment.ui import theme  # noqa: E402


def test_colors_match_design_md():
    c = theme.COLORS
    assert (c["primary"], c["primary_pressed"], c["on_primary"]) == ("#0067C0", "#005A9E", "#FFFFFF")
    assert (c["success"], c["success_bg"]) == ("#107C41", "#DFF6DD")
    assert (c["warning"], c["warning_bg"], c["warning_strong"]) == ("#C15C00", "#FFF4CE", "#D83B01")
    assert (c["error"], c["error_bg"]) == ("#A80000", "#FDE7E9")
    assert (c["text"], c["text_secondary"]) == ("#202020", "#5A5A5A")
    assert (c["window"], c["card"], c["border"], c["stroke"], c["stroke_hover"]) == ("#F3F3F3", "#FFFFFF", "#E5E5E5", "#D1D1D1", "#A6A6A6")
    assert (c["table_header"], c["surface_alt"], c["button_hover"], c["drop_active_bg"]) == ("#F9F9F9", "#FAFAFA", "#F5F5F5", "#EDF5FD")


def test_spacing_radius_and_type_scale_match_design_md():
    assert theme.SPACING == {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
    assert theme.RADIUS == {"control": 4, "card": 8}
    assert {k: v[0] for k, v in theme.TYPE.items()} == {
        "headline_lg": 20, "headline_md": 16, "headline_sm": 14, "body_lg": 14, "body_md": 13, "body_sm": 12,
        "label_lg": 13, "label_md": 12, "label_sm": 11}
    assert theme.TYPE["headline_lg"][1] == 600 and theme.TYPE["body_md"][1] == 400 and theme.TYPE["label_lg"][1] == 500


def test_window_and_control_sizes_follow_design_md():
    assert theme.DEFAULT_WINDOW == (900, 650) and theme.MIN_WINDOW == (800, 600)
    assert theme.CONTROL_HEIGHT == 32 and theme.FOOTER_HEIGHT == 40 and theme.STEPPER_HEIGHT == 48


def test_font_stack_uses_windows_system_fonts_only():
    assert theme.FONT_FAMILIES == ("Malgun Gothic", "Segoe UI")        # 글꼴 동봉 없음(결정 5)


def test_stylesheet_covers_variants_states_and_focus():
    css = theme.build_stylesheet()
    for variant in ("primary", "secondary", "destructive"):
        assert f'variant="{variant}"' in css
    for kind in ("verified", "caution", "error", "info", "neutral"):
        assert f'badge="{kind}"' in css
    for state in ("current", "done", "todo"):
        assert f'state="{state}"' in css
    assert ":focus" in css and ":disabled" in css and ":hover" in css and ":pressed" in css
    assert "Malgun Gothic" in css and "#0067C0" in css


def test_stylesheet_applies_without_qt_warnings(qapp):
    seen = []
    old = qInstallMessageHandler(lambda mode, ctx, msg: seen.append((mode, msg)))
    try:
        qapp.setStyleSheet(theme.build_stylesheet())
    finally:
        qInstallMessageHandler(old)
    assert [m for mode, m in seen if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg) and "stylesheet" in m.lower()] == []


def test_apply_theme_sets_application_font(qapp):
    assert qapp.font().families()[0] == "Malgun Gothic" and qapp.font().pixelSize() == 13


def test_fit_window_size_clamps_to_small_screens():
    assert theme.fit_window_size(1920, 1080) == ((900, 650), (800, 600))
    assert theme.fit_window_size(910, 470) == ((900, 470), (800, 470))     # 150% 배율 1366x768: 높이는 화면에 맞춘다
    assert theme.fit_window_size(700, 500) == ((700, 500), (700, 500))
