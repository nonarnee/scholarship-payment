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
