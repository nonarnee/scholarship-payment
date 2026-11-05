"""정식 PySide6 진입점(`ui/app_main.py`, `packaging/run_gui_qt.py`): 사용자용 기능만 노출하고 개발 모드(--gallery, --synthetic-e2e-smoke)는 실행되지 않는다."""
import subprocess
import sys
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")

import scholarship_payment  # noqa: E402
from scholarship_payment.ui import app_main  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def run_py(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=ROOT, env={"QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(ROOT / "src"), "PATH": ""}, timeout=120)


def test_smoke_runs_without_blocking_and_reports_ok(qapp, capsys, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    assert app_main.main(["--smoke"]) == 0
    assert "ui smoke ok" in capsys.readouterr().out


def test_smoke_fails_when_a_required_module_is_missing(qapp, capsys, monkeypatch):
    from scholarship_payment.ui import runtime_check
    monkeypatch.setattr(runtime_check, "REQUIRED_MODULES", ("scholarship_payment.not_a_real_module",))
    assert app_main.main(["--smoke"]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_version_flag_prints_versions_and_exits_without_creating_a_window(capsys):
    assert app_main.main(["--version"]) == 0
    out = capsys.readouterr().out
    assert scholarship_payment.__version__ in out and "PySide6" in out and "Qt" in out and "openpyxl" in out and "msoffcrypto" in out and "Python" in out


@pytest.mark.parametrize("flag", [["--gallery"], ["--synthetic-e2e-smoke"], ["--synthetic-e2e-smoke", "--work-dir", "x", "--result-json", "y"], ["--work-dir", "x"], ["--result-json", "y"], ["--unknown"], ["--smoke", "--gallery"]])
def test_development_flags_and_unknown_flags_are_rejected_with_exit_2(flag, tmp_path, capsys):
    before = sorted(p.name for p in tmp_path.iterdir())
    assert app_main.main(flag) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == before                     # 아무 것도 실행·생성하지 않는다
    out = capsys.readouterr()
    assert "ui smoke ok" not in out.out


def test_abbreviated_flags_are_not_accepted():
    assert app_main.main(["--smo"]) == 2 and app_main.main(["--vers"]) == 2


def test_production_entry_does_not_import_development_modules_or_tkinter():
    r = run_py("import sys\nfrom scholarship_payment.ui import app_main\n"
               "bad=[m for m in ('scholarship_payment.ui.gallery','scholarship_payment.ui.e2e_smoke','scholarship_payment.ui.__main__','tkinter','scholarship_payment.gui.app') if m in sys.modules]\n"
               "print('BAD', bad)")
    assert r.returncode == 0 and r.stdout.strip() == "BAD []", r.stderr


def test_dev_flags_do_not_even_load_dev_modules_in_the_production_entry():
    r = run_py("import sys\nfrom scholarship_payment.ui import app_main\n"
               "code=app_main.main(['--gallery'])\n"
               "bad=[m for m in ('scholarship_payment.ui.gallery','scholarship_payment.ui.e2e_smoke') if m in sys.modules]\nprint(code, bad)")
    assert r.stdout.strip() == "2 []", r.stderr


def test_pyinstaller_entry_file_uses_only_the_production_main():
    text = (ROOT / "packaging" / "run_gui_qt.py").read_text(encoding="utf-8")
    assert "scholarship_payment.ui.app_main" in text and "sys.exit(main())" in text
    for forbidden in ("gallery", "e2e", "ui.__main__", "gui.app", "tkinter"):
        assert forbidden not in text


def test_the_development_entry_keeps_its_development_flags(qapp, tmp_path):
    from scholarship_payment.ui import __main__ as dev
    assert dev.main(["--smoke", "--gallery"]) == 0                                    # 개발용 진입점은 그대로(갤러리 smoke)
    assert callable(dev.install_safe_excepthook)


def test_production_main_installs_the_safe_excepthook(qapp, monkeypatch, capsys):
    original = sys.excepthook
    monkeypatch.setattr(sys, "excepthook", original)
    app_main.main(["--smoke"])
    try:
        raise OSError("C:\\사용자\\홍길동\\원본.xlsx")
    except OSError:
        sys.excepthook(*sys.exc_info())
    err = capsys.readouterr().err
    assert "OSError" in err and "홍길동" not in err
    sys.excepthook = original


def test_normal_start_builds_the_main_window_without_dev_behaviour(qapp):
    window = app_main.create_window()
    assert window.windowTitle().endswith(scholarship_payment.__version__)
    assert not [w for w in window.findChildren(type(window.next_button)) if "갤러리" in w.text()]
    window.close()
