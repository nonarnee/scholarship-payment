"""정책 파일 만들기·수정 화면의 로직(Qt 무관). 생성은 기존 `config.policy_builder`(템플릿에서 머리글 읽기, 검증 후 저장, 기존 파일 무덮어쓰기)를,
수정은 `config.policy_edit`(같은 검증 + 백업·충돌 확인·원자 교체)를 그대로 쓴다.
입력값(근로구분명·구분코드·적요·시급 등)은 정책 파일에만 쓰이고 설정·로그에는 남지 않는다. 오류는 코드만 돌려준다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scholarship_payment.config import policy_edit
from scholarship_payment.config.policy_builder import (HIDDEN_FOR, PROMPTS, RATE_KEY_RURAL, RATE_KEY_URBAN, USER_KEYS, build_policy_dict, rates_from_fields,
                                                       save_policy_new)
from scholarship_payment.errors import ValidationFailed

RATE_FIELDS = (("rate_urban", "시급(도시)"), ("rate_rural", "시급(농어촌)"))
RATE_NOTE = ("시급은 원 단위 정수로 입력합니다. 이 두 칸은 원본 근무형태 끝 괄호 안의 글자가 '도시'·'농어촌'일 때만 시급을 찾습니다. "
             "실제 원본의 괄호 값과 일치하는지는 확인되지 않았습니다(미검증).")


@dataclass(frozen=True)
class PolicyField:
    key: str
    label: str


@dataclass(frozen=True)
class CreateResult:
    ok: bool
    path: Path | None = None
    codes: tuple[str, ...] = ()


def fields_for(program: str) -> list[PolicyField]:
    """입력칸 목록. 시급(도시)·시급(농어촌)은 다문화·탈북학생 멘토링에만 있다."""
    out = [PolicyField(k, PROMPTS[k]) for k in USER_KEYS]
    if program in HIDDEN_FOR:
        out.extend(PolicyField(k, label) for k, label in RATE_FIELDS)
    return out


def edit_fields_for(program: str) -> list[PolicyField]:
    return fields_for(program)                                  # 생성과 수정이 같은 칸을 쓴다


def suggest_path(program: str, folder: Path) -> Path:
    """폴더 안에서 아직 없는 첫 이름(policy_<사업>.json, _2, _3 …). 기존 파일을 가리키지 않는다."""
    base = Path(folder) / f"policy_{program}.json"
    n = 2
    while base.exists():
        base = Path(folder) / f"policy_{program}_{n}.json"
        n += 1
    return base


def _codes(e: ValidationFailed) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x.code for x in e.errors))


def create_policy(template, values: dict, out, program: str, rates_text: str | None = None, rate_values: dict | None = None) -> CreateResult:
    """rate_values(두 입력칸)가 있으면 그것을, 없으면 기존 rates_text(CLI·Tk 경로)를 쓴다."""
    out = Path(out)
    try:
        rates = None
        if program in HIDDEN_FOR and rate_values is not None:
            rates = rates_from_fields(rate_values.get("rate_urban"), rate_values.get("rate_rural"))
        d = build_policy_dict(template, {k: values.get(k, "") for k in USER_KEYS}, program, rates_text, rates)
        out.parent.mkdir(parents=True, exist_ok=True)
        path = save_policy_new(out, d)
    except ValidationFailed as e:
        return CreateResult(False, None, _codes(e))
    except OSError:
        return CreateResult(False, None, ("POLICY_OUTPUT_IO",))
    return CreateResult(True, path)


# ---------- 기존 정책 수정 ----------
@dataclass(frozen=True)
class EditLoad:
    ok: bool
    session: policy_edit.PolicyEditSession | None = None
    values: dict = field(default_factory=dict, repr=False)
    rate_values: dict = field(default_factory=dict, repr=False)
    codes: tuple[str, ...] = ()
    blocked: bool = False                                       # 수정할 수 없는 내용(추가 시급 키 등)이라 열지 않은 경우


@dataclass(frozen=True)
class EditSave:
    ok: bool
    changed: bool = False
    backup_name: str | None = None
    codes: tuple[str, ...] = ()
    sha256: str | None = None


def _as_text(v) -> str:
    return v if isinstance(v, str) else ""


def load_edit(path, program: str) -> EditLoad:
    """수정할 정책 파일을 읽어 입력칸에 채울 값을 돌려준다. 파일은 바꾸지 않는다."""
    try:
        s = policy_edit.open_for_edit(path, program)
    except ValidationFailed as e:
        codes = _codes(e)
        return EditLoad(False, None, {}, {}, codes, blocked=policy_edit.EXTRA_RATE_KEYS in codes)
    values = {k: _as_text(s.data.get(k)) for k in USER_KEYS}
    rates = {}
    if program in HIDDEN_FOR:
        old = s.data.get("hourly_rates") if isinstance(s.data.get("hourly_rates"), dict) else {}
        rates = {"rate_urban": str(old.get(RATE_KEY_URBAN, "")), "rate_rural": str(old.get(RATE_KEY_RURAL, ""))}
    return EditLoad(True, s, values, rates)


def save_edit(session: policy_edit.PolicyEditSession, values: dict, rate_values: dict | None = None) -> EditSave:
    """입력값으로 같은 경로의 정책 파일을 수정 저장한다(검증 → 충돌 확인 → 백업 → 원자 교체). 실패해도 기존 파일은 그대로다."""
    try:
        new = policy_edit.edited_data(session, {k: values.get(k, "") for k in USER_KEYS}, rate_values)
        r = policy_edit.save_policy_replace(session, new)
    except ValidationFailed as e:
        return EditSave(False, codes=_codes(e))
    return EditSave(True, r.changed, r.backup.name if r.backup else None, sha256=r.sha256)
