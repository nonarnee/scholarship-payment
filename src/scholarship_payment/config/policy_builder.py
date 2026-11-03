"""정책 파일 만들기: 템플릿에서 읽을 수 있는 항목(WRIS 머리글, 제외 시트)과 사용자가 입력한 상수 5개로 정책 JSON 을 만든다.
상수 값은 추정하지 않고 사용자가 준 값 그대로 쓴다. 저장 전에 load_policy 로 검증하고, 기존 파일은 덮어쓰지 않는다.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openpyxl import load_workbook

from scholarship_payment.config.policy_file import KEYS, load_policy
from scholarship_payment.errors import ValidationError, ValidationFailed

USER_KEYS = ("list_title", "wins_work_name", "wris_gub_a", "wris_gub_b", "remit_info")     # 사용자가 입력하는 5개
PROMPTS = {"list_title": "명단 제목 형식 ({year}/{month} 사용 가능)", "wins_work_name": "WINS 근로구분명",
           "wris_gub_a": "WRIS 구분코드 A", "wris_gub_b": "WRIS 구분코드 B", "remit_info": "WRIS 적요 형식 ({year}/{month} 사용 가능)"}

LIST_PREFIX = "지급대상자명단("
KNOWN = {"WINS", "WRIS", "은행코드"}
DEFAULT_PREFIX = "지급명단"


def derive_from_template(template: str | Path) -> dict:
    """템플릿에서 읽을 수 있는 항목만 돌려준다: wris_headers, excluded_sheets."""
    try:
        wb = load_workbook(template, read_only=False)
    except Exception:
        raise ValidationFailed([ValidationError("TEMPLATE_UNREADABLE", "template")]) from None
    if "WRIS" not in wb.sheetnames:
        raise ValidationFailed([ValidationError("TEMPLATE_LAYOUT", "sheet:WRIS")])
    headers = [c.value for c in wb["WRIS"][1]]
    while headers and (headers[-1] is None or str(headers[-1]).strip() == ""):
        headers.pop()
    if not headers or any(not isinstance(h, str) or not h.strip() for h in headers):
        raise ValidationFailed([ValidationError("TEMPLATE_LAYOUT", "WRIS:headers")])
    extra = [n for n in wb.sheetnames if n not in KNOWN and not n.startswith(LIST_PREFIX)]
    return {"wris_headers": headers, "excluded_sheets": extra}


def build_policy_dict(template: str | Path, values: dict[str, str]) -> dict:
    missing = [k for k in USER_KEYS if not isinstance(values.get(k), str) or not values[k].strip()]
    if missing:
        raise ValidationFailed([ValidationError("POLICY_KEY_MISSING", k) for k in missing])
    d = derive_from_template(template)
    d.update({k: values[k] for k in USER_KEYS})
    d["file_prefix"] = DEFAULT_PREFIX
    return {k: d[k] for k in KEYS}


def save_policy_new(out: str | Path, d: dict) -> Path:
    """검증(load_policy)을 통과한 정책만, 기존 파일을 덮어쓰지 않고 저장한다."""
    out = Path(out)
    text = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        load_policy(tmp)                                   # 잘못된 값이면 ValidationFailed (파일은 만들지 않음)
    finally:
        os.unlink(tmp)
    try:
        with open(out, "x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        raise ValidationFailed([ValidationError("POLICY_OUTPUT_EXISTS", "file")]) from None
    except OSError:
        raise ValidationFailed([ValidationError("POLICY_OUTPUT_IO", "file")]) from None
    return out


def make_policy_file(template: str | Path, values: dict[str, str], out: str | Path) -> Path:
    return save_policy_new(out, build_policy_dict(template, values))
