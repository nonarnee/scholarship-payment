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


RATES_PROMPT = "시급표 (예: 이름=금액, 이름=금액 — 이름은 원본 근무형태 끝 괄호 안의 글자)"
HIDDEN_FOR = {"multicultural": ("F",)}                 # 원본에 없는 열(사업자등록번호)을 공란+숨김 처리
# 화면의 두 입력칸(시급(도시)·시급(농어촌))이 쓰는 hourly_rates 키. 다문화 Adapter 는 원본 근무형태 끝 괄호 안의 글자와 키가 정확히 같아야 시급을 찾는다.
# 실제 원본의 괄호 값이 이 두 글자와 일치하는지는 확인되지 않았다(미검증). 다른 이름을 추정해 넣지 않는다.
RATE_KEY_URBAN, RATE_KEY_RURAL = "도시", "농어촌"
RATE_KEYS = (RATE_KEY_URBAN, RATE_KEY_RURAL)


def parse_rate_value(text) -> int:
    """시급 한 칸(원)을 정수로 바꾼다: ASCII 숫자만(쉼표 허용), 0보다 커야 한다. 틀리면 ValidationFailed(값은 오류에 넣지 않음)."""
    amount = (text if isinstance(text, str) else "").strip().replace(",", "")
    if not amount or not amount.isascii() or not amount.isdigit() or int(amount) <= 0:
        raise ValidationFailed([ValidationError("POLICY_TYPE", "hourly_rates")])
    return int(amount)


def rates_from_fields(urban, rural) -> dict[str, int]:
    """시급(도시)·시급(농어촌) 두 칸 → hourly_rates. 키는 고정(RATE_KEYS)이고 두 칸 모두 필요하다."""
    return {RATE_KEY_URBAN: parse_rate_value(urban), RATE_KEY_RURAL: parse_rate_value(rural)}


def parse_rates(text: str) -> dict[str, int]:
    """`이름=금액, 이름=금액` 문자열을 시급표로 바꾼다. 형식이 틀리면 ValidationFailed(값은 오류에 넣지 않음)."""
    rates: dict[str, int] = {}
    for part in (text or "").split(","):
        name, sep, amount = part.partition("=")
        name, amount = name.strip(), amount.strip().replace(",", "")
        if not sep or not name or not amount.isascii() or not amount.isdigit() or int(amount) <= 0 or name in rates:
            raise ValidationFailed([ValidationError("POLICY_TYPE", "hourly_rates")])
        rates[name] = int(amount)
    return rates


def build_policy_dict(template: str | Path, values: dict[str, str], program: str = "daechung", rates_text: str | None = None,
                      rates: dict[str, int] | None = None) -> dict:
    missing = [k for k in USER_KEYS if not isinstance(values.get(k), str) or not values[k].strip()]
    if missing:
        raise ValidationFailed([ValidationError("POLICY_KEY_MISSING", k) for k in missing])
    d = derive_from_template(template)
    d.update({k: values[k] for k in USER_KEYS})
    d["file_prefix"] = DEFAULT_PREFIX
    out = {k: d[k] for k in KEYS}
    if program in HIDDEN_FOR:
        if rates is not None:                              # 화면의 두 입력칸(검증된 hourly_rates). 기존 rates_text 경로(CLI·Tk)는 그대로 둔다
            if not rates:
                raise ValidationFailed([ValidationError("POLICY_TYPE", "hourly_rates")])
            out["hourly_rates"] = dict(rates)
        else:
            out["hourly_rates"] = parse_rates(rates_text or "")
        out["hidden_list_columns"] = list(HIDDEN_FOR[program])
    return out


def validate_policy_dict(d: dict) -> str:
    """정책 dict 를 저장 형식 그대로 임시 파일에 써서 load_policy 로 검증한다(생성·수정이 같은 검증을 쓴다). 통과하면 저장할 JSON 텍스트를 돌려준다.
    잘못된 값이면 ValidationFailed(코드·키 이름만)."""
    text = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        load_policy(tmp)
    finally:
        os.unlink(tmp)
    return text


def save_policy_new(out: str | Path, d: dict) -> Path:
    """검증(load_policy)을 통과한 정책만, 기존 파일을 덮어쓰지 않고 저장한다."""
    out = Path(out)
    text = validate_policy_dict(d)                         # 잘못된 값이면 ValidationFailed (파일은 만들지 않음)
    try:
        with open(out, "x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        raise ValidationFailed([ValidationError("POLICY_OUTPUT_EXISTS", "file")]) from None
    except OSError:
        raise ValidationFailed([ValidationError("POLICY_OUTPUT_IO", "file")]) from None
    return out


def make_policy_file(template: str | Path, values: dict[str, str], out: str | Path, program: str = "daechung",
                     rates_text: str | None = None, rates: dict[str, int] | None = None) -> Path:
    return save_policy_new(out, build_policy_dict(template, values, program, rates_text, rates))
