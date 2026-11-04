"""엑셀 출력의 **의미 있는 내용**을 정규화해 비교하는 도구(바이너리 SHA 는 쓰지 않는다: 압축·시각 메타데이터가 달라질 수 있음).
비교 항목: 시트 순서·이름·상태, 셀 값·타입·수식, 숫자 서식, 글꼴·채움·테두리·정렬·보호, 병합, 행 높이·숨김, 열 너비·숨김, 틀 고정,
조건부 서식, 데이터 유효성, 인쇄 설정(영역·제목행·용지·배율·여백·머리글/바닥글), 정의된 이름. 작성·수정 일시 같은 휘발성 값은 제외한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import load_workbook


def _color(c):
    if c is None:
        return None
    return [c.type, str(c.rgb) if c.type == "rgb" else str(c.theme) if c.type == "theme" else str(c.indexed), c.tint]


def _font(f):
    return [f.name, f.sz, f.b, f.i, f.u, f.strike, _color(f.color), f.vertAlign]


def _fill(f):
    return [f.fill_type, _color(f.fgColor) if f.fill_type else None, _color(f.bgColor) if f.fill_type else None]


def _side(s):
    return [s.style, _color(s.color)] if s is not None and s.style else None


def _border(b):
    return [_side(b.left), _side(b.right), _side(b.top), _side(b.bottom)]


def _cell(c):
    return [c.coordinate, type(c.value).__name__, repr(c.value), c.data_type, c.number_format, _font(c.font), _fill(c.fill), _border(c.border),
            [c.alignment.horizontal, c.alignment.vertical, c.alignment.wrap_text, c.alignment.indent], [c.protection.locked, c.protection.hidden]]


def _sheet(ws):
    cells = [_cell(c) for row in ws.iter_rows() for c in row if c.value is not None or c.has_style]
    cond = []
    for rng, rules in ws.conditional_formatting._cf_rules.items():
        for r in rules:
            dxf = r.dxf
            cond.append([str(rng.sqref), r.type, r.operator, list(r.formula or []), r.priority,
                         _font(dxf.font) if dxf is not None and dxf.font is not None else None, _fill(dxf.fill) if dxf is not None and dxf.fill is not None else None])
    dv = [[str(d.sqref), d.type, d.operator, d.formula1, d.formula2, d.allow_blank] for d in ws.data_validations.dataValidation] if ws.data_validations else []
    ps, pm, po = ws.page_setup, ws.page_margins, ws.print_options
    hf = ws.HeaderFooter
    return {
        "title": ws.title, "state": ws.sheet_state, "dims": ws.dimensions, "freeze": ws.freeze_panes,
        "cells": cells, "merged": sorted(str(m) for m in ws.merged_cells.ranges),
        "row_dims": sorted([r, d.height, d.hidden, d.outlineLevel] for r, d in ws.row_dimensions.items() if d.height is not None or d.hidden or d.outlineLevel),
        "col_dims": sorted([k, d.min, d.max, d.width, d.hidden, d.outlineLevel, d.customWidth] for k, d in ws.column_dimensions.items()),
        "cond": sorted(cond, key=repr), "validations": sorted(dv, key=repr),
        "print": {"area": ws.print_area, "title_rows": ws.print_title_rows, "title_cols": ws.print_title_cols,
                  "page": [ps.orientation, ps.paperSize, ps.scale, ps.fitToWidth, ps.fitToHeight],
                  "fit": ws.sheet_properties.pageSetUpPr.fitToPage if ws.sheet_properties.pageSetUpPr else None,
                  "margins": [pm.left, pm.right, pm.top, pm.bottom, pm.header, pm.footer],
                  "options": [po.horizontalCentered, po.verticalCentered, po.gridLines, po.headings],
                  "header_footer": [hf.oddHeader.center.text, hf.oddFooter.center.text, hf.oddHeader.left.text, hf.oddFooter.left.text]},
    }


def dump(path) -> dict:
    wb = load_workbook(path)                       # 수식은 수식 그대로(data_only 아님)
    names = sorted(f"{n}={wb.defined_names[n].attr_text}" for n in wb.defined_names)
    return {"sheet_order": list(wb.sheetnames), "defined_names": names, "sheets": [_sheet(ws) for ws in wb.worksheets]}


def write_golden(d: dict, path: Path) -> None:
    """사람이 diff 로 읽을 수 있게 셀 1개를 한 줄로 쓴다."""
    lines = ["{"]
    for k in ("case", "filename", "count", "warnings", "notes", "sheet_order", "defined_names"):
        if k in d:
            lines.append(f"  {json.dumps(k)}: {json.dumps(d[k], ensure_ascii=False)},")
    lines.append('  "sheets": [')
    for i, sh in enumerate(d["sheets"]):
        lines.append("   {")
        for k, v in sh.items():
            if k == "cells":
                lines.append('    "cells": [')
                lines.extend("     " + json.dumps(c, ensure_ascii=False) + ("," if j < len(v) - 1 else "") for j, c in enumerate(v))
                lines.append("    ],")
            else:
                lines.append(f"    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
        lines[-1] = lines[-1].rstrip(",")
        lines.append("   }" + ("," if i < len(d["sheets"]) - 1 else ""))
    lines.append("  ]")
    lines.append("}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def diff(a: dict, b: dict) -> list[str]:
    """어디가 다른지만 알려 준다(시트·좌표·항목 이름. 값은 합성이지만 출력하지 않는다)."""
    out = []
    for k in ("sheet_order", "defined_names", "filename", "count", "warnings", "notes"):
        if a.get(k) != b.get(k):
            out.append(f"top:{k}")
    for sa, sb in zip(a["sheets"], b["sheets"]):
        for k in sa:
            if sa[k] == sb.get(k):
                continue
            if k == "cells":
                ca, cb = {c[0]: c for c in sa[k]}, {c[0]: c for c in sb[k]}
                for coord in sorted(set(ca) | set(cb)):
                    if ca.get(coord) != cb.get(coord):
                        idx = next((i for i, (x, y) in enumerate(zip(ca.get(coord, []), cb.get(coord, []))) if x != y), -1)
                        out.append(f"{sa['title']}!{coord}[col{idx}]")
                        if len(out) > 40:
                            return out
            else:
                out.append(f"{sa['title']}:{k}")
    if len(a["sheets"]) != len(b["sheets"]):
        out.append("sheet_count")
    return out
