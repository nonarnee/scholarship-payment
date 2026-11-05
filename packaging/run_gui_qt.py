"""PyInstaller 진입점: 신규 PySide6 화면(정식 배포 후보의 기본 GUI). 사용자용 옵션(--smoke, --version)만 받는다."""
import sys

from scholarship_payment.ui.app_main import main

sys.exit(main())
