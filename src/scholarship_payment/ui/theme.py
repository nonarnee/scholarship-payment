"""디자인 토큰과 스타일시트. 값의 출처는 Stitch `DESIGN.md`(색·타이포·간격·모서리). 글꼴은 Windows 시스템 글꼴만 쓴다(동봉 없음).
Qt 스타일시트로 표현할 수 없는 그림자·그라디언트는 쓰지 않고, 1px 테두리와 색 층으로 구분한다.
"""
from __future__ import annotations

COLORS = {
    "primary": "#0067C0", "primary_pressed": "#005A9E", "on_primary": "#FFFFFF",
    "success": "#107C41", "success_bg": "#DFF6DD",
    "warning": "#C15C00", "warning_bg": "#FFF4CE", "warning_strong": "#D83B01",
    "error": "#A80000", "error_bg": "#FDE7E9",
    "info_bg": "#EDF5FD",
    "text": "#202020", "text_secondary": "#5A5A5A", "text_disabled": "#9A9A9A",
    "window": "#F3F3F3", "card": "#FFFFFF", "border": "#E5E5E5", "stroke": "#D1D1D1", "stroke_hover": "#A6A6A6",
    "table_header": "#F9F9F9", "surface_alt": "#FAFAFA", "button_hover": "#F5F5F5", "drop_active_bg": "#EDF5FD",
    "disabled_bg": "#F0F0F0",
}
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADIUS = {"control": 4, "card": 8}
# (px 크기, 굵기). 줄 높이는 한글 받침이 잘리지 않도록 135~145%를 쓴다(Qt 는 위젯 높이로 확보).
TYPE = {
    "headline_lg": (20, 600), "headline_md": (16, 600), "headline_sm": (14, 600),
    "body_lg": (14, 400), "body_md": (13, 400), "body_sm": (12, 400),
    "label_lg": (13, 500), "label_md": (12, 500), "label_sm": (11, 500),
}
FONT_FAMILIES = ("Malgun Gothic", "Segoe UI")
DEFAULT_WINDOW = (900, 650)
MIN_WINDOW = (800, 600)
CONTROL_HEIGHT = 32
FOOTER_HEIGHT = 40
STEPPER_HEIGHT = 48
BEAD_SIZE = 24


def fit_window_size(avail_w: int, avail_h: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """화면 가용 영역보다 크지 않은 (기본 크기, 최소 크기). 1366x768 노트북 150% 배율처럼 작은 화면을 고려한다."""
    default = (min(DEFAULT_WINDOW[0], avail_w), min(DEFAULT_WINDOW[1], avail_h))
    minimum = (min(MIN_WINDOW[0], avail_w), min(MIN_WINDOW[1], avail_h))
    return default, minimum


def _font(key: str) -> str:
    size, weight = TYPE[key]
    return f"font-size: {size}px; font-weight: {weight};"


def build_stylesheet() -> str:
    c, r = COLORS, RADIUS
    families = ", ".join(f'"{f}"' for f in FONT_FAMILIES)
    h = CONTROL_HEIGHT
    focus_ring = f"border: 2px solid {c['primary']};"
    css = f"""
* {{ font-family: {families}; color: {c['text']}; }}
QMainWindow, QWidget#AppRoot {{ background: {c['window']}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QLabel {{ background: transparent; {_font('body_md')} }}
QLabel[role="headline"] {{ {_font('headline_lg')} }}
QLabel[role="section"] {{ {_font('headline_md')} }}
QLabel[role="secondary"] {{ color: {c['text_secondary']}; {_font('body_sm')} }}

QFrame#Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: {r['card']}px; }}
QFrame#TopBand, QFrame#FooterBar {{ background: {c['card']}; border: none; }}
QFrame#TopBand {{ border-bottom: 1px solid {c['border']}; }}
QFrame#FooterBar {{ border-top: 1px solid {c['border']}; }}
QStatusBar {{ background: {c['window']}; border-top: 1px solid {c['border']}; }}
QStatusBar QLabel {{ color: {c['text_secondary']}; padding: 2px {SPACING['md']}px; {_font('body_sm')} }}

QPushButton {{ min-height: {h}px; padding: 0 {SPACING['lg']}px; border-radius: {r['control']}px; {_font('label_lg')} }}
QPushButton[variant="primary"] {{ background: {c['primary']}; color: {c['on_primary']}; border: 1px solid {c['primary']}; }}
QPushButton[variant="primary"]:hover {{ background: {c['primary_pressed']}; border-color: {c['primary_pressed']}; }}
QPushButton[variant="primary"]:pressed {{ background: {c['primary_pressed']}; }}
QPushButton[variant="primary"]:focus {{ border: 2px solid {c['text']}; }}
QPushButton[variant="primary"]:disabled {{ background: {c['disabled_bg']}; color: {c['text_disabled']}; border: 1px solid {c['border']}; }}
QPushButton[variant="secondary"] {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['stroke']}; }}
QPushButton[variant="secondary"]:hover {{ background: {c['button_hover']}; border-color: {c['stroke_hover']}; }}
QPushButton[variant="secondary"]:pressed {{ background: {c['border']}; }}
QPushButton[variant="secondary"]:focus {{ {focus_ring} }}
QPushButton[variant="secondary"]:disabled {{ background: {c['disabled_bg']}; color: {c['text_disabled']}; border: 1px solid {c['border']}; }}
QPushButton[variant="destructive"] {{ background: {c['card']}; color: {c['error']}; border: 1px solid {c['error']}; }}
QPushButton[variant="destructive"]:hover {{ background: {c['error_bg']}; }}
QPushButton[variant="destructive"]:pressed {{ background: {c['error']}; color: {c['on_primary']}; }}
QPushButton[variant="destructive"]:focus {{ border: 2px solid {c['error']}; }}
QPushButton[variant="destructive"]:disabled {{ background: {c['disabled_bg']}; color: {c['text_disabled']}; border: 1px solid {c['border']}; }}

QPushButton[variant="link"] {{ background: transparent; color: {c['primary']}; border: 1px solid transparent; padding: 0 {SPACING['sm']}px; min-height: 24px; {_font('label_md')} }}
QPushButton[variant="link"]:hover {{ background: {c['info_bg']}; }}
QPushButton[variant="link"]:focus {{ {focus_ring} }}
QPushButton[variant="link"]:disabled {{ color: {c['text_disabled']}; }}
QPushButton[seg="true"] {{ background: transparent; color: {c['text_secondary']}; border: 1px solid transparent; min-height: {h - 4}px; {_font('label_md')} }}
QPushButton[seg="true"]:hover {{ background: {c['button_hover']}; }}
QPushButton[seg="true"]:checked {{ background: {c['primary']}; color: {c['on_primary']}; }}
QPushButton[seg="true"]:focus {{ border: 2px solid {c['text']}; }}
QFrame#SegTabs {{ background: {c['surface_alt']}; border: 1px solid {c['border']}; border-radius: {r['card']}px; }}
QFrame#DropZone {{ background: {c['surface_alt']}; border: 1px dashed {c['stroke']}; border-radius: {r['card']}px; }}
QFrame#DropZone[state="active"] {{ background: {c['drop_active_bg']}; border: 1px solid {c['primary']}; }}
QFrame#DropZone[state="reject"] {{ background: {c['error_bg']}; border: 1px solid {c['error']}; }}
QFrame#Panel {{ background: {c['surface_alt']}; border: 1px solid {c['border']}; border-radius: {r['card']}px; }}
QFrame#Strip {{ background: {c['table_header']}; border: 1px solid {c['border']}; border-radius: {r['card']}px; }}
QFrame#Notice {{ background: {c['warning_bg']}; border: 1px solid {c['warning']}; border-radius: {r['control']}px; }}
QFrame#Notice QLabel {{ color: {c['warning']}; }}
QFrame#FileIcon {{ background: {c['success_bg']}; border-radius: {r['control']}px; }}
QLineEdit[role="path"] {{ background: {c['card']}; {_font('body_sm')} }}
QLabel[role="error"] {{ color: {c['error']}; {_font('body_sm')} }}
QLabel[role="hint"] {{ color: {c['text_secondary']}; {_font('label_sm')} }}
QLabel[role="icon"] {{ color: {c['success']}; {_font('label_sm')} }}
QLabel[role="filename"] {{ {_font('headline_sm')} }}
QDialog {{ background: {c['window']}; }}
QLineEdit, QComboBox {{ min-height: {h - 2}px; background: {c['card']}; border: 1px solid {c['stroke']}; border-radius: {r['control']}px; padding: 0 {SPACING['sm']}px; {_font('body_md')} }}
QLineEdit:hover, QComboBox:hover {{ border-color: {c['stroke_hover']}; }}
QLineEdit:focus, QComboBox:focus {{ {focus_ring} }}
QLineEdit:disabled, QComboBox:disabled {{ background: {c['disabled_bg']}; color: {c['text_disabled']}; }}

QLabel[badge] {{ border-radius: {r['control']}px; padding: 2px {SPACING['sm']}px; {_font('label_sm')} }}
QLabel[badge="verified"] {{ background: {c['success_bg']}; color: {c['success']}; }}
QLabel[badge="caution"] {{ background: {c['warning_bg']}; color: {c['warning']}; }}
QLabel[badge="error"] {{ background: {c['error_bg']}; color: {c['error']}; }}
QLabel[badge="info"] {{ background: {c['info_bg']}; color: {c['primary']}; }}
QLabel[badge="neutral"] {{ background: {c['border']}; color: {c['text_secondary']}; }}

QLabel[bead] {{ min-width: {BEAD_SIZE}px; max-width: {BEAD_SIZE}px; min-height: {BEAD_SIZE}px; max-height: {BEAD_SIZE}px; border-radius: {BEAD_SIZE // 2}px; qproperty-alignment: AlignCenter; {_font('label_md')} }}
QLabel[bead][state="current"] {{ background: {c['primary']}; color: {c['on_primary']}; }}
QLabel[bead][state="done"] {{ background: {c['success']}; color: {c['on_primary']}; }}
QLabel[bead][state="todo"] {{ background: {c['border']}; color: {c['text_secondary']}; }}
QLabel[stepLabel][state="current"] {{ color: {c['primary']}; {_font('headline_sm')} }}
QLabel[stepLabel][state="done"] {{ color: {c['text']}; {_font('body_lg')} }}
QLabel[stepLabel][state="todo"] {{ color: {c['text_secondary']}; {_font('body_lg')} }}
QLabel[stepSeparator] {{ color: {c['stroke']}; }}
"""
    return css


def apply_theme(app) -> None:
    """앱 전체 글꼴(Windows 시스템 글꼴 순서)과 스타일시트를 적용한다."""
    from PySide6.QtGui import QFont

    font = QFont()
    font.setFamilies(list(FONT_FAMILIES))
    font.setPixelSize(TYPE["body_md"][0])
    app.setFont(font)
    app.setStyleSheet(build_stylesheet())
