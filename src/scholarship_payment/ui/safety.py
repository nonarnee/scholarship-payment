"""처리되지 않은 예외의 출력을 안전하게 만든다(정식·개발 진입점 공용)."""
from __future__ import annotations

import os
import sys


def install_safe_excepthook() -> None:
    """처리되지 않은 예외는 종류만 출력한다. 예외 문구·추적 정보에는 파일 이름·경로가 들어갈 수 있다.
    개발 중 자세한 정보가 필요하면 환경변수 SCHOLARSHIP_UI_DEBUG=1 을 설정한다."""
    original = sys.excepthook

    def hook(exc_type, exc, tb):
        if os.environ.get("SCHOLARSHIP_UI_DEBUG") == "1":
            original(exc_type, exc, tb)
        else:
            print(f"예기치 않은 오류가 발생했습니다: {exc_type.__name__}", file=sys.stderr)

    sys.excepthook = hook
