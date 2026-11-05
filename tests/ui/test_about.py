"""앱 정보 화면: 버전과 라이선스 안내. 실제로 로드된 라이브러리 버전만 보여 주고, 라이선스 준수가 끝났다고 주장하지 않는다."""
import sys
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel  # noqa: E402

import scholarship_payment  # noqa: E402
from scholarship_payment.ui import about  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402


def all_text(w):
    return " ".join(x.text() for x in w.findChildren(QLabel))


@pytest.fixture
def win(qapp, make_context):
    w = MainWindow(context=make_context())
    w.show()
    yield w
    w.close()


def test_about_button_is_in_the_status_bar_and_opens_a_dialog_without_changing_the_step(win):
    assert win.about_button.text() == "정보" and win.about_button.isVisible()
    from scholarship_payment.ui.navigation import Step
    d = win.build_about_dialog()
    assert d.windowTitle() == "정보" and win.navigator.current == Step.FILE


def test_dialog_shows_the_real_version_and_loaded_library_versions(win):
    import PySide6
    from PySide6.QtCore import qVersion
    d = win.build_about_dialog()
    t = all_text(d)
    assert scholarship_payment.__version__ in t and PySide6.__version__ in t and qVersion() in t and "Python" in t and "openpyxl" in t and "msoffcrypto" in t
    assert "배포 후보" in d.version_label.text() and "검증이 끝나지 않았" in d.version_label.text()          # rc 는 정식 배포가 아님을 밝힌다


def test_release_candidate_notice_disappears_for_a_final_version(win, monkeypatch):
    monkeypatch.setattr(about, "__version__", "1.0.0")
    assert "배포 후보" not in win.build_about_dialog().version_label.text()


def test_license_notice_names_qt_lgpl_and_points_to_the_licenses_folder_without_claiming_compliance(win):
    t = all_text(win.build_about_dialog())
    assert "Qt" in t and "LGPL" in t and "LICENSES" in t
    for claim in ("준수했", "문제 없", "법적으로", "보증", "승인됨", "허가됨"):
        assert claim not in t
    assert "라이선스" in t


def test_library_license_labels_come_from_installed_metadata_not_hardcoded_guesses(win):
    rows = {r.name: r for r in about.library_rows()}
    assert rows["PySide6"].license.startswith("LGPL-3.0") and rows["openpyxl"].license == "MIT"
    assert all(r.version and r.version != "" for r in rows.values())


def test_licenses_folder_button_is_disabled_outside_a_packaged_build_and_explains_why(win, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    d = win.build_about_dialog()
    assert not d.licenses_button.isEnabled() and "설치 폴더" in d.licenses_hint.text() and about.licenses_dir() is None


def test_licenses_folder_button_opens_the_folder_when_it_exists(qapp, make_context, tmp_path, monkeypatch):
    from conftest import FakeActions
    app_dir = tmp_path / "app"
    (app_dir / "LICENSES").mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "ScholarshipPayment-v0.3.0-rc.1.exe"))
    actions = FakeActions()
    w = MainWindow(context=make_context(actions=actions))
    d = w.build_about_dialog()
    assert d.licenses_button.isEnabled()
    d.licenses_button.click()
    assert actions.opened == [str(app_dir / "LICENSES")]
    actions.open_ok = False
    d.licenses_button.click()
    assert "열지 못했습니다" in d.licenses_hint.text()
    w.close()


def test_missing_licenses_folder_in_a_packaged_build_is_reported_not_hidden(qapp, make_context, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "x.exe"))
    w = MainWindow(context=make_context())
    d = w.build_about_dialog()
    assert not d.licenses_button.isEnabled() and "찾을 수 없습니다" in d.licenses_hint.text()
    w.close()


def test_about_dialog_contains_no_paths_or_personal_data(win):
    t = all_text(win.build_about_dialog())
    assert str(Path.home()) not in t and "@" not in t


def test_about_can_be_opened_while_generating_without_affecting_the_lock(qapp, make_context, ready_settings, make_input):
    from scholarship_payment.ui.runner import ManualRunner
    r = ManualRunner()
    w = MainWindow(context=make_context(settings=ready_settings, generation_runner=r))
    w.show()
    w.step1.model.set_source(make_input(n=3))
    w.next_button.click()
    w.next_button.click()
    assert w.generation.busy
    d = w.build_about_dialog()
    d.close_button.click()
    assert w.generation.busy and w.navigator.locked
    w.generation.close()
    w.close()
