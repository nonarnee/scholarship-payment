"""은행코드 표. 은행명 **정확 일치**만 허용하고 WINS·WRIS를 각각 판정한다.
없거나 모호하면(같은 이름에 서로 다른 값/공란이 섞임) 오류로 차단한다. 추정·유사 매칭은 하지 않는다.
오류에는 규칙 코드·필드만 담는다(은행명 같은 값 금지, DI-13).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from scholarship_payment.errors import ValidationError

SHEET_NAME = "은행코드"
FIRST_DATA_ROW = 2          # 1행은 머리글
NAME_COL, WINS_COL, WRIS_COL = 2, 3, 4      # B, C, D
_FIELDS = {"wins": "wins_bank_code", "wris": "wris_bank_code"}


@dataclass(frozen=True)
class BankCodes:
    wins: int | str
    wris: int | str


def _code(value: object) -> int | str | None:
    """공란은 None. 숫자/문자열 코드는 셀 타입 그대로 둔다(선행 0 보존)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value.strip() or None
    return None


class BankCodeTable:
    def __init__(self, entries: Iterable[tuple[object, object, object]]) -> None:
        self._rows: dict[str, list[tuple[int | str | None, int | str | None]]] = {}
        for name, wins, wris in entries:
            if not isinstance(name, str) or not name.strip():
                continue
            self._rows.setdefault(name.strip(), []).append((_code(wins), _code(wris)))

    @classmethod
    def from_workbook(cls, wb) -> BankCodeTable:
        if SHEET_NAME not in wb.sheetnames:
            raise ValidationError("BANK_SHEET_MISSING", "bank_sheet")
        ws = wb[SHEET_NAME]
        return cls(
            (ws.cell(r, NAME_COL).value, ws.cell(r, WINS_COL).value, ws.cell(r, WRIS_COL).value)
            for r in range(FIRST_DATA_ROW, ws.max_row + 1)
        )

    def resolve(self, bank_name: str, system: str) -> int | str:
        if system not in _FIELDS:
            raise ValueError("system must be 'wins' or 'wris'")
        field = _FIELDS[system]
        rows = self._rows.get(bank_name.strip()) if isinstance(bank_name, str) else None
        if not rows:
            raise ValidationError("BANK_CODE_MISSING", field)
        idx = 0 if system == "wins" else 1
        values = [row[idx] for row in rows]
        if len({(type(v).__name__, v) for v in values}) > 1:
            raise ValidationError("BANK_CODE_AMBIGUOUS", field)
        if values[0] is None:
            raise ValidationError("BANK_CODE_MISSING", field)
        return values[0]

    def codes(self, bank_name: str) -> BankCodes:
        return BankCodes(wins=self.resolve(bank_name, "wins"), wris=self.resolve(bank_name, "wris"))
