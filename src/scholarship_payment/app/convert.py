"""변환 오케스트레이션: Adapter → Validator → TemplateWriter → 출력 재검증 → 안전 저장.
GUI/명령줄은 이 함수만 호출한다. 업무 계산·변환 규칙은 여기 두지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from scholarship_payment.adapters.base import InputValidationFailed
from scholarship_payment.adapters.daechung import DaechungAdapter
from scholarship_payment.adapters.multicultural import MulticulturalAdapter
from scholarship_payment.config.policy import SYNTHETIC_POLICY, OutputPolicy
from scholarship_payment.core.bank_codes import BankCodeTable
from scholarship_payment.errors import ValidationError, ValidationFailed
from scholarship_payment.io.safe_save import save_new
from scholarship_payment.validation.validator import validate
from scholarship_payment.writers.output_check import verify_output
from scholarship_payment.writers.template_writer import build_workbook

ADAPTERS = {
    "daechung": lambda policy: DaechungAdapter(),
    "multicultural": lambda policy: MulticulturalAdapter(policy.rates()),
}


class ConversionFailed(ValidationFailed):
    """변환이 중단되었다. `stage`는 input / template / validate / write / output 중 하나."""

    def __init__(self, errors, stage: str, missing_banks: tuple[str, ...] = ()) -> None:
        super().__init__(errors)
        self.stage = stage
        # 은행코드 표를 고쳐야 할 은행명(화면 안내용). 오류 문구·repr 에는 포함하지 않는다.
        self.missing_banks = missing_banks


@dataclass(frozen=True)
class ConvertResult:
    output_path: Path
    count: int
    warnings: tuple[ValidationError, ...]


def convert(program: str, input_path, out_dir, template_path, policy: OutputPolicy = SYNTHETIC_POLICY,
            base_date: str | None = None, today: date | None = None,
            password: str | None = None) -> ConvertResult:
    """base_date 미지정 시 기준일은 작성일(today, 기본 오늘) `YYYY.MM.DD` (사용자 결정)."""
    if base_date is None:
        base_date = (today or date.today()).strftime("%Y.%m.%d")
    adapter_cls = ADAPTERS.get(program)
    if adapter_cls is None:
        raise ConversionFailed([ValidationError("PROGRAM_UNSUPPORTED", "program")], "input")
    try:
        banks = BankCodeTable.from_workbook(load_workbook(template_path, read_only=False))
    except ValidationError as e:
        raise ConversionFailed([e], "template") from None
    except Exception:
        raise ConversionFailed([ValidationError("TEMPLATE_UNREADABLE", "template")], "template") from None
    try:
        adapted = adapter_cls(policy).read(input_path, password)
    except InputValidationFailed as e:
        raise ConversionFailed(e.errors, "input") from None
    try:
        validated = validate(adapted.batch, banks)
    except ValidationFailed as e:
        bad_rows = {x.row for x in e.errors if x.code.startswith("BANK_CODE_")}
        banks_to_fix = tuple(sorted({r.bank_name for r in adapted.batch.rows if r.source_row in bad_rows}))
        raise ConversionFailed(e.errors, "validate", banks_to_fix) from None
    try:
        wb = build_workbook(validated, template_path, policy, base_date)
    except ValidationFailed as e:
        raise ConversionFailed(e.errors, "template") from None

    warnings = list(adapted.warnings)
    b = validated.batch
    filename = f"{policy.file_prefix}_{b.program_code}_{b.year:04d}_{b.month:02d}.xlsx"
    try:
        path = save_new(wb, out_dir, filename, lambda tmp: verify_output(tmp, validated, adapted.source_totals))
    except ValidationFailed as e:
        raise ConversionFailed(e.errors, "output") from None
    return ConvertResult(output_path=path, count=len(validated.rows), warnings=tuple(warnings))
