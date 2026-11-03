"""명령줄: python -m scholarship_payment convert --program daechung --input <원본.xlsx> --out-dir <폴더>.
성공하면 출력 파일 경로·인원·경고 코드만, 실패하면 규칙 코드·필드·행 번호만 표시한다(성명·학번·계좌 비표시).
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

from scholarship_payment.app.controller import run_conversion
from scholarship_payment.app.convert import ADAPTERS
from scholarship_payment.config.policy_builder import PROMPTS, make_policy_file
from scholarship_payment.errors import ValidationFailed

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
MAX_PASSWORD_TRIES = 3
_DATE = re.compile(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="scholarship_payment")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("convert", help="재단 월별지급승인 원본을 지급명단 엑셀로 변환")
    c.add_argument("--program", required=True, choices=sorted(ADAPTERS))
    c.add_argument("--input", required=True, type=Path, help="재단에서 내려받은 원본 파일(읽기만 함)")
    c.add_argument("--out-dir", required=True, type=Path, help="결과 파일을 만들 기존 폴더(기존 파일은 덮어쓰지 않음)")
    c.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="출력 템플릿(기본: 합성 템플릿)")
    c.add_argument("--policy", type=Path, help="출력 정책 JSON(실제 상수·머리글. 생략하면 합성 정책). 저장소 밖에 보관")
    c.add_argument("--base-date", help="명단 기준일 YYYY.MM.DD(생략하면 작성일=오늘)")
    c.add_argument("--ask-password", action="store_true", help="원본에 암호가 걸려 있으면 실행 중에 비밀번호를 입력받음(인자로는 받지 않음)")
    p = sub.add_parser("make-policy", help="실제 템플릿과 직접 입력한 상수 5개로 정책 파일(JSON)을 만든다")
    p.add_argument("--template", required=True, type=Path, help="학교 실제 출력 템플릿")
    p.add_argument("--out", required=True, type=Path, help="만들 정책 파일 경로(이미 있으면 만들지 않음)")
    return ap


def _make_policy(args) -> int:
    values = {k: input(f"{label}: ") for k, label in PROMPTS.items()}
    try:
        path = make_policy_file(args.template, values, args.out)
    except ValidationFailed as e:
        print("정책 파일을 만들지 못했습니다.", file=sys.stderr)
        for err in e.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"정책 파일 생성: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "make-policy":
        return _make_policy(args)
    if args.base_date is not None and not _DATE.fullmatch(args.base_date):
        print("오류: --base-date 는 YYYY.MM.DD 형식이어야 합니다.", file=sys.stderr)
        return 2
    o = run_conversion(args.program, args.input, args.out_dir, args.template, args.policy, args.base_date)
    if o.needs_password and args.ask_password:
        for _ in range(MAX_PASSWORD_TRIES):
            o = run_conversion(args.program, args.input, args.out_dir, args.template, args.policy, args.base_date,
                               password=getpass.getpass("원본 파일 비밀번호: "))
            if not o.needs_password:
                break
    if o.needs_password:
        print("변환 실패(input): " + o.summary + ("" if args.ask_password else " --ask-password 로 실행하세요."), file=sys.stderr)
        return 1
    if not o.ok:
        stage = "policy" if o.stage == "policy" else o.stage
        print(f"변환 실패({stage}): {o.summary.split(': ', 1)[-1]}", file=sys.stderr)
        for line in o.details:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"완료: {o.output_path}")
    print(f"대상자 {o.count}명, 출력 재검증 통과")
    for line in o.details:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
