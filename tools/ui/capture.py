"""개발 도구: 메인 창·갤러리를 offscreen 으로 그려 100/125/150% 배율 PNG 로 저장한다(화면 확인용, 커밋 대상 아님).
사용: .venv/bin/python tools/ui/capture.py <출력 폴더>   (출력은 private/ 또는 스크래치 폴더에만 둔다)
배율은 QT_SCALE_FACTOR 로 바꾸므로 배율마다 별도 프로세스로 실행한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCALES = (1.0, 1.25, 1.5)


def _one(out_dir: Path, scale: float) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from scholarship_payment.ui.gallery import build_gallery
    from scholarship_payment.ui.main_window import MainWindow
    from scholarship_payment.ui.navigation import Step
    from scholarship_payment.ui.theme import apply_theme

    app = QApplication([])
    apply_theme(app)
    tag = f"{int(scale * 100)}"
    window = MainWindow(available=QSize(1920, 1080))
    window.show()
    app.processEvents()
    window.grab().save(str(out_dir / f"main_step1_{tag}.png"))
    window.set_step_ready(Step.FILE, True)
    window.next_button.click()
    app.processEvents()
    window.grab().save(str(out_dir / f"main_step2_{tag}.png"))
    gallery = build_gallery()
    gallery.resize(900, 760)
    gallery.show()
    app.processEvents()
    gallery.grab().save(str(out_dir / f"gallery_{tag}.png"))


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
