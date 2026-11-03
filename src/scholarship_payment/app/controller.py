"""화면·명령줄 공용 실행 계층: 입력값 확인 → 정책 로드 → convert → 사용자에게 보여줄 문구.
업무 규칙은 여기 두지 않는다(convert 가 담당). 문구에는 규칙 코드·필드·행 번호만 넣고 성명·학번·계좌는 넣지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scholarship_payment.adapters.source import PASSWORD_REQUIRED, PASSWORD_WRONG
from scholarship_payment.app.convert import ConversionFailed, convert
from scholarship_payment.config.policy import SYNTHETIC_POLICY
from scholarship_payment.config.policy_file import load_policy
from scholarship_payment.errors import ValidationFailed

DATE_RE = re.compile(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}")
MAX_LINES = 50


@dataclass(frozen=True)
class Outcome:
    ok: bool
    stage: str                    # "ok" | "args" | "policy" | input/template/validate/write/output
    summary: str
    details: tuple[str, ...] = ()
    output_path: Path | None = None
    count: int = 0
    needs_password: bool = False   # 화면이 비밀번호를 묻고 다시 실행해야 할 때


def _lines(errors) -> tuple[str, ...]:
    out = [f"- {e}" for e in errors[:MAX_LINES]]
    if len(errors) > MAX_LINES:
        out.append(f"... 외 {len(errors) - MAX_LINES}건")
    return tuple(out)


def run_conversion(program: str, input_path, out_dir, template_path, policy_path=None, base_date: str | None = None,
                   today: date | None = None, password: str | None = None) -> Outcome:
    if not input_path:
        return Outcome(False, "args", "재단 원본 파일을 선택하세요.")
    if not out_dir:
        return Outcome(False, "args", "결과를 저장할 폴더를 선택하세요.")
    if not template_path:
        return Outcome(False, "args", "출력 템플릿(은행코드 표가 들어 있는 학교 양식 파일)을 선택하세요.")
    if base_date is not None and not DATE_RE.fullmatch(base_date):
        return Outcome(False, "args", "기준일은 YYYY.MM.DD 형식이어야 합니다.")
    policy = SYNTHETIC_POLICY
    if policy_path:
        try:
            policy = load_policy(policy_path)
        except ValidationFailed as e:
            return Outcome(False, "policy", "정책 파일을 사용할 수 없어 파일을 만들지 않았습니다.", _lines(e.errors))
    try:
        r = convert(program, Path(input_path), Path(out_dir), Path(template_path), policy=policy, base_date=base_date, today=today, password=password)
    except ConversionFailed as e:
        extra: tuple[str, ...] = ()
        if e.stage == "template" and not policy_path:
            extra = ("(합성 정책으로 실행 중입니다. 실제 템플릿이면 정책 파일(--policy)이 필요할 수 있습니다.)",)
        codes = {x.code for x in e.errors}
        if codes & {PASSWORD_REQUIRED, PASSWORD_WRONG}:
            msg = "비밀번호가 틀렸습니다." if PASSWORD_WRONG in codes else "암호가 걸린 파일입니다. 비밀번호가 필요합니다."
            return Outcome(False, e.stage, msg, (), needs_password=True)
        return Outcome(False, e.stage, "변환 실패: 파일을 만들지 않았습니다.", extra + _lines(e.errors))
    return Outcome(True, "ok", f"완료: 대상자 {r.count}명, 출력 재검증 통과", tuple(f"경고: {w}" for w in r.warnings), r.output_path, r.count)
