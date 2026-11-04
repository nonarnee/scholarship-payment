"""PyInstaller 진입점(신규 PySide6 화면, 개발용 확인 빌드). 실제 배포 진입점은 Phase 5 에서 `run_gui.py` 를 교체할 때 정한다."""
import sys

from scholarship_payment.ui.__main__ import main

sys.exit(main())
