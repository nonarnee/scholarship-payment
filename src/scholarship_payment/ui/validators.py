"""화면용 입력 검증(Qt 무관). 세 단계를 구분한다.
 ① 존재·확장자 같은 **가벼운 검사**(`light`, 즉시, 파일을 열지 않음)
 ② 파일 구조 확인(`heavy`, 시간이 걸릴 수 있어 백그라운드에서 실행): 원본은 xlsx 컨테이너 모양만 보고 셀·금액은 읽지 않는다.
 ③ 실제 변환 준비 상태는 이 모듈이 판단하지 않는다(Phase 4의 변환 단계).
메시지에는 규칙 코드에 해당하는 고정 문구만 쓰며 파일 이름·경로·값을 넣지 않는다(경로 표시는 화면이 별도로 한다).
"""
from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scholarship_payment.config.policy_builder import derive_from_template
from scholarship_payment.config.policy_file import load_policy
from scholarship_payment.errors import ValidationFailed

UNSET, CHECKING, OK, ERROR = "unset", "checking", "ok", "error"
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_DATE_RE = re.compile(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}", re.ASCII)


@dataclass(frozen=True)
class FieldState:
    level: str
    code: str | None = None
    note: str | None = None          # 통과했지만 알려 줄 것(예: 암호 파일로 보임)

    @property
    def ok(self) -> bool:
        return self.level == OK


UNSET_STATE = FieldState(UNSET)
CHECKING_STATE = FieldState(CHECKING)
OK_STATE = FieldState(OK)


def _err(code: str) -> FieldState:
    return FieldState(ERROR, code)


MESSAGES = {
    "SOURCE_MISSING": "파일을 찾을 수 없습니다.", "SOURCE_NOT_FILE": "파일이 아닙니다.",
    "SOURCE_NOT_XLSX_EXT": "엑셀(.xlsx) 파일만 사용할 수 있습니다.", "SOURCE_TEMP_FILE": "엑셀이 만든 임시 파일(~$)입니다. 원본 파일을 선택하세요.",
    "SOURCE_EMPTY": "빈 파일입니다.", "SOURCE_UNREADABLE": "파일을 읽을 수 없습니다. 다른 프로그램에서 열려 있는지 확인하세요.",
    "SOURCE_NOT_XLSX": "엑셀(.xlsx) 형식이 아니거나 손상된 파일입니다.",
    "SOURCE_ENCRYPTED_POSSIBLE": "암호가 걸린 파일로 보입니다. 비밀번호는 변환할 때 확인합니다.",
    "DIR_MISSING": "폴더를 찾을 수 없습니다.", "DIR_NOT_DIR": "폴더가 아닙니다.",
    "DIR_NOT_WRITABLE": "참고: 이 폴더에 쓸 권한이 없어 보입니다. 이 확인은 참고용이며 실제 저장 가능 여부는 변환할 때 확인합니다.",
    "TEMPLATE_MISSING": "템플릿 파일을 찾을 수 없습니다.", "TEMPLATE_NOT_FILE": "템플릿이 파일이 아닙니다.",
    "TEMPLATE_NOT_XLSX_EXT": "템플릿은 엑셀(.xlsx) 파일이어야 합니다.", "TEMPLATE_UNREADABLE": "템플릿을 열 수 없습니다.",
    "TEMPLATE_LAYOUT": "템플릿 구조가 맞지 않습니다(WRIS 시트와 머리글을 확인하세요).",
    "POLICY_FILE_MISSING": "정책 파일을 찾을 수 없습니다.", "POLICY_NOT_FILE": "정책 파일이 파일이 아닙니다.",
    "POLICY_NOT_JSON_EXT": "정책 파일은 .json 파일이어야 합니다.", "POLICY_UNREADABLE": "정책 파일을 읽을 수 없습니다.",
    "POLICY_NOT_OBJECT": "정책 파일 형식이 맞지 않습니다.", "POLICY_KEY_MISSING": "정책 파일에 필요한 항목이 빠져 있습니다.",
    "POLICY_KEY_UNKNOWN": "정책 파일에 알 수 없는 항목이 있습니다.",
    "DATE_FORMAT": "기준일은 YYYY.MM.DD 형식이어야 합니다.", "DATE_INVALID": "존재하지 않는 날짜입니다.",
    "DROP_EMPTY": "놓은 항목에서 파일을 찾지 못했습니다.", "DROP_MULTIPLE": "파일은 한 개만 선택할 수 있습니다.",
    "DROP_NOT_XLSX": "엑셀(.xlsx) 파일만 사용할 수 있습니다.", "DROP_NOT_FILE": "파일을 찾을 수 없거나 폴더입니다.",
    "SETTINGS_SAVE_FAILED": "설정 파일을 저장하지 못했습니다.",
    "POLICY_OUTPUT_EXISTS": "이미 있는 파일입니다. 다른 이름을 선택하세요. (기존 파일은 덮어쓰지 않습니다)",
    "POLICY_OUTPUT_IO": "해당 위치에 저장하지 못했습니다. 다른 위치를 선택하세요.",
    "POLICY_TYPE": "입력 형식이 맞지 않습니다. 시급은 0보다 큰 정수(원)로 입력하세요. (시급표는 '이름=금액, 이름=금액' 형식입니다)",
    "POLICY_PLACEHOLDER": "아직 채워지지 않은 항목('<입력 필요>')이 있습니다.",
    "POLICY_TEMPLATE": "제목·적요 형식에는 {year}, {month} 외의 치환자를 쓸 수 없습니다.",
    "POLICY_EDIT_CONFLICT": "정책 파일이 불러온 뒤 다른 곳에서 바뀌었습니다. 아무것도 저장하지 않았습니다. 이 창을 닫고 다시 열어 최신 내용을 확인하세요.",
    "POLICY_EDIT_EXTRA_RATE_KEYS": "이 정책의 시급표에 '도시'·'농어촌' 외의 항목이 있어 이 화면에서 수정할 수 없습니다. 기존 항목을 지우지 않으려고 막았습니다. 정책 파일을 직접 확인하세요.",
    "POLICY_EDIT_BACKUP_FAILED": "백업 파일을 만들지 못해 저장하지 않았습니다. 원본은 그대로입니다.",
    "POLICY_EDIT_IO": "정책 파일을 저장하지 못했습니다. 원본은 그대로입니다.",
    "POLICY_EDIT_NOT_ALLOWED": "지금은 정책 파일을 수정할 수 없습니다. 첫 단계(파일 선택)에서 생성 중이 아닐 때만 수정할 수 있습니다.",
    "CHECK_FAILED": "검사 중 문제가 생겼습니다. 다시 선택해 주세요.",
}


def message(code: str | None) -> str:
    if not code:
        return ""
    return MESSAGES.get(code, f"사용할 수 없는 파일입니다. (코드: {code})")


_KIND = {"source": ("SOURCE", ".xlsx"), "template": ("TEMPLATE", ".xlsx"), "policy": ("POLICY", ".json")}


def _blank(path) -> bool:
    return path is None or str(path).strip() == ""


def light(kind: str, path) -> FieldState:
    """즉시 실행해도 되는 검사. 파일을 열지 않는다(존재·종류·확장자·크기만)."""
    if _blank(path):
        return UNSET_STATE
    p = Path(str(path))
    if kind == "dir":
        if not p.exists():
            return _err("DIR_MISSING")
        if not p.is_dir():
            return _err("DIR_NOT_DIR")
        # os.access 는 운영체제·권한 설정에 따라 틀릴 수 있어 확정 근거로 쓰지 않는다: 차단하지 않고 참고만 알린다.
        return OK_STATE if os.access(p, os.W_OK) else FieldState(OK, note="DIR_NOT_WRITABLE")
    prefix, ext = _KIND[kind]
    missing = "POLICY_FILE_MISSING" if kind == "policy" else f"{prefix}_MISSING"
    if not p.exists():
        return _err(missing)
    if not p.is_file():
        return _err(f"{prefix}_NOT_FILE")
    if p.suffix.lower() != ext:
        return _err("POLICY_NOT_JSON_EXT" if kind == "policy" else f"{prefix}_NOT_XLSX_EXT")
    if kind == "source":
        if p.name.startswith("~$"):
            return _err("SOURCE_TEMP_FILE")
        try:
            if p.stat().st_size == 0:
                return _err("SOURCE_EMPTY")
        except OSError:
            return _err("SOURCE_UNREADABLE")
    return OK_STATE


def _source_structure(p: Path) -> FieldState:
    try:
        with open(p, "rb") as f:
            head = f.read(8)
    except OSError:
        return _err("SOURCE_UNREADABLE")
    if head == OLE_MAGIC:                                   # 암호가 걸린 OOXML 은 OLE 컨테이너다(내용은 읽지 않는다)
        return FieldState(OK, note="SOURCE_ENCRYPTED_POSSIBLE")
    try:
        with zipfile.ZipFile(p) as z:
            names = set(z.namelist())
    except (zipfile.BadZipFile, OSError):
        return _err("SOURCE_NOT_XLSX")
    return OK_STATE if {"[Content_Types].xml", "xl/workbook.xml"} <= names else _err("SOURCE_NOT_XLSX")


def _first_code(e: ValidationFailed, fallback: str) -> str:
    return e.errors[0].code if getattr(e, "errors", None) else fallback


def heavy(kind: str, path) -> FieldState:
    """시간이 걸릴 수 있는 구조 검사(백그라운드용). 먼저 light 를 통과해야 한다. 예외 문구는 쓰지 않고 코드만 돌려준다."""
    first = light(kind, path)
    if not first.ok:
        return first
    p = Path(str(path))
    try:
        if kind == "source":
            return _source_structure(p)
        if kind == "template":
            derive_from_template(p)
        elif kind == "policy":
            load_policy(p)
        else:
            return first
    except ValidationFailed as e:
        return _err(_first_code(e, "TEMPLATE_LAYOUT" if kind == "template" else "POLICY_UNREADABLE"))
    except Exception:
        return _err("TEMPLATE_UNREADABLE" if kind == "template" else "POLICY_UNREADABLE")
    return OK_STATE


def check_date(text: str) -> FieldState:
    if not isinstance(text, str) or not _DATE_RE.fullmatch(text):
        return _err("DATE_FORMAT")
    try:
        datetime.strptime(text, "%Y.%m.%d")
    except ValueError:
        return _err("DATE_INVALID")
    return OK_STATE


def classify_drop(paths: list[str]) -> tuple[str | None, str | None]:
    """끌어다 놓은 항목 → (선택할 경로, None) 또는 (None, 거부 코드). 파일은 한 개, 존재, .xlsx 만 받는다."""
    if not paths:
        return None, "DROP_EMPTY"
    if len(paths) > 1:
        return None, "DROP_MULTIPLE"
    p = Path(paths[0]) if paths[0] else None
    if p is None or not p.is_file():
        return None, "DROP_NOT_FILE"
    if p.suffix.lower() != ".xlsx":
        return None, "DROP_NOT_XLSX"
    return str(p), None
