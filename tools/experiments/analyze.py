"""읽기 전용 템플릿 분석. 개인정보 값은 출력하지 않고 구조/타입/형식만 요약한다.
사용: python analyze.py <xlsx>
"""
import sys, re, collections
from openpyxl import load_workbook

path = sys.argv[1]
wb = load_workbook(path)  # 메모리에서만 사용, 저장하지 않는다


def sty(c):
    f, fl, b, a = c.font, c.fill, c.border, c.alignment
    fg = fl.fgColor.rgb if fl and fl.fill_type else None
    if fl and fl.fill_type and fl.fgColor.type == "theme":
        fg = f"theme{fl.fgColor.theme}"
    bd = "".join(
        (s.style or "-")[0] if (s := getattr(b, side)) else "-"
        for side in ("left", "right", "top", "bottom")
    )
    return (
        c.style_id, f.name, f.sz, "B" if f.b else "", fg, bd,
        a.horizontal, a.vertical, "wrap" if a.wrap_text else "", c.number_format,
    )


print("== 파일:", path.split("/")[-1][:20], "| openpyxl", __import__("openpyxl").__version__)
print("정의된 이름:", {k: v.attr_text for k, v in wb.defined_names.items()})
for ws in wb.worksheets:
    print(f"\n--- 시트 {ws.title!r} state={ws.sheet_state} dim={ws.dimensions} tab={ws.sheet_properties.tabColor.rgb if ws.sheet_properties.tabColor else None}")
    print(" sheet 정의 이름:", {k: v.attr_text for k, v in ws.defined_names.items()})
    print(" 병합:", sorted(str(m) for m in ws.merged_cells.ranges))
    print(" print_area:", ws.print_area, "| title_rows:", ws.print_title_rows, "| title_cols:", ws.print_title_cols)
    ps, pm = ws.page_setup, ws.page_margins
    print(" page_setup:", dict(orientation=ps.orientation, paperSize=ps.paperSize, scale=ps.scale, fitToWidth=ps.fitToWidth, fitToHeight=ps.fitToHeight),
          "| margins:", (pm.left, pm.right, pm.top, pm.bottom), "| fitToPage:", ws.sheet_properties.pageSetUpPr.fitToPage if ws.sheet_properties.pageSetUpPr else None)
    print(" freeze:", ws.freeze_panes, "| autofilter:", ws.auto_filter.ref, "| header/footer:", bool(ws.oddHeader.center.text or ws.oddFooter.center.text))
    print(" row_breaks:", len(ws.row_breaks.brk), "col_breaks:", len(ws.col_breaks.brk))
    cf = [(str(k.sqref), [r.type for r in v]) for k, v in ws.conditional_formatting._cf_rules.items()]
    print(" 조건부서식:", cf)
    print(" 데이터검증:", len(ws.data_validations.dataValidation) if ws.data_validations else 0)
    hidden_r = [r for r, d in ws.row_dimensions.items() if d.hidden]
    hidden_c = [c for c, d in ws.column_dimensions.items() if d.hidden or d.width == 0]
    print(" 숨김 행:", hidden_r, "| 숨김/0폭 열:", hidden_c)
    ht = collections.Counter((d.height, d.customHeight) for r, d in ws.row_dimensions.items())
    print(" 행 높이 분포(height,custom):count:", dict(ht), "| default:", ws.sheet_format.defaultRowHeight)
    print(" 열 너비:", {k: (round(d.width, 2) if d.width else None, d.min, d.max) for k, d in sorted(ws.column_dimensions.items())})

    # 수식/타입 요약
    forms, types = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    ref_sheets = collections.Counter()
    for row in ws.iter_rows():
        for c in row:
            if c.value is None:
                continue
            col = c.column_letter
            if isinstance(c.value, str) and c.value.startswith("="):
                forms[col][re.sub(r"\d+", "#", c.value)] += 1
                for m in re.findall(r"'([^']+)'!|(\w+)!", c.value):
                    ref_sheets[m[0] or m[1]] += 1
            types[col][(c.data_type, c.number_format)] += 1
    print(" 수식 열 패턴:", {k: dict(v) for k, v in forms.items()})
    print(" 수식이 참조하는 시트:", dict(ref_sheets))
    print(" 열별 (data_type, number_format) 분포:")
    for k in sorted(types, key=lambda x: (len(x), x)):
        print("   ", k, dict(types[k]))

    # 대표 스타일: 헤더/데이터/합계 행
    rows_of_interest = []
    if ws.title.startswith("지급대상자명단"):
        rows_of_interest = [1, 2, 3, 4, 5, 6, 49, 50]
    elif ws.title in ("WINS", "WRIS"):
        rows_of_interest = [1, 2, ws.max_row]
    elif ws.title == "월별지급승인":
        rows_of_interest = [1, 2, 3, 47, 48]
    for r in rows_of_interest:
        print(f" [행 {r}] style:", [(c.coordinate, *sty(c)) for c in ws[r] if c.has_style][:6], "...")
    # 스타일 균일성: 데이터 구간에서 열별 style_id 가 단일한가
    if ws.title.startswith("지급대상자명단"):
        for col in "ABDIKLNPQ":
            ids = {ws[f"{col}{r}"].style_id for r in range(5, 50)}
            print(f"  명단 {col}열 데이터행 style_id 종류:", len(ids))
