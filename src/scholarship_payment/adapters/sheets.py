"""재단 원본의 데이터 시트 자동 탐색. **시트명은 판단 기준이 아니다**(재단이 내려받는 파일의 시트명은 달라질 수 있다).

기준은 각 Adapter 의 구조 검사(필수 머리글의 값과 위치, 필요한 병합 구조 전부)다. 낱말 하나(예: '학번')만 있다고 일치로 보지 않는다.
- 구조가 일치하는 시트가 **정확히 1개**일 때만 그 시트를 쓴다(숨김 시트와 앞뒤 위치에 상관없이 모든 워크시트가 후보이고, 차트 시트는 셀이 없어 후보가 아니다).
- 하나도 없으면 구조 오류로 차단한다. 후보가 워크시트 하나뿐이면 어디가 다른지 알 수 있게 그 시트의 구조 오류(`LAYOUT_*`, 위치 포함)를 그대로 돌려주고,
  여러 개면 `SHEET_NO_MATCH` 로 차단한다.
- 2개 이상이면 어느 쪽이 맞는지 알 수 없으므로 `SHEET_AMBIGUOUS` 로 차단한다. 시트명을 추정하거나 첫 시트를 쓰지 않는다.
오류에는 코드와 필드만 담고 시트명·값은 담지 않는다(DI-13).
"""
from __future__ import annotations

from collections.abc import Callable

from scholarship_payment.adapters.base import InputValidationFailed
from scholarship_payment.errors import ValidationError


def select_data_sheet(wb, layout_errors: Callable[[object], list[ValidationError]]):
    """`layout_errors(ws)` 가 빈 목록인 워크시트가 정확히 하나면 그것을 돌려주고, 아니면 InputValidationFailed."""
    checked = [(ws, layout_errors(ws)) for ws in wb.worksheets]
    matches = [ws for ws, errors in checked if not errors]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise InputValidationFailed([ValidationError("SHEET_AMBIGUOUS", "sheet")])
    if len(checked) == 1:
        raise InputValidationFailed(checked[0][1])          # 후보가 하나뿐: 기존처럼 어느 머리글·병합이 다른지 위치까지 알린다
    raise InputValidationFailed([ValidationError("SHEET_NO_MATCH", "sheet")])
