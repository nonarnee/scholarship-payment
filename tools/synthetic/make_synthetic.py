#!/usr/bin/env python3
"""완전 합성 테스트 엑셀 생성기. 실제 업무자료를 읽지 않는다(입력 파일 인자 없음).

생성물(공개 저장소에 포함 가능):
  templates/synthetic_payment_template.xlsx                      표준 출력 템플릿(합성 값 45행 포함)
  tests/fixtures/synthetic/synthetic_monthly_approval_45.xlsx    입력 형식, 학번 숫자 셀(실제 형식 모사)
  tests/fixtures/synthetic/synthetic_monthly_approval_3_text_ids.xlsx  입력 형식, 학번 문자열(선행 0 시험)

사용: .venv/bin/python -I tools/synthetic/make_synthetic.py [--root <저장소 루트>]

합성 규칙(공개 안전):
  이름 가상NNN / 기관 가상기관NN / 근로지 가상근로지NN / 학과 가상학과NN / 은행 가상은행NN
  학번 90NNNNNN(숫자) 또는 00NNNNNN(문자열) / 사업자번호 000-00-NNNNN / 계좌 000-000-NNNNNN
  시급 1000(합계가 8자리 숫자가 되지 않도록 작게), 연월·날짜는 예약값, 상수 코드는 SYN-*, 모든 파일에 SYNTHETIC-TEST-DATA 표식.
레이아웃(시트 구성, 병합, 열 너비, 행 높이, 수식 구조)은 실제 업무 양식의 구조를 모사하되,
헤더 중 외부 시스템 고유 식별 문자열은 중립 이름으로 바꾸었다(실제 헤더·상수는 비공개 설정으로 주입한다).
"""
import argparse
import io
import re
import zipfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import Rule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.styles.differential import DifferentialStyle

MARKER = "SYNTHETIC-TEST-DATA"
LIST_SHEET = "지급대상자명단(9월)"
HISTORY_SHEET = "업로드 결과(이력)"
THIN = Side(style="thin")
NONE = Side(style=None)
FONT = Font(name="돋움", size=9)
BOLD = Font(name="돋움", size=9, bold=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RATE = 1000


def border(l=THIN, r=THIN, t=THIN, b=THIN):
    return Border(left=l, right=r, top=t, bottom=b)


def mark(wb, title):
    wb.properties.creator = "synthetic-generator"
    wb.properties.lastModifiedBy = "synthetic-generator"
    wb.properties.title = title
    wb.properties.subject = MARKER
    wb.properties.keywords = MARKER
    wb.properties.description = "완전 합성 데이터. 실제 학생·기관·지급 정보를 포함하지 않는다."


def fmt_min(m):
    h, mm = divmod(m, 60)
    return f"{h}시간" if mm == 0 else f"{h}시간{mm}분"


def records(n, id_mode="numeric"):
    banks = [f"가상은행{k:02d}" for k in range(1, 9)]
    mins = [33 * 60, 14 * 60 + 30, 10 * 60, 32 * 60, 55 * 60 + 18, 20 * 60, 5 * 60 + 30, 9 * 60 + 45]
    out = []
    for i in range(1, n + 1):
        m = mins[i % len(mins)]
        sid = f"90{i:06d}" if id_mode == "numeric" else f"00{i:06d}"
        out.append(dict(
            seq=i, ym="9999년09월", name=f"가상{i:03d}", sid=sid,
            dept=f"가상학과{i % 7 + 1:02d}", biz=f"000-00-{i:05d}",
            org=f"가상기관{i % 12 + 1:02d}", place=f"가상근로지{i % 12 + 1:02d}",
            heads=i % 11 + 1, rate=RATE, minutes=m, text=fmt_min(m),
            pay=RATE * m // 60, bank=banks[i % len(banks)], acct=f"000-000-{i:06d}",
        ))
    return out


def bank_rows():
    """합성 은행코드표. 일부 WINS 코드 공란, 이름 중복 1건(모호성 시험)."""
    rows = []
    for k in range(1, 21):
        name = f"가상은행{k:02d}"
        wins = None if k in (9, 10, 11, 12, 13, 14, 15) else (900 + k if k % 2 else f"9{k:02d}")
        rows.append((name, wins, f"99{k:04d}"))
    rows.append(("가상은행01", 901, "990001"))  # 중복 이름
    return rows


def set_widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def dup_rule():
    return Rule(type="duplicateValues", dxf=DifferentialStyle(font=Font(color="FF9C0006"), fill=PatternFill(bgColor="FFFFC7CE")))


# ---------------------------------------------------------------- 출력 템플릿
def build_template(n=45):
    rows = records(n)
    wb = Workbook()
    ws = wb.active
    ws.title = LIST_SHEET
    ws.sheet_properties.tabColor = "FFFFFF00"
    ws.page_setup.orientation, ws.page_setup.paperSize = "portrait", 9
    ws.merge_cells("A1:Q1")
    ws["A1"] = "합성 데이터 — 가상 사업 지급 명단 (9월분)"
    ws["A1"].font, ws["A1"].alignment = Font(name="돋움", size=16, bold=True), CENTER
    ws["Q2"] = "*기준 : 0000.00.00"
    ws["Q2"].font, ws["Q2"].alignment = Font(name="돋움", size=10), Alignment(horizontal="right", vertical="center")
    heads = ["순번", "년월", "성명", "학번", "학과", "사업자\n등록번호", "활동기관", "근로지", "멘티\n인원", "시급", "시간"]
    hfill = PatternFill("solid", fgColor="FFDCE6F1")
    for c, h in enumerate(heads, 1):
        ws.cell(3, c, h)
        ws.merge_cells(start_row=3, start_column=c, end_row=4, end_column=c)
    ws["L3"], ws["L4"] = "재단 장학금", "계"
    ws.merge_cells("M3:P3")
    ws["M3"] = "계좌번호"
    for c, h in zip("MNOP", ["은행명", "은행코드(WINS)", "은행코드(WRIS)", "계좌번호"]):
        ws[f"{c}4"] = h
    ws["Q3"] = "비고"
    ws.merge_cells("Q3:Q4")
    for r in (3, 4):
        for c in range(1, 18):
            cell = ws.cell(r, c)
            cell.font, cell.alignment, cell.border = BOLD, CENTER, border()
            if r == 3 or c in (12, 13, 14, 15, 16):
                cell.fill = hfill
    ws.row_dimensions[1].height, ws.row_dimensions[2].height = 20.25, 12
    for i, d in enumerate(rows):
        r = 5 + i
        vals = [d["seq"], d["ym"], d["name"], int(d["sid"]), d["dept"], d["biz"], d["org"], d["place"],
                d["heads"], d["rate"], d["text"], d["pay"], d["bank"]]
        for c, v in enumerate(vals, 1):
            ws.cell(r, c, v)
        ws[f"N{r}"] = f"=VLOOKUP(M{r},은행코드!$B$2:$C$79,2,0)"
        ws[f"O{r}"] = f"=VLOOKUP(M{r},은행코드!$B$2:$D$79,3,0)"
        ws[f"P{r}"] = d["acct"]
        top = THIN if i == 0 else NONE
        for c in range(1, 18):
            cell = ws.cell(r, c)
            cell.font, cell.border = FONT, border(t=top)
            cell.alignment = LEFT if c in (5, 7, 8) else CENTER
            cell.number_format = "#,##0_ " if c in (9, 10, 12) else ("General" if c in (1, 14, 15) else "@")
        if r <= 40:
            ws.row_dimensions[r].height = 14.1  # 41행 이후는 의도적으로 미지정(원 양식의 불균일 모사)
    t = 5 + n
    ws[f"K{t}"] = fmt_min(sum(d["minutes"] for d in rows))
    ws[f"L{t}"] = sum(d["pay"] for d in rows)
    for c in range(1, 18):
        cell = ws.cell(t, c)
        cell.font, cell.fill, cell.alignment = BOLD, PatternFill("solid", fgColor="FFFFE4B1"), CENTER
        cell.border = border(l=NONE, r=NONE)
    ws[f"L{t}"].number_format = "#,##0_ "
    ws.row_dimensions[t].height = 16.5
    ws.auto_filter.ref = "C3:G4"
    for rng in ("D5:D7 D20:D25", "D8:D14", "D26:D27"):  # 조각난 조건부 서식 모사
        ws.conditional_formatting.add(rng, dup_rule())
    set_widths(ws, dict(A=3.75, B=9, C=9.6, D=10.6, E=15.9, F=11.9, G=36.1, H=31.9, I=5.4, J=6.4, K=11.6,
                        L=11.6, M=16, N=13.3, O=13.3, P=20.4, Q=14.8))

    # WINS
    w = wb.create_sheet("WINS")
    wh = ["근로구분명", "년도", "월", "학번", "근무부서코드", "근무일수", "재단 장학금", "은행코드", "계좌번호"]
    for c, h in enumerate(wh, 1):
        cell = w.cell(1, c, h)
        cell.font, cell.fill = Font(name="돋움", size=9, bold=True, color="FFFFFFFF"), PatternFill("solid", fgColor="FF002060")
        cell.alignment, cell.border = CENTER, border()
    q = f"'{LIST_SHEET}'!"
    for i, d in enumerate(rows):
        r = 2 + i
        w.cell(r, 1, "SYN-근로구분")
        w.cell(r, 2, 2099)
        w.cell(r, 3, 9)
        w.cell(r, 4, int(d["sid"]))
        w.cell(r, 7, f"=VLOOKUP(D{r},{q}$D$5:$L$100,9,0)")
        w.cell(r, 8, f"=VLOOKUP(D{r},{q}$D$5:$N$100,11,0)")
        w.cell(r, 9, f"=VLOOKUP(D{r},{q}$D$5:$P$100,13,0)")
        for c in range(1, 10):
            cell = w.cell(r, c)
            cell.font, cell.alignment = FONT, CENTER
            cell.border = border(t=THIN if i == 0 else NONE)
            cell.number_format = "@" if c == 4 else ("_-* #,##0_-;\\-* #,##0_-;_-* \"-\"_-;_-@_-" if c == 7 else "General")
        w.row_dimensions[r].height = 14.1
    w.row_dimensions[1].height = 14.1
    set_widths(w, dict(A=13.6, G=16.3, H=12.3, I=17.5))

    # 업로드 결과 이력(헤더만, 출력에서 제외되는 시트)
    h = wb.create_sheet(HISTORY_SHEET)
    for c in range(1, 23):
        h.cell(1, c, f"col{c:02d}")

    # WRIS (헤더는 중립 이름. 실제 헤더는 비공개 설정으로 주입)
    s = wb.create_sheet("WRIS")
    sh = ["gub_a", "gub_b", "verify_no", "payee_name", "total_money", "bank_code", "account_no", "depositor", "remit_info", "remark"]
    for c, hd in enumerate(sh, 1):
        cell = s.cell(1, c, hd)
        cell.font, cell.fill = Font(name="맑은 고딕", size=9, bold=True), PatternFill("solid", fgColor="FFBFBFBF")
        cell.alignment, cell.border = CENTER, border()
    for i, d in enumerate(rows):
        r = 2 + i
        s.cell(r, 1, "SYN-GUB-A")
        s.cell(r, 2, "SYN-GUB-B")
        s.cell(r, 3, int(d["sid"]))
        s.cell(r, 4, d["name"])
        s.cell(r, 5, f"=VLOOKUP(C{r},{q}$D$5:$L$100,9,0)")
        s.cell(r, 6, f"=VLOOKUP(C{r},{q}$D$5:$P$100,12,0)")
        s.cell(r, 7, f"=VLOOKUP(C{r},{q}$D$5:$Q$100,13,0)")
        s.cell(r, 8, f"=D{r}")
        s.cell(r, 9, "가상사업(9월)")
        for c in range(1, 11):
            cell = s.cell(r, c)
            cell.font, cell.alignment = FONT, CENTER
            cell.border = border(t=THIN if i == 0 else NONE)
            cell.number_format = "@" if c in (3, 8) else ("_-* #,##0_-;\\-* #,##0_-;_-* \"-\"_-;_-@_-" if c == 5 else "General")
        s.row_dimensions[r].height = 14.1
    s.row_dimensions[1].height = 14.1
    set_widths(s, dict(E=11.8, G=14.1, I=17.8, J=25.8))

    # 은행코드(합성)
    b = wb.create_sheet("은행코드")
    for c, hd in enumerate(["은행명", "은행명", "WINS 사용코드(합성)", "WRIS 사용코드(합성)"], 1):
        b.cell(1, c, hd)
    for i, (name, wins, wris) in enumerate(bank_rows()):
        r = 2 + i
        b.cell(r, 1, name)
        b.cell(r, 2, name)
        if wins is not None:
            b.cell(r, 3, wins)
        b.cell(r, 4, wris)
    set_widths(b, dict(A=16.4, B=29.4, D=12.9))
    mark(wb, "합성 지급명단 템플릿")
    return wb


# ---------------------------------------------------------------- 입력 형식
def with_carryover(rows, extra):
    """`extra` = [(대상자 번호(1부터), 분, 년월)]: 해당 대상자 바로 아래에 같은 사람의 이월 행을 끼워 넣고 순번을 다시 매긴다."""
    out = []
    for d in rows:
        out.append(d)
        for who, minutes, ym in extra:
            if who == d["seq"]:
                out.append({**d, "ym": ym, "minutes": minutes, "text": fmt_min(minutes), "pay": d["rate"] * minutes // 60})
    return [{**d, "seq": k} for k, d in enumerate(out, 1)]


def build_input(n, id_mode, extra=()):
    rows = with_carryover(records(n, id_mode), extra)
    n = len(rows)
    wb = Workbook()
    ws = wb.active
    ws.title = "월별지급승인"
    top = ["", "일치", "순번", "년월", "성명", "학번", "학과", "사업자\n등록번호", "활동기관", "근로지", "멘토\n인원",
           "시급", "시간", "기준금액\n(시급X총시간)", "재단 장학금", "", "", "대학 자체 장학금", "", "계좌번호", "", "지급일자", "지급확인", "비고"]
    for c, v in enumerate(top, 1):
        if v != "":
            ws.cell(1, c, v)
    ws["A1"] = 0
    for c, v in zip("OPQRSTU", ["계", "교부금집행액", "이자수익집행액", "대응투자 장학금\n(기본금)", "별도 추가 장학금\n(추가금)", "은행명", "계좌번호"]):
        ws[f"{c}2"] = v
    for c in list("ABCDEFGHIJKLMN") + list("VWX"):
        ws.merge_cells(f"{c}1:{c}2")
    for rng in ("O1:Q1", "R1:S1", "T1:U1"):
        ws.merge_cells(rng)
    for r in (1, 2):
        for c in range(1, 25):
            cell = ws.cell(r, c)
            cell.font, cell.alignment, cell.border = BOLD, CENTER, border()
    for i, d in enumerate(rows):
        r = 3 + i
        sid = int(d["sid"]) if id_mode == "numeric" else d["sid"]
        vals = {"A": 0, "C": d["seq"], "D": d["ym"], "E": d["name"], "F": sid, "G": d["dept"], "H": d["biz"], "I": d["org"],
                "J": d["place"], "K": d["heads"], "L": d["rate"], "M": d["text"], "N": d["pay"], "O": d["pay"], "P": d["pay"],
                "Q": 0, "R": 0, "S": 0, "T": d["bank"], "U": d["acct"], "W": "미처리"}
        for col, v in vals.items():
            ws[f"{col}{r}"] = v
        for c in range(1, 25):
            cell = ws.cell(r, c)
            cell.font, cell.border = FONT, border()
            cell.alignment = CENTER
            if 11 <= c <= 19 and c != 13:
                cell.number_format = "#,##0_ "
    t = 3 + n
    ws.merge_cells(f"A{t}:E{t}")
    ws.merge_cells(f"F{t}:L{t}")
    ws[f"F{t}"] = "합               계"
    ws[f"M{t}"] = fmt_min(sum(d["minutes"] for d in rows))
    for col in "NOP":
        ws[f"{col}{t}"] = sum(d["pay"] for d in rows)
    for col in "QRS":
        ws[f"{col}{t}"] = 0
    for c in range(1, 25):
        ws.cell(t, c).font = BOLD
        ws.cell(t, c).border = border()
    ws.column_dimensions["B"].width = 0
    ws.column_dimensions["B"].hidden = True
    set_widths(ws, dict(A=2.5, C=3.75, E=9.6, G=18.1, H=11, I=16.8, J=14.3, K=5.4, L=6.4, M=11.6, N=11.6, O=11.6,
                        P=11.6, Q=12.9, R=13.9, S=13.9, T=10.8, U=15.1, V=10.3, W=7.6, X=13.3))
    mark(wb, "합성 월별지급승인 입력")
    return wb


MC_RATES = {"가상A": 1000, "가상B": 1500}      # 합성 시급표(근무형태 괄호 값 -> 원)


def mc_students(n):
    """다문화 형식 합성 학생 n명(각자 기관 1곳). rows 항목: (기관, 근무형태 키, 분)."""
    banks = [f"가상은행{k:02d}" for k in range(1, 9)]
    return [dict(sid=f"90{i:06d}", name=f"가상{i:03d}", dept=f"가상학과{i % 7 + 1:02d}", bank=banks[i % 8],
                 acct=f"000-000-{i:06d}", ym="9999-09",
                 rows=[(f"가상기관{i % 12 + 1:02d}", "가상A" if i % 3 else "가상B", (10 + i % 40) * 60 + (30 if i % 4 == 0 else 0))])
            for i in range(1, n + 1)]


def build_input_multicultural(students, rates=MC_RATES):
    """`월별지급부현황` 형식 합성 입력: 학생 묶음(데이터 행 + 소계 행) 반복 + 합계 행."""
    wb = Workbook()
    ws = wb.active
    ws.title = "월별지급부현황"
    top = {"A1": 0, "B1": "순번", "C1": "멘토유형", "D1": "년월", "E1": "성명", "F1": "학번", "G1": "학과", "H1": "멘티현황",
           "M1": "총시간", "N1": "총금액(원)", "O1": "은행정보", "Q1": "지급\n확인", "R1": "비고",
           "H2": "근무형태", "I2": "기관명", "J2": "학교구분", "K2": "학년", "L2": "멘티명", "O2": "은행명", "P2": "계좌번호"}
    for k, v in top.items():
        ws[k] = v
    for c in "ABCDEFGMNQ":
        ws.merge_cells(f"{c}1:{c}2")
    ws.merge_cells("H1:L1")
    ws.merge_cells("O1:P1")
    r = 3
    seq = 0
    tot_m = tot_a = 0
    for st in students:
        sm = sa = 0
        for k, (org, wk, minutes) in enumerate(st["rows"]):
            seq += 1
            amount = rates[wk] * minutes // 60
            vals = {"A": 0, "B": seq, "C": "가상멘토링", "D": st["ym"] if k == 0 else None, "E": st["name"] if k == 0 else None,
                    "F": st["sid"] if k == 0 else None, "G": st["dept"] if k == 0 else None,        # 년월·성명·학번·학과는 첫 행에만 나온다(실제 원본 특성)
                    "H": f"09월 방문({wk})", "I": org, "J": "초등학교", "K": "3", "L": "가상멘티", "M": fmt_min(minutes),
                    "N": amount, "O": st["bank"], "P": st["acct"], "Q": "미처리"}
            for col, v in vals.items():
                ws[f"{col}{r}"] = v
            sm, sa = sm + minutes, sa + amount
            r += 1
        for col, v in {"G": "소   계", "M": fmt_min(sm), "N": sa}.items():
            ws[f"{col}{r}"] = v
        tot_m, tot_a = tot_m + sm, tot_a + sa
        r += 1
    ws[f"A{r}"], ws[f"M{r}"], ws[f"N{r}"] = "합계", fmt_min(tot_m), tot_a
    ws.merge_cells(f"A{r}:L{r}")
    ws.column_dimensions["J"].hidden = True
    mark(wb, "합성 월별지급부현황 입력")
    return wb


def _inject_empty_strings(path, coords):
    """저장된 xlsx 의 지정 칸을 '빈 문자열(inlineStr)' 셀로 바꾼다.
    실제 다운로드 원본은 B·V·X 열과 합계행 일부가 None 이 아니라 빈 문자열이며, openpyxl 은 빈 문자열을 저장하지 않는다."""
    zin = zipfile.ZipFile(path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                xml = data.decode("utf-8")
                for c in coords:
                    xml, n = re.subn(rf'<c r="{c}"( s="\d+")?(?: t="n")? ?/>',
                                     lambda m, c=c: f'<c r="{c}"{m.group(1) or ""} t="inlineStr"><is><t></t></is></c>', xml)
                    if n != 1:
                        raise RuntimeError(f"빈 문자열 셀 주입 실패: {c}")
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    Path(path).write_bytes(buf.getvalue())


def save_input(path, n, id_mode):
    """입력 형식 합성 파일을 저장한다(실제 원본의 빈 문자열 칸 포함)."""
    build_input(n, id_mode).save(path)
    total = 3 + n
    coords = [f"{c}{r}" for r in range(3, total) for c in "BVX"] + [f"{c}{total}" for c in "ATUVWX"]
    _inject_empty_strings(path, coords)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    root = Path(ap.parse_args().root)
    (root / "templates").mkdir(exist_ok=True)
    fx = root / "tests" / "fixtures" / "synthetic"
    fx.mkdir(parents=True, exist_ok=True)
    build_template(45).save(root / "templates" / "synthetic_payment_template.xlsx")
    save_input(fx / "synthetic_monthly_approval_45.xlsx", 45, "numeric")
    save_input(fx / "synthetic_monthly_approval_3_text_ids.xlsx", 3, "text")
    print("생성 완료: templates/synthetic_payment_template.xlsx, tests/fixtures/synthetic/ 2개")


if __name__ == "__main__":
    main()
