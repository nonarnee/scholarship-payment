"""입력 파일 열기: 암호가 걸린 .xlsx 는 비밀번호로 **메모리에서만** 복호화한다(임시 파일 없음, 원본 불변).
비밀번호와 라이브러리 예외 원문은 오류·로그에 남기지 않는다.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import msoffcrypto
from msoffcrypto.exceptions import InvalidKeyError

from scholarship_payment.adapters.base import InputValidationFailed
from scholarship_payment.errors import ValidationError

PASSWORD_REQUIRED = "INPUT_PASSWORD_REQUIRED"
PASSWORD_WRONG = "INPUT_PASSWORD_WRONG"


def _fail(code: str) -> InputValidationFailed:
    return InputValidationFailed([ValidationError(code, "file")])


def open_source(path: Path, password: str | None = None) -> Path | BytesIO:
    """암호 없는 파일은 경로를 그대로, 암호 파일은 복호화한 BytesIO 를 돌려준다."""
    try:
        with open(path, "rb") as f:
            office = msoffcrypto.OfficeFile(f)
            if not office.is_encrypted():
                return path
            if not password:
                raise _fail(PASSWORD_REQUIRED)
            office.load_key(password=password, verify_password=True)
            buf = BytesIO()
            office.decrypt(buf)
    except InputValidationFailed:
        raise
    except InvalidKeyError:
        raise _fail(PASSWORD_WRONG) from None
    except Exception:                       # 형식 오류·손상·미지원 방식. 원인 메시지는 노출하지 않는다.
        return path                         # 평문 .xlsx 가 아니면 이후 load_workbook 이 FILE_UNREADABLE 로 처리한다
    buf.seek(0)
    return buf
