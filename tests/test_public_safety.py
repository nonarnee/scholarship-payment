"""공개 안전성 검사기(tools/safety/check_public_safety.py)의 자체 시험. 합성 값만 사용한다."""
import importlib.util
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("chk", ROOT / "tools" / "safety" / "check_public_safety.py")
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)


def run(path, data, deny=()):
    out = []
    chk.classify_and_check(path, data, list(deny), out)
    return out


def rules(out):
    return {r[0] for r in out}


def make_xlsx(marker=True, author="synthetic-generator", cell="가상001", hidden=False):
    core = (f'<cp:coreProperties xmlns:cp="x" xmlns:dc="y"><dc:creator>{author}</dc:creator>'
            f'<cp:lastModifiedBy>{author}</cp:lastModifiedBy>'
            f'<dc:subject>{"SYNTHETIC-TEST-DATA" if marker else ""}</dc:subject></cp:coreProperties>')
    state = ' state="hidden"' if hidden else ""
    wb = f'<workbook><sheets><sheet name="s" sheetId="1"{state}/></sheets></workbook>'
    sheet = f"<worksheet><sheetData><row><c t=\"inlineStr\"><is><t>{cell}</t></is></c></row></sheetData></worksheet>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("docProps/core.xml", core)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


# ---- 경로 규칙
def test_blocked_dirs_and_exts():
    assert "P1:blocked_dir" in rules(run("samples/a.txt", b"x"))
    assert "P1:blocked_dir" in rules(run("private/notes.md", b"x"))
    assert "P1:blocked_ext" in rules(run("docs/a.csv", b"x"))
    assert "P1:blocked_ext" in rules(run("docs/a.pdf", b"x"))


def test_excel_location_and_name():
    ok = make_xlsx()
    assert run("templates/synthetic_t.xlsx", ok) == []
    assert "P1:excel_outside_allowed_dir" in rules(run("docs/synthetic_t.xlsx", ok))
    assert "P2:excel_name" in rules(run("templates/real_list.xlsx", ok))


# ---- 엑셀 내부 규칙
def test_excel_requires_marker_and_clean_author():
    assert "X1:no_synthetic_marker" in rules(run("templates/synthetic_a.xlsx", make_xlsx(marker=False)))
    assert "X1:author" in rules(run("templates/synthetic_a.xlsx", make_xlsx(author="Some Person")))
    assert "X2:hidden_sheet" in rules(run("templates/synthetic_a.xlsx", make_xlsx(hidden=True)))


def test_excel_cell_patterns_and_denylist():
    assert "T1:biz_no" in rules(run("templates/synthetic_a.xlsx", make_xlsx(cell="123-45-67890")))
    assert "T2:denylist" in rules(run("templates/synthetic_a.xlsx", make_xlsx(cell="비밀기관명"), deny=["비밀기관명"]))
    assert run("templates/synthetic_a.xlsx", make_xlsx(cell="000-00-00001")) == []


# ---- 텍스트 패턴
def test_text_patterns_flag_real_looking_values():
    assert "T1:biz_no" in rules(run("docs/a.md", "사업자 123-45-67890".encode()))
    assert "T1:account" in rules(run("docs/a.md", "계좌 123-456-789012".encode()))
    assert "T1:digits8" in rules(run("docs/a.md", "학번 20241234".encode()))
    assert "T1:phone" in rules(run("docs/a.md", "010-1234-5678".encode()))
    assert "T1:email" in rules(run("docs/a.md", "a@b.com".encode()))
    assert "T1:rrn" in rules(run("docs/a.md", "900101-1234567".encode()))


def test_text_allows_reserved_synthetic_values():
    for ok in ("000-00-00001", "000-000-000001", "00000001", "90000001", "99990901", "가상001"):
        assert run("docs/a.md", f"값 {ok}".encode()) == [], ok


def test_denylist_blocks_in_text():
    assert "T2:denylist" in rules(run("docs/a.md", "여기에 비밀값이 있다".encode(), deny=["비밀값"]))


def test_messages_never_contain_matched_value():
    out = run("docs/a.md", "123-45-67890 비밀값".encode(), deny=["비밀값"])
    flat = " ".join(str(x) for r in out for x in r)
    assert "123-45-67890" not in flat and "비밀값" not in flat


# ---- 저장소에 포함된 합성 파일은 항상 통과해야 한다
def test_committed_synthetic_files_pass():
    for f in [*(ROOT / "templates").glob("synthetic_*.xlsx"), *(ROOT / "tests/fixtures/synthetic").glob("synthetic_*.xlsx")]:
        rel = str(f.relative_to(ROOT))
        assert run(rel, f.read_bytes()) == [], rel
