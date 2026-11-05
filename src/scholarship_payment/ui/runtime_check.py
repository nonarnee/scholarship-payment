"""패키징된 실행 파일에 생성 경로에 필요한 모듈이 모두 들어 있는지 확인한다(정식 `--smoke` 와 합성 E2E 가 함께 쓴다)."""
from __future__ import annotations

import importlib

REQUIRED_MODULES = ("openpyxl", "msoffcrypto", "cryptography", "scholarship_payment.app.convert", "scholarship_payment.app.workflow",
                    "scholarship_payment.adapters.daechung", "scholarship_payment.adapters.multicultural", "scholarship_payment.adapters.source",
                    "scholarship_payment.validation.validator", "scholarship_payment.writers.template_writer", "scholarship_payment.writers.output_check",
                    "scholarship_payment.io.safe_save", "scholarship_payment.ui.step1", "scholarship_payment.ui.step2", "scholarship_payment.ui.step3",
                    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets")


def missing_modules() -> list[str]:
    missing = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    return missing
