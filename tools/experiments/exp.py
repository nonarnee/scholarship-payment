"""템플릿 확장·축소 실험 (방식 A: 행 삽입/삭제, 방식 B: 스타일 복제 후 블록 재구성).
합성 데이터만 사용한다. 결과 xlsx는 스크래치 exp_out/ 에만 저장한다.
사용: python exp.py <template.xlsx> <out_dir>
"""
import sys, os, re, copy, json, zipfile, hashlib
from openpyxl import load_workbook
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.formatting.rule import Rule

TEMPLATE, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
LIST = "지급대상자명단(9월)"
HISTORY = "업로드 결과(이력)"
TPL_N = 45                      # 템플릿 데이터 행 수
LIST_FIRST, LIST_TOTAL = 5, 50  # 명단 첫 데이터 행 / 합계 행(템플릿)
SIDE_FIRST = 2                  # WINS/WRIS 첫 데이터 행


# ---------------------------------------------------------------- 합성 데이터
def fmt_min(m):
    h, mm = divmod(m, 60)
    return f"{h}시간" if mm == 0 else f"{h}시간{mm}분"


def bank_table(wb):
    ws = wb["은행코드"]
    out = {}
    for r in range(2, ws.max_row + 1):
        name, w, s = ws.cell(r, 2).value, ws.cell(r, 3).value, ws.cell(r, 4).value
        if name and w not in (None, "") and s not in (None, ""):
            out.setdefault(name, (w, s))
    return out


def synth(n, banks):
    names = list(banks)[:3]
    mins = [33 * 60, 14 * 60 + 30, 10 * 60, 32 * 60, 55 * 60 + 15]
    rows = []
    for i in range(1, n + 1):
        m = mins[i % len(mins)]
        rate = 10320
        rows.append(dict(
            seq=i, ym="202609", name=f"가상{i:03d}", sid=f"{i:08d}",  # 선행 0 포함
            dept="가상학과", biz=f"000-00-{i:05d}", org="가상기관", place="가상근로지",
            heads=(i % 11) + 1, rate=rate, minutes=m, text=fmt_min(m),
            pay=round(rate * m / 60), bank=names[i % 3], acct=f"000-000-{i:06d}",
        ))
    return rows


# ---------------------------------------------------------------- 값 기록
def sid_val(s, mode):
    return s if mode == "str" else int(s)


def fill_list_row(ws, r, d, banks, mode):
    v = {"A": d["seq"], "B": d["ym"], "C": d["name"], "D": sid_val(d["sid"], mode), "E": d["dept"],
         "F": d["biz"], "G": d["org"], "H": d["place"], "I": d["heads"], "J": d["rate"], "K": d["text"],
         "L": d["pay"], "M": d["bank"], "P": d["acct"]}
    for col, val in v.items():
        ws[f"{col}{r}"] = val
    ws[f"N{r}"] = f"=VLOOKUP(M{r},은행코드!$B$2:$C$79,2,0)"
    ws[f"O{r}"] = f"=VLOOKUP(M{r},은행코드!$B$2:$D$79,3,0)"


def fill_list_total(ws, r, rows):
    ws[f"K{r}"] = fmt_min(sum(d["minutes"] for d in rows))
    ws[f"L{r}"] = sum(d["pay"] for d in rows)


def fill_wins_row(ws, r, d, banks, mode):
    ws[f"A{r}"], ws[f"B{r}"], ws[f"C{r}"] = "SYN-근로구분", 2099, 9
    ws[f"D{r}"] = sid_val(d["sid"], mode)
    ws[f"E{r}"] = ws[f"F{r}"] = None
    ws[f"G{r}"], ws[f"H{r}"], ws[f"I{r}"] = d["pay"], banks[d["bank"]][0], d["acct"]


def fill_wris_row(ws, r, d, banks, mode):
    ws[f"A{r}"], ws[f"B{r}"] = "SYN-GUB-A", "SYN-GUB-B"
    ws[f"C{r}"] = sid_val(d["sid"], mode)
    ws[f"D{r}"], ws[f"E{r}"] = d["name"], d["pay"]
    ws[f"F{r}"], ws[f"G{r}"], ws[f"H{r}"] = str(banks[d["bank"]][1]), d["acct"], d["name"]
    ws[f"I{r}"], ws[f"J{r}"] = "가상사업(9월)", None


# ---------------------------------------------------------------- 방식 A
def approach_A(n, rows, banks, mode):
    wb = load_workbook(TEMPLATE)
    wb.remove(wb[HISTORY])
    ws = wb[LIST]
    if n < TPL_N:
        ws.delete_rows(LIST_FIRST + n, TPL_N - n)
    elif n > TPL_N:
        ws.insert_rows(LIST_TOTAL, n - TPL_N)
    for i, d in enumerate(rows):
        fill_list_row(ws, LIST_FIRST + i, d, banks, mode)
    fill_list_total(ws, LIST_FIRST + n, rows)
    for name, fn in (("WINS", fill_wins_row), ("WRIS", fill_wris_row)):
        s = wb[name]
        if n < TPL_N:
            s.delete_rows(SIDE_FIRST + n, TPL_N - n)
        elif n > TPL_N:
            s.insert_rows(SIDE_FIRST + TPL_N, n - TPL_N)
        for i, d in enumerate(rows):
            fn(s, SIDE_FIRST + i, d, banks, mode)
    return wb


# ---------------------------------------------------------------- 방식 B
def snap(ws, r, ncol):
    return ([copy.copy(ws.cell(r, c)._style) for c in range(1, ncol + 1)], ws.row_dimensions[r].height)


def apply(ws, r, s):
    styles, h = s
    for c, st in enumerate(styles, 1):
        ws.cell(r, c)._style = copy.copy(st)
    if h is not None:
        ws.row_dimensions[r].height = h


def wipe_below(ws, first_row):
    ws.delete_rows(first_row, ws.max_row - first_row + 1)
    for r in [r for r in ws.row_dimensions if r >= first_row]:
        del ws.row_dimensions[r]


def approach_B(n, rows, banks, mode):
    wb = load_workbook(TEMPLATE)
    wb.remove(wb[HISTORY])
    ws = wb[LIST]
    first, mid, total = snap(ws, 5, 17), snap(ws, 6, 17), snap(ws, 50, 17)
    dxf = None
    for cf in ws.conditional_formatting:
        for rule in cf.rules:
            dxf = dxf or rule.dxf
    wipe_below(ws, LIST_FIRST)
    ws.conditional_formatting = ConditionalFormattingList()
    for i, d in enumerate(rows):
        r = LIST_FIRST + i
        apply(ws, r, first if i == 0 else mid)
        fill_list_row(ws, r, d, banks, mode)
    apply(ws, LIST_FIRST + n, total)
    fill_list_total(ws, LIST_FIRST + n, rows)
    ws.conditional_formatting.add(f"D{LIST_FIRST}:D{LIST_FIRST + n - 1}",
                                  Rule(type="duplicateValues", dxf=dxf))
    for name, fn in (("WINS", fill_wins_row), ("WRIS", fill_wris_row)):
        s = wb[name]
        ncol = 9 if name == "WINS" else 10
        f, m = snap(s, 2, ncol), snap(s, 3, ncol)
        sdxf = None
        for cf in s.conditional_formatting:
            for rule in cf.rules:
                sdxf = sdxf or rule.dxf
        wipe_below(s, SIDE_FIRST)
        s.conditional_formatting = ConditionalFormattingList()
        for i, d in enumerate(rows):
            apply(s, SIDE_FIRST + i, f if i == 0 else m)
            fn(s, SIDE_FIRST + i, d, banks, mode)
        col = "D" if name == "WINS" else "C"
        s.conditional_formatting.add(f"{col}{SIDE_FIRST}:{col}{SIDE_FIRST + n - 1}",
                                     Rule(type="duplicateValues", dxf=sdxf))
    return wb


# ---------------------------------------------------------------- 비교
def sig(c):
    f, fl, b, a = c.font, c.fill, c.border, c.alignment
    fg = None
    if fl and fl.fill_type:
        fg = (fl.fgColor.type, fl.fgColor.rgb if fl.fgColor.type == "rgb" else fl.fgColor.theme)
    bd = tuple((getattr(b, s).style if getattr(b, s) else None) for s in ("left", "right", "top", "bottom"))
    return (f.name, f.sz, bool(f.b), fg, bd, a.horizontal, a.vertical, bool(a.wrap_text), c.number_format)


def parts(path):
    return set(zipfile.ZipFile(path).namelist())


def compare(tpl_wb, out_path, n, rows, mode, tpl_path):
    res = {}
    out = load_workbook(out_path)
    t = tpl_wb
    res["sheets"] = out.sheetnames
    # ---- 명단
    to, ts = out[LIST], t[LIST]
    ncol = 17
    res["list.merges_same"] = sorted(map(str, to.merged_cells.ranges)) == sorted(map(str, ts.merged_cells.ranges))
    res["list.col_widths_same"] = {k: v.width for k, v in to.column_dimensions.items()} == {k: v.width for k, v in ts.column_dimensions.items()}
    res["list.header_style_same(r1-4)"] = all(sig(to.cell(r, c)) == sig(ts.cell(r, c)) for r in range(1, 5) for c in range(1, ncol + 1))
    res["list.header_heights_same"] = all(to.row_dimensions[r].height == ts.row_dimensions[r].height for r in range(1, 5))
    mism = 0
    for i in range(n):
        r = LIST_FIRST + i
        ref = 5 if i == 0 else 6
        for c in range(1, ncol + 1):
            if sig(to.cell(r, c)) != sig(ts.cell(ref, c)):
                mism += 1
    res["list.data_style_mismatch_cells"] = f"{mism}/{n * ncol}"
    res["list.data_row_height_ok"] = sum(1 for i in range(n) if to.row_dimensions[LIST_FIRST + i].height == 14.1)
    tr = LIST_FIRST + n
    res["list.total_row"] = tr
    res["list.total_style_same"] = all(sig(to.cell(tr, c)) == sig(ts.cell(LIST_TOTAL, c)) for c in range(1, ncol + 1))
    res["list.total_height"] = to.row_dimensions[tr].height
    res["list.total_values"] = (to[f"K{tr}"].value == fmt_min(sum(d["minutes"] for d in rows)),
                                to[f"L{tr}"].value == sum(d["pay"] for d in rows))
    # 잔여 데이터/서식(합계 행 아래)
    left = [(c.coordinate) for row in to.iter_rows(min_row=tr + 1) for c in row if c.value is not None]
    res["list.leftover_values_below_total"] = len(left)
    res["list.leftover_styled_rows_below_total"] = sum(1 for r in to.row_dimensions if r > tr and to.row_dimensions[r].height not in (None, 16.5))
    res["list.dim"] = to.dimensions
    cfr = [str(k.sqref) for k in to.conditional_formatting]
    res["list.cf_ranges"] = cfr if len(cfr) <= 3 else f"{len(cfr)} ranges (fragmented)"
    res["list.autofilter"] = to.auto_filter.ref
    res["list.formula_rows_ok"] = sum(1 for i in range(n) if to[f"N{LIST_FIRST + i}"].value == f"=VLOOKUP(M{LIST_FIRST + i},은행코드!$B$2:$C$79,2,0)")
    res["list.page_setup_same"] = (to.page_setup.orientation, to.page_setup.paperSize, to.page_margins.left) == (ts.page_setup.orientation, ts.page_setup.paperSize, ts.page_margins.left)
    res["list.tab_color_same"] = (to.sheet_properties.tabColor.rgb if to.sheet_properties.tabColor else None) == (ts.sheet_properties.tabColor.rgb if ts.sheet_properties.tabColor else None)
    # ---- WINS / WRIS
    for name, ncol_, idcol in (("WINS", 9, "D"), ("WRIS", 10, "C")):
        so, st = out[name], t[name]
        mm = 0
        for i in range(n):
            r = SIDE_FIRST + i
            ref = 2 if i == 0 else 3
            for c in range(1, ncol_ + 1):
                if sig(so.cell(r, c)) != sig(st.cell(ref, c)):
                    mm += 1
        res[f"{name}.data_style_mismatch_cells"] = f"{mm}/{n * ncol_}"
        res[f"{name}.header_same"] = all(sig(so.cell(1, c)) == sig(st.cell(1, c)) for c in range(1, ncol_ + 1))
        res[f"{name}.rows"] = sum(1 for r in range(SIDE_FIRST, so.max_row + 1) if so[f"{idcol}{r}"].value is not None)
        res[f"{name}.leftover_below"] = sum(1 for row in so.iter_rows(min_row=SIDE_FIRST + n) for c in row if c.value is not None)
        res[f"{name}.height_ok"] = sum(1 for i in range(n) if so.row_dimensions[SIDE_FIRST + i].height == 14.1)
        res[f"{name}.formulas"] = sum(1 for row in so.iter_rows() for c in row if c.data_type == "f")
        res[f"{name}.col_widths_same"] = {k: v.width for k, v in so.column_dimensions.items()} == {k: v.width for k, v in st.column_dimensions.items()}
        cfr = [str(k.sqref) for k in so.conditional_formatting]
        res[f"{name}.cf"] = cfr if len(cfr) <= 3 else f"{len(cfr)} ranges"
    # ---- 교차 일치(합성 데이터)
    L, W, R = out[LIST], out["WINS"], out["WRIS"]
    ok = True
    for i, d in enumerate(rows):
        a, b, c = LIST_FIRST + i, SIDE_FIRST + i, SIDE_FIRST + i
        ok &= str(L[f"D{a}"].value) == str(W[f"D{b}"].value) == str(R[f"C{c}"].value)
        ok &= L[f"L{a}"].value == W[f"G{b}"].value == R[f"E{c}"].value == d["pay"]
        ok &= L[f"P{a}"].value == W[f"I{b}"].value == R[f"G{c}"].value
    res["cross_check_list_wins_wris"] = bool(ok)
    # ---- 식별자 타입
    res["sid_cell_type"] = sorted({L[f"D{LIST_FIRST + i}"].data_type for i in range(n)})
    res["sid_preserves_source_string"] = all(str(L[f"D{LIST_FIRST + i}"].value) == d["sid"] for i, d in enumerate(rows))
    res["acct_cell_type"] = sorted({L[f"P{LIST_FIRST + i}"].data_type for i in range(n)})
    # ---- 패키지
    po, pt = parts(out_path), parts(tpl_path)
    res["parts_lost"] = sorted(re.sub(r"\d+", "#", p) for p in pt - po)
    res["parts_added"] = sorted(re.sub(r"\d+", "#", p) for p in po - pt)
    return res


def main():
    tpl_wb = load_workbook(TEMPLATE)
    banks = bank_table(tpl_wb)
    h0 = hashlib.sha256(open(TEMPLATE, "rb").read()).hexdigest()
    report = {}
    # 기준선: 무수정 round-trip
    rt = load_workbook(TEMPLATE)
    rt.save(os.path.join(OUT, "roundtrip.xlsx"))
    report["roundtrip"] = dict(parts_lost=sorted(re.sub(r"\d+", "#", p) for p in parts(TEMPLATE) - parts(os.path.join(OUT, "roundtrip.xlsx"))),
                               parts_added=sorted(re.sub(r"\d+", "#", p) for p in parts(os.path.join(OUT, "roundtrip.xlsx")) - parts(TEMPLATE)))
    for label, fn in (("A", approach_A), ("B", approach_B)):
        for n in (1, 32, 45, 70, 120):
            rows = synth(n, banks)
            wb = fn(n, rows, banks, "str")
            p = os.path.join(OUT, f"{label}_{n}.xlsx")
            wb.save(p)
            report[f"{label}_{n}"] = compare(tpl_wb, p, n, rows, "str", TEMPLATE)
    # 학번 정수 기록 대비(타입 비교)
    rows = synth(45, banks)
    wb = approach_B(45, rows, banks, "int")
    p = os.path.join(OUT, "B_45_idint.xlsx")
    wb.save(p)
    r = compare(tpl_wb, p, 45, rows, "int", TEMPLATE)
    report["B_45_idint"] = {k: r[k] for k in ("sid_cell_type", "sid_preserves_source_string", "cross_check_list_wins_wris")}
    assert hashlib.sha256(open(TEMPLATE, "rb").read()).hexdigest() == h0, "template changed!"
    json.dump(report, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1, default=str)
    print("done; template sha unchanged")


main()
