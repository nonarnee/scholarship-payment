"""시트별 저장 선택(Step 2)과 결과 표시(Step 3). 합성 데이터만 사용한다."""
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")

from scholarship_payment.ui import generation as gn  # noqa: E402
from scholarship_payment.ui.navigation import Step  # noqa: E402
from test_step3 import generate, inline, listing, make_win, to_step2  # noqa: E402,F401


def test_option_is_off_by_default_and_visible_on_the_review_step(inline, make_input):
    to_step2(inline, make_input(n=3))
    assert not inline.step2.split_check.isChecked() and not inline.step2.split_check.isHidden() and not inline.step2.split_selected()


def test_default_generation_is_still_one_file(inline, make_input, out_dir):
    to_step2(inline, make_input(n=3))
    generate(inline)
    o = inline.generation.outcome
    assert inline.generation.state == gn.SUCCESS and not o.split and [p.is_file() for p in out_dir.iterdir()] == [True]
    assert inline.step3.file_cap.text() == "저장된 파일"


def test_split_generation_creates_one_subfolder_with_three_files(inline, make_input, out_dir):
    to_step2(inline, make_input(n=3))
    inline.step2.split_check.setChecked(True)
    generate(inline)
    g, s3 = inline.generation, inline.step3
    assert g.state == gn.SUCCESS and g.split and g.outcome.split
    folders = [p for p in out_dir.iterdir()]
    assert len(folders) == 1 and folders[0].is_dir() and len(list(folders[0].iterdir())) == 3
    assert s3.file_cap.text().startswith("저장된 폴더") and folders[0].name in s3.file_name_value.text()
    for p in g.outcome.output_paths:
        assert Path(p).name in s3.file_name_value.text()
    assert "서로 대조" in s3.verify_label.text() and s3.count_value.text() == "3명"


def test_open_folder_opens_the_new_subfolder_for_split(qapp, make_context, ready_settings, make_input, out_dir):
    from test_step3 import make_win as mk
    calls = []

    class Actions:
        def open_folder(self, p):
            calls.append(Path(p))
            return True

        def copy_text(self, t):
            calls.append(t)
            return True
    w, _ = mk(make_context, ready_settings, actions=Actions())
    to_step2(w, make_input(n=3))
    w.step2.split_check.setChecked(True)
    generate(w)
    w.step3.open_folder_button.click()
    w.step3.copy_path_button.click()
    out = Path(w.generation.outcome.output_path)
    assert calls == [out, str(out)]
    w.close()


def test_mode_is_not_carried_into_a_new_conversion(inline, make_input):
    to_step2(inline, make_input(n=3))
    inline.step2.split_check.setChecked(True)
    generate(inline)
    inline.step3.new_button.click()
    assert not inline.generation.split and not inline.step2.split_check.isChecked()
