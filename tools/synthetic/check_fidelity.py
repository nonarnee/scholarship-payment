#!/usr/bin/env python3
"""합성 입력(생성기 출력)이 실제 다운로드 원본과 **구조적으로 같은지** 비교한다. 로컬 수동 실행 전용.

사용: .venv/bin/python -I tools/synthetic/check_fidelity.py <실제 월별지급승인.xlsx>

- 실제 파일은 읽기 전용으로 열고 저장하지 않는다. CI·공개 pytest에는 넣지 않는다(실자료가 필요).
- **차이가 있는 항목만** 출력한다. 값(성명·학번·계좌 등)은 출력하지 않고, 형태(자릿수→#, 한글→가)와 타입만 비교한다.
- 새 월의 원본을 받았을 때도 같은 도구로 형태 변화를 점검한다.
- 결과의 상세는 공개 문서·커밋에 옮기지 않는다(`docs/PUBLIC-SAFETY.md`).
"""
import importlib.util
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mk", ROOT / "tools" / "synthetic" / "make_synthetic.py")
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)

DATA_FIRST_ROW = 3
SHAPE_COLS = "DFHKLMNOPQRSTUVWX"     # 형태를 비교할 열(값 자체는 비교·출력하지 않는다)


def shape(v):
    if v is None:
        return "None"
    s = re.sub(r"[가-힣]", "가", re.sub(r"\d", "#", str(v)))
    return s if len(s) <= 24 else s[:24] + "…"


def column_kind(v):
    return type(v).__name__


def signature(ws):
    """구조 서명: 값은 담지 않고 형태·타입·위치만 담는다."""
    sig = {"sheet": ws.title, "dims": None, "merges": sorted(str(m) for m in ws.merged_cells.ranges)}
    # 데이터 행 범위: 순번(C)이 int 인 연속 행
    last = DATA_FIRST_ROW - 1
    while isinstance(ws[f"C{last + 1}"].value, int):
        last += 1
    sig["data_rows"] = (DATA_FIRST_ROW, last)
    sig["total_row"] = last + 1
    sig["max_row"], sig["max_col"] = ws.max_row, ws.max_column
    sig["hidden_cols"] = sorted(k for k, d in ws.column_dimensions.items() if d.hidden or d.width == 0)
    sig["headers"] = {c.coordinate: str(c.value) for r in (1, 2) for c in ws[r] if c.value is not None}
    types, shapes = {}, {}
    for col in "ABCDEFGHIJKLMNOPQRSTUVWX":
        cells = [ws[f"{col}{r}"].value for r in range(DATA_FIRST_ROW, last + 1)]
        types[col] = dict(Counter(column_kind(v) for v in cells))
        if col in SHAPE_COLS:
            shapes[col] = dict(Counter(shape(v) for v in cells).most_common(3)) if col in "DM" else \
                sorted({shape(v) for v in cells})[:3]
    sig["types"], sig["shapes"] = types, shapes
    tr = sig["total_row"]
    sig["total_row_types"] = {c.column_letter: column_kind(c.value) for c in ws[tr] if c.value is not None}
    sig["total_label_shape"] = shape(ws[f"F{tr}"].value)
    return sig


def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a:
                out.append(f"{path}/{k}: 실제에 없음, 합성에만 있음")
            elif k not in b:
                out.append(f"{path}/{k}: 합성에 없음, 실제에만 있음")
            else:
                out += diff(a[k], b[k], f"{path}/{k}")
    elif a != b:
        out.append(f"{path}: 실제={a!r} 합성={b!r}")
    return out


def main(argv):
    if len(argv) != 1:
        sys.exit(__doc__)
    real_wb = load_workbook(argv[0], read_only=False, data_only=True)
    real = signature(real_wb["월별지급승인"])
    n = real["data_rows"][1] - real["data_rows"][0] + 1
    with tempfile.TemporaryDirectory() as tmp:             # 저장·재로드를 거쳐야 실제 파일과 같은 조건으로 비교된다
        path = Path(tmp) / "syn.xlsx"
        mk.save_input(path, n, "numeric")
        syn = signature(load_workbook(path, data_only=True)["월별지급승인"])
    # 합성은 자리표시 값이므로 값 형태(shape)는 같은 규칙으로 변환한 결과끼리만 비교한다.
    diffs = diff(real, syn)
    if not diffs:
        print("구조 서명 일치: 차이 없음")
        return 0
    print(f"구조 서명 차이 {len(diffs)}건 (값은 출력하지 않음)")
    for d in diffs:
        print("  -", d)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
