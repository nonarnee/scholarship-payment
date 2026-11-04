"""검사 상태 → 화면 문구·배지 종류. **실제로 확인한 것만** 표현한다(원본은 '형식 확인', 템플릿은 'WRIS 머리글 확인', 정책은 '형식 확인').
'정상', '완료', '변환 준비' 같은 말은 쓰지 않는다 — 변환 준비 여부는 이 단계에서 판단하지 않는다.
"""
from __future__ import annotations

from scholarship_payment.ui import validators as v

_OK_TEXT = {"source": "엑셀 형식 확인됨 (내용은 아직 읽지 않음)", "template": "WRIS 머리글 확인됨", "policy": "정책 형식 확인됨"}
_CHECKING = {"source": "구조 확인 중…", "template": "구조 확인 중…", "policy": "확인 중…"}


def describe(kind: str, st: v.FieldState) -> tuple[str, str | None]:
    """(배지 문구, 배지 종류). 문구가 비면 배지를 숨긴다."""
    if st.level == v.UNSET:
        return ("", None) if kind == "source" else ("설정 필요", "caution")
    if st.level == v.CHECKING:
        return _CHECKING[kind], "neutral"
    if st.level == v.ERROR:
        return "사용할 수 없음", "error"
    if st.note:
        return "암호 파일로 보임 (구조 미확인)", "caution"
    return _OK_TEXT[kind], "verified"


def detail(st: v.FieldState) -> str:
    """배지 아래에 보여 줄 사유(오류 또는 참고)."""
    if st.level == v.ERROR:
        return v.message(st.code)
    return v.message(st.note) if st.note else ""


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def dir_message(st: v.FieldState) -> str:
    """저장 폴더 안내. 사전 확인일 뿐이라 '저장할 수 있다'고 보장하는 말은 쓰지 않는다."""
    if st.note:
        return v.message(st.note)
    return "폴더가 있는 것을 확인했습니다. 실제로 저장할 수 있는지는 변환할 때 확인합니다."
