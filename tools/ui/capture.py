"""개발 도구: 새 화면(Step 1·고급 설정·정책 만들기)을 offscreen 으로 그려 100/125/150% 배율 PNG 로 저장한다(화면 확인용, 커밋 대상 아님).
사용: .venv/bin/python tools/ui/capture.py <출력 폴더>   (출력은 private/ 또는 스크래치 폴더에만 둔다)
입력 파일·템플릿·정책은 모두 합성 데이터이며 임시 폴더에서 만들고 끝나면 지운다. 설정 파일도 임시 폴더를 쓴다(실제 사용자 설정을 건드리지 않음).
배율은 QT_SCALE_FACTOR 로 바꾸므로 배율마다 별도 프로세스로 실행한다.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

SCALES = (1.0, 1.25, 1.5)
ROOT = Path(__file__).resolve().parents[2]


def _synthetic():
    spec = importlib.util.spec_from_file_location("make_synthetic", ROOT / "tools" / "synthetic" / "make_synthetic.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(out_dir: Path, scale: float) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from scholarship_payment.config.policy_builder import make_policy_file
    from scholarship_payment.config.user_settings import UserSettings
    from scholarship_payment.ui.context import AppContext
    from scholarship_payment.ui.main_window import MainWindow
    from scholarship_payment.ui.runner import InlineRunner
    from scholarship_payment.ui.state import SettingsStore
    from scholarship_payment.ui.theme import apply_theme

    class Pick:
        def __init__(self):
            self.answers = {}

        def __getattr__(self, name):
            return lambda *a, **k: None

    tag = f"{int(scale * 100)}"
    app = QApplication([])
    apply_theme(app)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        template = tmp / "synthetic_template.xlsx"            # 저장소·사용자 홈 경로가 캡처에 나오지 않게 임시 폴더로 복사한다
        template.write_bytes((ROOT / "templates" / "synthetic_payment_template.xlsx").read_bytes())
        values = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
        policy = make_policy_file(template, values, tmp / "policy_daechung.json", "daechung")
        src = tmp / "synthetic_monthly_approval.xlsx"
        _synthetic().build_input(5, "numeric").save(src)
        out = tmp / "결과"
        out.mkdir()

        def window(settings=None, size=None):
            store = SettingsStore(tmp / f"cfg_{len(list(tmp.iterdir()))}" / "settings.json")
            if settings:
                store.commit(settings)
            ctx = AppContext(store=store, runner=InlineRunner(), chooser=Pick(), today=lambda: date(2099, 10, 7), default_dirs=[])
            w = MainWindow(available=size or QSize(1920, 1080), context=ctx)
            w.show()
            app.processEvents()
            return w

        ready = UserSettings(last_program="daechung").with_paths("daechung", template_path=str(template), policy_path=str(policy), out_dir=str(out))

        def save(widget, name):
            app.processEvents()
            widget.grab().save(str(out_dir / f"{name}_{tag}.png"))

        w = window()
        save(w, "step1_empty")
        w.close()

        w = window(ready)
        w.step1.model.set_source(str(src))
        save(w, "step1_ready")
        w.step1.drop_zone.setProperty("state", "active")
        w.step1.drop_zone.style().unpolish(w.step1.drop_zone)
        w.step1.drop_zone.style().polish(w.step1.drop_zone)
        save(w, "step1_drag_active")
        w.close()

        w = window(ready)
        bad = tmp / "bad.xlsx"
        bad.write_bytes(b"not a zip")
        w.step1.model.set_source(str(bad))
        w.step1.date_edit.setText("2099-10-07")
        save(w, "step1_errors")
        w.close()

        w = window(ready, QSize(910, 512))              # 1366x768 노트북 150% 배율에 해당하는 가용 영역
        w.step1.model.set_source(str(src))
        save(w, "step1_small_screen")
        w.close()

        w = window(ready)
        dlg = w.step1.build_settings_dialog()
        dlg.show()
        save(dlg, "settings_dialog")
        dlg.tabs.set_current("ai")
        dlg.tabs.changed.emit("ai")
        save(dlg, "settings_dialog_ai_empty")
        dlg.cancel_button.click()

        dlg = w.step1.build_settings_dialog()
        dlg.draft.set_path("daechung", "policy_path", str(tmp / "missing.json"))
        dlg.show()
        save(dlg, "settings_dialog_error")
        wiz = w.step1.build_settings_dialog().build_wizard()
        wiz.show()
        save(wiz, "policy_wizard")
        wiz.close()
        dlg.cancel_button.click()
        w.close()


def _step2(out_dir: Path, scale: float) -> None:
    """Step 2(읽기 전용 미리보기)의 상태별 캡처. 모든 입력은 합성 데이터다."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from msoffcrypto.format.ooxml import OOXMLFile
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from scholarship_payment.config.policy_builder import make_policy_file
    from scholarship_payment.config.user_settings import UserSettings
    from scholarship_payment.ui.context import AppContext
    from scholarship_payment.ui.main_window import MainWindow
    from scholarship_payment.ui.runner import InlineRunner, ManualRunner
    from scholarship_payment.ui.state import SettingsStore
    from scholarship_payment.ui.theme import apply_theme

    tag = f"{int(scale * 100)}"
    app = QApplication([])
    apply_theme(app)
    mk = _synthetic()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        template = tmp / "synthetic_template.xlsx"
        template.write_bytes((ROOT / "templates" / "synthetic_payment_template.xlsx").read_bytes())
        values = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
        policy = make_policy_file(template, values, tmp / "policy_daechung.json", "daechung")
        out = tmp / "결과"
        out.mkdir()
        settings = UserSettings(last_program="daechung").with_paths("daechung", template_path=str(template), policy_path=str(policy), out_dir=str(out))
        n = {"i": 0}

        def src(name, rows=5, extra=(), mutate=None):
            wb = mk.build_input(rows, "numeric", extra)
            if mutate:
                mutate(wb.active)
            p = tmp / name
            wb.save(p)
            return p

        class NoPick:
            def __getattr__(self, name):
                return lambda *a, **k: None

        def window(runner=None):
            n["i"] += 1
            store = SettingsStore(tmp / f"cfg{n['i']}" / "settings.json")
            store.commit(settings)
            w = MainWindow(available=QSize(1920, 1080), context=AppContext(store=store, runner=runner or InlineRunner(), chooser=NoPick(), today=lambda: date(2099, 10, 7), default_dirs=[]))
            w.show()
            return w

        def go(w, path):
            w.step1.model.set_source(str(path))
            if hasattr(w.context.runner, "run_all"):
                w.context.runner.run_all()
            w.next_button.click()
            app.processEvents()

        def save(w, name):
            app.processEvents()
            w.grab().save(str(out_dir / f"step2_{name}_{tag}.png"))
            w.close()

        w = window()
        go(w, src("ok.xlsx"))
        save(w, "ready")
        w = window()
        go(w, src("carry.xlsx", 4, ((2, 480, "9999년08월"), (3, 90, "9999년08월"))))
        save(w, "ready_with_notes")
        w = window()
        go(w, src("dup.xlsx", 5, mutate=lambda ws: ws.__setitem__("F7", ws["F5"].value)))
        save(w, "blocking_error")
        w = window()
        go(w, src("bank.xlsx", 3, mutate=lambda ws: [ws.__setitem__(f"T{r}", "표에없는가상은행") for r in (3, 4)]))
        save(w, "bank_missing")
        enc = tmp / "enc.xlsx"
        with open(src("plain.xlsx", 3), "rb") as f, open(enc, "wb") as o:
            OOXMLFile(f).encrypt("가짜-pw", o)
        w = window()
        go(w, enc)
        save(w, "password")
        w = window()
        go(w, enc)
        w.step2.password_edit.setText("틀림")
        w.step2.password_ok.click()
        save(w, "password_wrong_once")
        w = window()
        go(w, enc)
        for i in range(3):
            w.step2.password_edit.setText(f"틀림{i}")
            w.step2.password_ok.click()
        save(w, "password_locked")
        r = ManualRunner()
        w = window(r)
        r.run_all()
        go(w, src("load.xlsx"))
        save(w, "loading")
        w = window()
        file = src("changed.xlsx")
        go(w, file)
        data = bytearray(file.read_bytes())
        data[-1] ^= 1
        file.write_bytes(bytes(data))
        w.step2.refresh_freshness()
        save(w, "invalidated")
        w = window()
        w.resize(910, 512)
        go(w, src("small.xlsx", 4, ((2, 480, "9999년08월"),)))
        save(w, "small_screen")


def _step3(out_dir: Path, scale: float) -> None:
    """Step 3(생성·결과)의 상태별 캡처. 모든 입력은 합성 데이터이고 저장 폴더도 임시 폴더다."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import dataclasses
    from datetime import datetime

    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from openpyxl import load_workbook
    from scholarship_payment.app import convert as conv
    from scholarship_payment.app import workflow as wf
    from scholarship_payment.config.policy_builder import make_policy_file
    from scholarship_payment.config.user_settings import UserSettings
    from scholarship_payment.ui.context import AppContext
    from scholarship_payment.ui.main_window import MainWindow
    from scholarship_payment.ui.runner import InlineRunner, ManualRunner
    from scholarship_payment.ui.state import SettingsStore
    from scholarship_payment.ui.theme import apply_theme

    tag = f"{int(scale * 100)}"
    app = QApplication([])
    apply_theme(app)
    mk = _synthetic()

    class Acts:
        def open_folder(self, p):
            return True

        def copy_text(self, t):
            return True

    class NoPick:
        def __getattr__(self, name):
            return lambda *a, **k: None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        good_tpl = tmp / "synthetic_template.xlsx"
        good_tpl.write_bytes((ROOT / "templates" / "synthetic_payment_template.xlsx").read_bytes())
        bad_tpl = tmp / "bad_layout_template.xlsx"
        wb = load_workbook(good_tpl)
        del wb["WINS"]
        wb.save(bad_tpl)
        values = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
        policy = make_policy_file(good_tpl, values, tmp / "policy_daechung.json", "daechung")
        n = {"i": 0}

        def src(name, rows=5, extra=()):
            p = tmp / name
            mk.build_input(rows, "numeric", extra).save(p)
            return p

        def window(template=good_tpl, gen_runner=None):
            n["i"] += 1
            out = tmp / f"결과{n['i']}"
            out.mkdir()
            store = SettingsStore(tmp / f"cfg{n['i']}" / "settings.json")
            store.commit(UserSettings(last_program="daechung").with_paths("daechung", template_path=str(template), policy_path=str(policy), out_dir=str(out)))
            ctx = AppContext(store=store, runner=InlineRunner(), chooser=NoPick(), today=lambda: date(2099, 10, 7), default_dirs=[], generation_runner=gen_runner, actions=Acts(),
                             now=lambda: datetime(2099, 10, 7, 12, 34, 56))
            w = MainWindow(available=QSize(1920, 1080), context=ctx)
            w.show()
            return w, out

        def go(w, path):
            w.step1.model.set_source(str(path))
            w.next_button.click()
            app.processEvents()
            w.next_button.click()                      # 지급명단 생성
            app.processEvents()

        def save(w, name):
            app.processEvents()
            w.grab().save(str(out_dir / f"step3_{name}_{tag}.png"))
            w.generation.close()
            w.close()

        w, out = window()
        go(w, src("ok.xlsx"))
        save(w, "success")
        w, out = window()
        real = conv.finish
        wf.finish = lambda p, d: dataclasses.replace(real(p, d), warnings=(conv.ValidationError("SPLIT_AMOUNT_MISMATCH", "grant_interest", 4),))
        go(w, src("warn.xlsx", 4, ((2, 480, "9999년08월"), (3, 90, "9999년08월"))))
        wf.finish = real
        save(w, "success_with_warnings_and_notes")
        w, out = window()
        (out / "지급명단_DAECHUNG_9999_09.xlsx").write_bytes(b"existing")
        (out / ".~old_run.xlsx").write_bytes(b"leftover")
        go(w, src("same_name.xlsx"))
        save(w, "same_name_and_leftover")
        r = ManualRunner()
        w, out = window(gen_runner=r)
        go(w, src("busy.xlsx"))
        w.closeEvent(__import__("PySide6.QtGui", fromlist=["QCloseEvent"]).QCloseEvent())
        save(w, "generating_close_blocked")
        w, out = window(template=bad_tpl)
        go(w, src("badtpl.xlsx"))
        save(w, "failure_template")
        w, out = window()
        w.step1.model.set_source(str(src("folder.xlsx")))
        w.next_button.click()
        out.rmdir()
        w.next_button.click()
        save(w, "failure_folder")
        w, out = window()
        conv.verify_output, keep = (lambda *a, **k: (_ for _ in ()).throw(conv.ValidationFailed([conv.ValidationError("OUTPUT_TOTAL_MISMATCH", "amount", 9)]))), conv.verify_output
        go(w, src("verify.xlsx"))
        conv.verify_output = keep
        save(w, "failure_verify")
        w, out = window()
        w.resize(910, 512)
        go(w, src("small.xlsx", 4, ((2, 480, "9999년08월"),)))
        save(w, "small_screen")


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "--step3":
        _step3(Path(argv[2]), float(argv[3]))
        return 0
    if len(argv) >= 4 and argv[1] == "--step2":
        _step2(Path(argv[2]), float(argv[3]))
        return 0
    if len(argv) >= 4 and argv[1] == "--one":
        _one(Path(argv[2]), float(argv[3]))
        return 0
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for scale in SCALES:
        env = {**os.environ, "QT_SCALE_FACTOR": str(scale), "QT_QPA_PLATFORM": "offscreen"}
        subprocess.run([sys.executable, __file__, "--one", str(out), str(scale)], env=env, check=True)
        subprocess.run([sys.executable, __file__, "--step2", str(out), str(scale)], env=env, check=True)
        subprocess.run([sys.executable, __file__, "--step3", str(out), str(scale)], env=env, check=True)
    print("saved:", ", ".join(sorted(p.name for p in out.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
