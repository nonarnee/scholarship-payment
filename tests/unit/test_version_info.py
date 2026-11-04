import importlib.util
from pathlib import Path

import scholarship_payment

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("make_version_info", ROOT / "packaging" / "make_version_info.py")
mvi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mvi)


class _Rec:
    def __init__(self, name):
        self.name = name

    def __call__(self, *a, **k):
        return (self.name, a, k)


def _evaluate(text):
    names = ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable", "StringStruct", "VarFileInfo", "VarStruct")
    return eval(text, {n: _Rec(n) for n in names})        # PyInstaller 가 같은 방식으로 읽는다(개발 환경에는 PyInstaller 없음)


def test_version_info_is_a_valid_expression_and_carries_the_version():
    text = mvi.render("1.2.3", "ScholarshipPayment-v1.2.3")
    name, _, kw = _evaluate(text)
    assert name == "VSVersionInfo" and kw["ffi"][2]["filevers"] == (1, 2, 3, 0)
    assert "'FileVersion', '1.2.3'" in text and "ScholarshipPayment-v1.2.3.exe" in text


def test_main_writes_file_using_the_package_version(tmp_path):
    out = tmp_path / "v.txt"
    assert mvi.main(["x", str(out)]) == 0
    assert f"'ProductVersion', '{scholarship_payment.__version__}'" in out.read_text(encoding="utf-8")
