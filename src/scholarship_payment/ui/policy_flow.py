"""정책 파일 만들기 화면의 로직(Qt 무관). 실제 생성은 기존 `config.policy_builder`를 그대로 쓴다(템플릿에서 머리글 읽기, 검증 후 저장, 기존 파일 무덮어쓰기).
입력값(근로구분명·구분코드·적요 등)은 정책 파일에만 쓰이고 설정·로그에는 남지 않는다. 오류는 코드만 돌려준다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scholarship_payment.config.policy_builder import HIDDEN_FOR, PROMPTS, RATES_PROMPT, USER_KEYS, build_policy_dict, save_policy_new
from scholarship_payment.errors import ValidationFailed


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
    out = [PolicyField(k, PROMPTS[k]) for k in USER_KEYS]
    if program in HIDDEN_FOR:
        out.append(PolicyField("rates", RATES_PROMPT))
    return out


def suggest_path(program: str, folder: Path) -> Path:
    """폴더 안에서 아직 없는 첫 이름(policy_<사업>.json, _2, _3 …). 기존 파일을 가리키지 않는다."""
    base = Path(folder) / f"policy_{program}.json"
    n = 2
    while base.exists():
        base = Path(folder) / f"policy_{program}_{n}.json"
        n += 1
    return base


def create_policy(template, values: dict, out, program: str, rates_text: str | None = None) -> CreateResult:
    out = Path(out)
    try:
        d = build_policy_dict(template, {k: values.get(k, "") for k in USER_KEYS}, program, rates_text)
        out.parent.mkdir(parents=True, exist_ok=True)
        path = save_policy_new(out, d)
    except ValidationFailed as e:
        return CreateResult(False, None, tuple(dict.fromkeys(x.code for x in e.errors)))
    except OSError:
        return CreateResult(False, None, ("POLICY_OUTPUT_IO",))
    return CreateResult(True, path)
