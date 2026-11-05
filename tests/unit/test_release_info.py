"""배포 후보 버전·산출물 이름·Windows 버전 리소스의 일관성. 버전은 scholarship_payment.__version__ 하나에서만 나온다."""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

import scholarship_payment

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "packaging" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ri = _load("release_info")
mvi = _load("make_version_info")


def test_release_candidate_version_is_applied_everywhere_from_one_source():
    assert scholarship_payment.__version__ == "0.3.0-rc.1"
    assert ri.current_version() == scholarship_payment.__version__


@pytest.mark.parametrize("text,expected", [("0.3.0-rc.1", (0, 3, 0, 1)), ("1.2.3", (1, 2, 3, None)), ("10.20.30-rc.12", (10, 20, 30, 12))])
def test_parse_accepts_final_and_rc_versions_only(text, expected):
    assert ri.parse(text) == expected


@pytest.mark.parametrize("bad", ["0.3", "0.3.0-rc", "0.3.0-rc.x", "0.3.0rc1", "v0.3.0", "0.3.0-beta.1", "0.3.0-rc.1-x", ""])
def test_parse_rejects_anything_else(bad):
    with pytest.raises(ValueError):
        ri.parse(bad)


def test_artifact_and_exe_names_are_distinct_per_kind_and_carry_version_and_sha():
    v = "0.3.0-rc.1"
    assert ri.exe_name("qt", v) == "ScholarshipPayment-v0.3.0-rc.1"                 # 신규 기본 산출물
    assert ri.exe_name("legacy", v) == "ScholarshipPaymentLegacyTk-v0.3.0-rc.1"     # Tk 병행 산출물
    assert ri.exe_name("dev", v) == "ScholarshipPaymentUI-dev"                      # 개발용(E2E) 빌드는 사용자용이 아니다
    names = {ri.artifact_name(k, v, "0123456789abcdef") for k in ("qt", "legacy", "dev")}
    assert len(names) == 3 and ri.artifact_name("qt", v, "0123456789abcdef") == "ScholarshipPayment-v0.3.0-rc.1-0123456"
    with pytest.raises(ValueError):
        ri.exe_name("other", v)


def test_cli_prints_values_for_the_workflow():
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "packaging" / "release_info.py"), *a], capture_output=True, text=True, check=True).stdout.strip()  # noqa: E731
    assert run("version") == "0.3.0-rc.1" and run("exe-name", "qt") == "ScholarshipPayment-v0.3.0-rc.1"
    assert run("artifact-name", "legacy", "abcdef0123") == "ScholarshipPaymentLegacyTk-v0.3.0-rc.1-abcdef0"


def test_version_resource_matches_version_and_exe_name_for_rc():
    v = "0.3.0-rc.1"
    text = mvi.render(v, ri.exe_name("qt", v))
    assert "filevers=(0, 3, 0, 0)" in text                                            # 숫자 4칸은 rc 표시를 담지 못하므로 문자열 버전이 정본이다
    assert "'FileVersion', '0.3.0-rc.1'" in text and "'ProductVersion', '0.3.0-rc.1'" in text
    assert "'OriginalFilename', 'ScholarshipPayment-v0.3.0-rc.1.exe'" in text and "배포 후보" in text


def test_final_version_resource_has_no_release_candidate_comment():
    assert "배포 후보" not in mvi.render("1.0.0", "ScholarshipPayment-v1.0.0")


def test_main_uses_the_package_version_and_accepts_an_exe_name(tmp_path):
    out = tmp_path / "v.txt"
    assert mvi.main(["x", str(out), "ScholarshipPaymentLegacyTk-v0.3.0-rc.1"]) == 0
    t = out.read_text(encoding="utf-8")
    assert f"'FileVersion', '{scholarship_payment.__version__}'" in t and "LegacyTk" in t


def test_window_title_version_and_about_text_use_the_same_source():
    from scholarship_payment import __version__
    assert re.fullmatch(r"\d+\.\d+\.\d+(-rc\.\d+)?", __version__)
