"""개발용 컴포넌트 갤러리와 진입점(--smoke)."""
import pytest

PySide6 = pytest.importorskip("PySide6")

from scholarship_payment.ui import __main__ as entry  # noqa: E402
from scholarship_payment.ui.gallery import build_gallery  # noqa: E402
from scholarship_payment.ui.widgets import AppButton, Badge, Card, StepperBar  # noqa: E402


def test_gallery_shows_every_component_variant(qapp):
    g = build_gallery()
    assert {b.property("variant") for b in g.findChildren(AppButton)} >= {"primary", "secondary", "destructive"}
    assert {b.property("badge") for b in g.findChildren(Badge)} >= {"verified", "caution", "error", "info", "neutral"}
    assert g.findChildren(Card) and g.findChildren(StepperBar)
    assert any(not b.isEnabled() for b in g.findChildren(AppButton))


def test_smoke_entry_returns_zero_without_blocking(qapp, capsys):
    assert entry.main(["--smoke"]) == 0
    assert "ui smoke ok" in capsys.readouterr().out


def test_gallery_option_smoke(qapp, capsys):
    assert entry.main(["--smoke", "--gallery"]) == 0


def test_unhandled_exception_output_has_type_only_no_message_or_path(qapp, capsys, monkeypatch):
    import sys
    monkeypatch.delenv("SCHOLARSHIP_UI_DEBUG", raising=False)
    original = sys.excepthook
    try:
        entry.install_safe_excepthook()
        try:
            raise OSError("C:\\사용자\\홍길동\\원본파일.xlsx 접근 거부")
        except OSError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = original
    err = capsys.readouterr().err
    assert "OSError" in err and "홍길동" not in err and "원본파일" not in err and "Traceback" not in err
