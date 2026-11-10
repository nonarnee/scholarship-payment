"""변환 오케스트레이션: Adapter → Validator → TemplateWriter → 출력 재검증 → 안전 저장.
GUI/명령줄은 `convert()`(기존 계약 그대로)를 호출한다. 업무 계산·변환 규칙은 여기 두지 않는다.

`convert()` = `finish(prepare(...), out_dir)`.
- `prepare()`: 은행코드 로드 → Adapter 파싱 → Validator 검증까지. **파일을 만들지 않고** 입력도 바꾸지 않는다(저장 위치 인자 없음).
- `finish()`: 파일 변경 감지(SHA-256) → 템플릿 레이아웃 검증을 포함한 Workbook 생성 → 출력 재검증 → 안전 저장.
  미리보기(prepare 결과)와 최종 출력은 같은 검증 결과(`Prepared`)를 쓰므로 인원·금액이 어긋나지 않는다.
- 변경 감지: 원본·템플릿(·정책 파일)의 SHA-256 을 `prepare()` 시점에 기록하고 `finish()` 직전에 다시 확인한다. 크기·수정 시각은 보조 정보일 뿐
  판단 기준이 아니다. 템플릿은 `finish()` 에서 **한 번 읽은 바이트로 해시를 확인하고 그 바이트로 Workbook 을 만든다**(검사와 사용 사이에 바뀔 틈이 없다).
  원본은 `prepare()` 가 읽는 동안 바뀌지 않았는지 읽기 전후 해시로 확인한다(Adapter 가 경로로 직접 연다).
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from scholarship_payment.adapters.base import InputValidationFailed
from scholarship_payment.adapters.daechung import DaechungAdapter
from scholarship_payment.adapters.multicultural import MulticulturalAdapter
from scholarship_payment.config.policy import SYNTHETIC_POLICY, OutputPolicy
from scholarship_payment.core.bank_codes import BankCodeTable
from scholarship_payment.errors import ValidationError, ValidationFailed
from scholarship_payment.io.safe_save import save_new, save_set
from scholarship_payment.adapters.base import SourceTotals
from scholarship_payment.validation.validator import ValidatedBatch, validate
from scholarship_payment.writers.output_check import verify_output, verify_split_set
from scholarship_payment.writers.template_writer import SPLIT_KINDS, SPLIT_SUFFIX, build_single_sheet_workbook, build_workbook

AI_HOURLY_RATE = 18000        # AI멘토링 시급 고정(사용자 결정 2026-11-04)

ADAPTERS = {
    "daechung": lambda policy: DaechungAdapter(),
    "ai": lambda policy: DaechungAdapter(program_code="AI", fixed_rate=AI_HOURLY_RATE),
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
class FileFingerprint:
    """파일 내용 지문. 판단 기준은 sha256 이며 size·mtime_ns 는 보조 정보다. repr 에 값을 싣지 않는다."""

    size: int
    mtime_ns: int
    sha256: str

    def __repr__(self) -> str:
        return "FileFingerprint()"


@dataclass(frozen=True)
class PolicySource:
    """정책 파일의 위치와 지문(정책 객체를 파일에서 읽은 쪽이 만든다). 변경 감지에만 쓰인다."""

    path: str | os.PathLike
    fingerprint: FileFingerprint


@dataclass(frozen=True)
class Issue:
    """경고·참고 1건(코드·필드·행 번호만). 예외 객체 대신 불변 값으로 보관한다."""

    code: str
    field: str
    row: int | None = None


def fingerprint_bytes(data: bytes) -> FileFingerprint:
    return FileFingerprint(len(data), 0, hashlib.sha256(data).hexdigest())


def fingerprint_file(path) -> FileFingerprint:
    """파일을 조각 단위로 읽어 SHA-256 을 계산한다. 읽을 수 없으면 OSError."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        size = 0
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
        mtime = os.fstat(f.fileno()).st_mtime_ns
    return FileFingerprint(size, mtime, h.hexdigest())


CHANGED_CODE, UNREADABLE_CODE = "INPUT_FILE_CHANGED", "INPUT_FILE_UNREADABLE"


def _probe(path) -> tuple[FileFingerprint | None, str]:
    """지문을 계산한다. 어떤 OSError 도 밖으로 내보내지 않고 상태로 돌려준다: ok / missing(없음) / unreadable(권한·잠금·입출력 오류).
    예외 문구에는 경로가 들어갈 수 있어 버린다."""
    try:
        return fingerprint_file(path), "ok"
    except FileNotFoundError:
        return None, "missing"
    except (OSError, TypeError, ValueError):
        return None, "unreadable"


def _try_fingerprint(path) -> FileFingerprint | None:
    return _probe(path)[0]


@dataclass(frozen=True, repr=False)
class Prepared:
    """`prepare()` 의 결과: 검증을 통과한 지급 데이터와 이를 만든 입력의 지문. 안에 든 것은 모두 불변 값이다
    (frozen dataclass·튜플·문자열·정수뿐). 비밀번호·Workbook·템플릿 바이트는 보관하지 않는다. repr·예외에 경로와 업무 값을 싣지 않는다."""

    program: str
    base_date: str                                  # prepare 에서 확정(finish 는 오늘 날짜를 다시 읽지 않는다)
    filename: str
    year: int
    month: int
    count: int
    total_amount: int                               # 정수 원
    warnings: tuple[Issue, ...]
    notes: tuple[Issue, ...]
    policy: OutputPolicy = field(repr=False)        # 정책 스냅샷(frozen, 튜플만 포함)
    source_fp: FileFingerprint = field(repr=False)
    template_fp: FileFingerprint = field(repr=False)
    policy_fp: FileFingerprint | None = field(repr=False)
    _validated: ValidatedBatch = field(repr=False)
    _source_totals: SourceTotals = field(repr=False)
    _source_path: str = field(repr=False)
    _template_path: str = field(repr=False)
    _policy_path: str | None = field(repr=False)

    def __repr__(self) -> str:
        return f"Prepared(program={self.program!r}, count={self.count})"


_ORDER = ("source", "template", "policy")


def _code_for(status: str) -> str:
    return CHANGED_CODE if status == "missing" else UNREADABLE_CODE


def _diagnose(prepared: Prepared, template_probe: tuple[str | None, str] | None = None) -> dict[str, str]:
    """원본·템플릿·(정책 파일)을 지문과 비교해 이상이 있는 이름 → 오류 코드. 삭제·내용 변경은 INPUT_FILE_CHANGED,
    권한·잠금 등으로 읽을 수 없으면 INPUT_FILE_UNREADABLE. template_probe 는 (sha256, 상태): finish 가 이미 읽은 바이트의 값이다."""
    out: dict[str, str] = {}
    cur, status = _probe(prepared._source_path)
    if cur is None:
        out["source"] = _code_for(status)
    elif cur.sha256 != prepared.source_fp.sha256:
        out["source"] = CHANGED_CODE
    if template_probe is None:
        t, status = _probe(prepared._template_path)
        template_probe = (t.sha256 if t else None, status)
    sha, status = template_probe
    if sha is None:
        out["template"] = _code_for(status)
    elif sha != prepared.template_fp.sha256:
        out["template"] = CHANGED_CODE
    if prepared.policy_fp is not None:
        p, status = _probe(prepared._policy_path)
        if p is None:
            out["policy"] = _code_for(status)
        elif p.sha256 != prepared.policy_fp.sha256:
            out["policy"] = CHANGED_CODE
    return {k: out[k] for k in _ORDER if k in out}


def diagnose_changes(prepared: Prepared) -> dict[str, str]:
    """미리보기 이후 이상이 생긴 입력 파일 이름 → 오류 코드(비어 있으면 지문이 모두 같다)."""
    return _diagnose(prepared)


def check_unchanged(prepared: Prepared) -> tuple[str, ...]:
    """미리보기 이후 바뀌었거나 사라졌거나 읽을 수 없게 된 입력 파일 이름. 비어 있으면 지문이 모두 같다."""
    return tuple(_diagnose(prepared))


@dataclass(frozen=True)
class ConvertResult:
    output_path: Path
    count: int
    warnings: tuple[ValidationError, ...]
    notes: tuple[ValidationError, ...] = ()
    output_paths: tuple[Path, ...] = ()       # 통합본: (output_path,) / 분리 모드: 명단·WINS·WRIS 파일 3개(output_path 는 그 폴더)


def prepare(program: str, input_path, template_path, policy: OutputPolicy = SYNTHETIC_POLICY,
            base_date: str | None = None, today: date | None = None, password: str | None = None,
            policy_source: PolicySource | None = None) -> Prepared:
    """은행코드 로드 → Adapter 파싱 → Validator 검증. 파일을 만들지 않는다. 오류 단계·코드는 기존 convert() 와 같다.
    base_date 미지정 시 기준일은 작성일(today, 기본 오늘) `YYYY.MM.DD` 로 **여기서 확정**한다."""
    if base_date is None:
        base_date = (today or date.today()).strftime("%Y.%m.%d")
    adapter_cls = ADAPTERS.get(program)
    if adapter_cls is None:
        raise ConversionFailed([ValidationError("PROGRAM_UNSUPPORTED", "program")], "input")
    try:
        template_bytes = Path(template_path).read_bytes()          # 한 번만 읽고, 이 바이트로 해시와 은행코드 표를 만든다
        template_fp = fingerprint_bytes(template_bytes)
        banks = BankCodeTable.from_workbook(load_workbook(BytesIO(template_bytes), read_only=False))
    except ValidationError as e:
        raise ConversionFailed([e], "template") from None
    except Exception:
        raise ConversionFailed([ValidationError("TEMPLATE_UNREADABLE", "template")], "template") from None
    mtime = _try_fingerprint(template_path)
    template_fp = FileFingerprint(template_fp.size, mtime.mtime_ns if mtime else 0, template_fp.sha256)
    source_before = _try_fingerprint(input_path)
    try:
        adapted = adapter_cls(policy).read(input_path, password)
    except InputValidationFailed as e:
        raise ConversionFailed(e.errors, "input") from None
    source_after = _try_fingerprint(input_path)
    if source_before is None and source_after is None:                       # 읽기는 됐지만 지문을 만들 수 없다 → 일관성을 보장할 수 없어 닫는다
        raise ConversionFailed([ValidationError("FILE_UNREADABLE", "file")], "input")
    if source_before is None or source_after is None or source_after.sha256 != source_before.sha256:
        raise ConversionFailed([ValidationError(CHANGED_CODE, "source")], "changed")   # 읽는 동안 원본이 바뀜
    try:
        validated = validate(adapted.batch, banks)
    except ValidationFailed as e:
        bad_rows = {x.row for x in e.errors if x.code.startswith("BANK_CODE_")}
        banks_to_fix = tuple(sorted({r.bank_name for r in adapted.batch.rows if r.source_row in bad_rows}))
        raise ConversionFailed(e.errors, "validate", banks_to_fix) from None

    b = validated.batch
    return Prepared(
        program=program, base_date=base_date,
        filename=f"{policy.file_prefix}_{b.program_code}_{b.year:04d}_{b.month:02d}.xlsx",
        year=b.year, month=b.month, count=len(validated.rows), total_amount=sum(r.row.pay_amount for r in validated.rows),
        warnings=tuple(Issue(w.code, w.field, w.row) for w in adapted.warnings),
        notes=tuple(Issue(n.code, n.field, n.row) for n in adapted.notes),
        policy=policy, source_fp=source_after, template_fp=template_fp,
        policy_fp=policy_source.fingerprint if policy_source else None,
        _validated=validated, _source_totals=adapted.source_totals,
        _source_path=os.fspath(input_path), _template_path=os.fspath(template_path),
        _policy_path=os.fspath(policy_source.path) if policy_source else None,
    )


def finish(prepared: Prepared, out_dir, split: bool = False) -> ConvertResult:
    """파일 변경 확인 → Workbook 생성(템플릿 레이아웃 검증 포함) → 출력 재검증 → 안전 저장.
    입력이 하나라도 바뀌었으면 아무 것도 만들지 않고 `ConversionFailed(stage="changed")` 로 멈춘다(자동으로 다시 읽지 않는다).
    `split=True` 이면 통합본 대신 명단·WINS·WRIS 를 각각 1개 시트 파일로 만들어 새 하위 폴더 하나에 공개한다(전부 검증을 통과해야만 공개)."""
    try:
        data = Path(prepared._template_path).read_bytes()
        template_probe = (fingerprint_bytes(data).sha256, "ok")
    except FileNotFoundError:
        data, template_probe = None, (None, "missing")
    except (OSError, TypeError, ValueError):
        data, template_probe = None, (None, "unreadable")
    problems = _diagnose(prepared, template_probe)
    if problems:
        raise ConversionFailed([ValidationError(code, name) for name, code in problems.items()], "changed")
    to_error = lambda i: ValidationError(i.code, i.field, i.row)  # noqa: E731
    warnings, notes = tuple(map(to_error, prepared.warnings)), tuple(map(to_error, prepared.notes))
    if split:
        try:
            books = {k: build_single_sheet_workbook(prepared._validated, BytesIO(data), prepared.policy, prepared.base_date, k) for k in SPLIT_KINDS}   # 해시를 확인한 바이트를 파일마다 새로 읽는다
        except ValidationFailed as e:
            raise ConversionFailed(e.errors, "template") from None
        try:
            folder, files = save_set(books, out_dir, Path(prepared.filename).stem, SPLIT_SUFFIX,
                                     lambda paths: verify_split_set(paths, prepared._validated, prepared._source_totals))
        except ValidationFailed as e:
            raise ConversionFailed(e.errors, "output") from None
        return ConvertResult(output_path=folder, count=prepared.count, warnings=warnings, notes=notes, output_paths=tuple(files[k] for k in SPLIT_KINDS))
    try:
        wb = build_workbook(prepared._validated, BytesIO(data), prepared.policy, prepared.base_date)   # 해시를 확인한 바로 그 바이트
    except ValidationFailed as e:
        raise ConversionFailed(e.errors, "template") from None
    try:
        path = save_new(wb, out_dir, prepared.filename, lambda tmp: verify_output(tmp, prepared._validated, prepared._source_totals))
    except ValidationFailed as e:
        raise ConversionFailed(e.errors, "output") from None
    return ConvertResult(output_path=path, count=prepared.count, warnings=warnings, notes=notes, output_paths=(path,))


def convert(program: str, input_path, out_dir, template_path, policy: OutputPolicy = SYNTHETIC_POLICY,
            base_date: str | None = None, today: date | None = None,
            password: str | None = None) -> ConvertResult:
    """기존 계약 그대로: `finish(prepare(...), out_dir)`. base_date 미지정 시 기준일은 작성일(today, 기본 오늘) `YYYY.MM.DD` (사용자 결정)."""
    return finish(prepare(program, input_path, template_path, policy, base_date, today, password), out_dir)
