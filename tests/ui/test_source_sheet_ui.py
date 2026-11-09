"""Qt 화면도 같은 시트 탐색 규칙을 쓴다: 시트명이 달라도 구조가 맞으면 미리보기가 준비되고, 모호하거나 구조가 맞지 않으면 안내와 함께 차단한다."""
import pytest

PySide6 = pytest.importorskip("PySide6")

from openpyxl import load_workbook  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402

from scholarship_payment.ui import preview as pv  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402
from scholarship_payment.ui.navigation import Step  # noqa: E402

MARK = "가상시트-비공개-QZ"


def texts(w):
    return " ".join(x.text() for x in w.findChildren(QLabel))


def reshape(src, dst, fn):
    wb = load_workbook(src)
    fn(wb)
    wb.save(dst)
    return dst


@pytest.fixture
def win(qapp, make_context, ready_settings):
    w = MainWindow(context=make_context(settings=ready_settings))
    w.show()
    yield w
    w.close()


def open_step2(w, src):
    w.step1.model.set_source(src)
    assert w.next_button.isEnabled()
    w.next_button.click()
    assert w.navigator.current == Step.REVIEW


def test_a_renamed_sheet_with_extra_sheets_gives_the_same_preview(win, make_input, tmp_path):
    src = make_input(n=4)
    open_step2(win, src)
    base = (win.step2.count_value.text(), win.step2.total_value.text(), win.step2.month_value.text())
    assert win.step2.session.state == pv.READY
    win.navigator.back()

    def shape(wb):
        wb.worksheets[0].title = "재단에서 받은 파일"
        wb.create_sheet("안내", 0)["A1"] = "학번 성명 합계"
        wb.create_sheet("메모")
    open_step2(win, reshape(src, tmp_path / "shaped.xlsx", shape))
    assert win.step2.session.state == pv.READY
    assert (win.step2.count_value.text(), win.step2.total_value.text(), win.step2.month_value.text()) == base


def test_two_matching_sheets_are_blocked_with_a_clear_message_and_no_sheet_name(win, make_input, tmp_path):
    def dup(wb):
        wb.worksheets[0].title = MARK + "-원본"
        wb.copy_worksheet(wb.worksheets[0]).title = MARK + "-복사"
    open_step2(win, reshape(make_input(n=3), tmp_path / "dup.xlsx", dup))
    p = win.step2
    assert p.session.state == pv.FAILED and not win.next_button.isEnabled()
    assert "구조가 같은 시트가 둘 이상" in texts(p) and "SHEET_AMBIGUOUS" in texts(p) and MARK not in texts(p)


def test_no_matching_sheet_is_blocked_with_a_structure_message(win, make_input, tmp_path):
    def nomatch(wb):
        wb.worksheets[0]["E1"] = "이름"
        wb.create_sheet(MARK + "-안내", 0)
    open_step2(win, reshape(make_input(n=3), tmp_path / "nomatch.xlsx", nomatch))
    p = win.step2
    assert p.session.state == pv.FAILED and not win.next_button.isEnabled()
    assert "구조가 맞는 시트를 찾지 못했습니다" in texts(p) and "SHEET_NO_MATCH" in texts(p) and MARK not in texts(p)
    assert "월별지급승인" not in texts(p)                                  # 옛 안내('필요한 시트(월별지급승인)')는 더 이상 나오지 않는다


def test_a_single_sheet_with_a_wrong_layout_still_shows_the_layout_message(win, make_input):
    open_step2(win, make_input(n=3, mutate=lambda ws: ws.__setitem__("F1", "다른 제목")))
    assert win.step2.session.state == pv.FAILED and "머리글이 예상한 형식과 다릅니다" in texts(win.step2)
