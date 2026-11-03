"""정책 JSON 파일 로더. 실제 근로구분명·구분코드·적요·머리글 같은 비공개 값은 저장소 밖의 이 파일로만 들어온다.

- **모든 키가 필수**다. 빠진 값을 합성 기본값으로 채우지 않는다(실제 업로드에 합성 상수가 섞이는 사고 방지).
- 알 수 없는 키, 타입 오류, 자리표시자(`<입력 필요>`) 잔존, 허용되지 않는 치환자, 위험한 파일명 접두는 차단한다.
- 오류에는 규칙 코드와 키 이름만 담고 값은 담지 않는다(DI-13).
"""
from __future__ import annotations

import json
import re
import string
from dataclasses import asdict
from pathlib import Path

from scholarship_payment.config.policy import OutputPolicy
from scholarship_payment.errors import ValidationError, ValidationFailed

PLACEHOLDER = "<입력 필요>"
KEYS = ("list_title", "wins_work_name", "wris_gub_a", "wris_gub_b", "remit_info", "wris_headers", "excluded_sheets", "file_prefix")
OPTIONAL_KEYS = ("hourly_rates", "hidden_list_columns")
_COLUMN_RE = re.compile(r"[A-Q]")
_TEMPLATE_KEYS = ("list_title", "remit_info")
_STRING_KEYS = ("list_title", "wins_work_name", "wris_gub_a", "wris_gub_b", "remit_info", "file_prefix")
_BAD_PREFIX = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def policy_to_dict(policy: OutputPolicy) -> dict:
    d = asdict(policy)
    d["wris_headers"] = list(policy.wris_headers)
    d["excluded_sheets"] = list(policy.excluded_sheets)
    out = {k: d[k] for k in KEYS}
    if policy.hourly_rates:
        out["hourly_rates"] = dict(policy.hourly_rates)
    if policy.hidden_list_columns:
        out["hidden_list_columns"] = list(policy.hidden_list_columns)
    return out


def _bad_template(text: str) -> bool:
    try:
        parts = list(string.Formatter().parse(text))
    except ValueError:
        return True
    return any(name is not None and (name not in ("year", "month") or spec or conv) for _, name, spec, conv in parts)


def _bad_prefix(text: str) -> bool:
    return bool(_BAD_PREFIX.search(text)) or text.startswith(".") or ".." in text or text != text.rstrip(" .")


def load_policy(path: str | Path) -> OutputPolicy:
    p = Path(path)
    if not p.is_file():
        raise ValidationFailed([ValidationError("POLICY_FILE_MISSING", "file")])
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValidationFailed([ValidationError("POLICY_UNREADABLE", "file")]) from None
    if not isinstance(data, dict):
        raise ValidationFailed([ValidationError("POLICY_NOT_OBJECT", "file")])

    errors: list[ValidationError] = []
    if set(data) - set(KEYS) - set(OPTIONAL_KEYS):
        errors.append(ValidationError("POLICY_KEY_UNKNOWN", "keys"))
    for key in KEYS:
        if key not in data:
            errors.append(ValidationError("POLICY_KEY_MISSING", key))
            continue
        value = data[key]
        if key in _STRING_KEYS:
            if not isinstance(value, str) or not value.strip():
                errors.append(ValidationError("POLICY_TYPE", key))
                continue
            if value == PLACEHOLDER:
                errors.append(ValidationError("POLICY_PLACEHOLDER", key))
            elif key in _TEMPLATE_KEYS and _bad_template(value):
                errors.append(ValidationError("POLICY_TEMPLATE", key))
            elif key == "file_prefix" and _bad_prefix(value):
                errors.append(ValidationError("POLICY_FILE_PREFIX", key))
        else:
            items_ok = isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
            if not items_ok or (key == "wris_headers" and not value):
                errors.append(ValidationError("POLICY_TYPE", key))
            elif PLACEHOLDER in value:
                errors.append(ValidationError("POLICY_PLACEHOLDER", key))
    rates = data.get("hourly_rates", {})
    if not isinstance(rates, dict) or not all(
            isinstance(k, str) and k.strip() and k != PLACEHOLDER and isinstance(v, int) and not isinstance(v, bool) and v > 0
            for k, v in rates.items()):
        errors.append(ValidationError("POLICY_TYPE", "hourly_rates"))
    hidden = data.get("hidden_list_columns", [])
    if not isinstance(hidden, list) or not all(isinstance(c, str) and _COLUMN_RE.fullmatch(c) for c in hidden) or len(set(hidden)) != len(hidden):
        errors.append(ValidationError("POLICY_TYPE", "hidden_list_columns"))
    if errors:
        raise ValidationFailed(errors)
    return OutputPolicy(
        list_title=data["list_title"], wins_work_name=data["wins_work_name"], wris_gub_a=data["wris_gub_a"],
        wris_gub_b=data["wris_gub_b"], remit_info=data["remit_info"], wris_headers=tuple(data["wris_headers"]),
        excluded_sheets=tuple(data["excluded_sheets"]), file_prefix=data["file_prefix"],
        hourly_rates=tuple(rates.items()), hidden_list_columns=tuple(hidden),
    )
