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


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "--one":
        _one(Path(argv[2]), float(argv[3]))
        return 0
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for scale in SCALES:
        env = {**os.environ, "QT_SCALE_FACTOR": str(scale), "QT_QPA_PLATFORM": "offscreen"}
        subprocess.run([sys.executable, __file__, "--one", str(out), str(scale)], env=env, check=True)
    print("saved:", ", ".join(sorted(p.name for p in out.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
