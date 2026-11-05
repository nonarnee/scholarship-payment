"""배포 자료(설치·실행 안내, 라이선스 전문), 제3자 고지문 생성, 산출물 점검 도구, 빌드 스크립트의 순수 함수 검증. 실제 자료·정책·학교 템플릿은 어디에도 없다."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "packaging" / "dist_assets"

needs_qt_installed = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 가 설치된 환경(Qt 빌드 잡)에서만 실제 설치 메타데이터를 검증한다",
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


notices = _load(ROOT / "packaging" / "make_release_notices.py", "make_release_notices")
build = _load(ROOT / "packaging" / "build_release.py", "build_release")
inv = _load(ROOT / "tools" / "ci" / "inventory_dist.py", "inventory_dist")


# ---------- 설치·실행 안내 ----------
def read(name):
    return (ASSETS / name).read_text(encoding="utf-8-sig")


def test_readme_covers_setup_settings_limits_and_rollback():
    t = read("README-설치.txt")
    for needle in ("%APPDATA%", "ScholarshipPayment", "settings.json", "policy_", "template_", "고급 설정", "SHA256SUMS", "Get-FileHash",
                   "배포 후보", ".~", "자동으로 삭제하지 않", "되돌리", "legacy", "LICENSES"):
        assert needle in t, needle
    assert "포함되어 있지 않" in t                                                  # 정책 JSON·학교 템플릿은 프로그램에 들어 있지 않다
    assert "보장하지 않" in t and "비정상 종료" in t                                  # 비정상 종료 한계를 명시


def test_readme_example_exe_name_matches_the_current_version():
    import scholarship_payment
    assert f"ScholarshipPayment-v{scholarship_payment.__version__}.exe" in read("README-설치.txt")


def test_readme_documents_what_the_settings_file_holds_and_does_not_hold():
    t = read("README-설치.txt")
    assert "원본 파일 경로" in t and "비밀번호" in t and "저장하지 않" in t


def test_readme_has_no_placeholders_personal_data_or_real_paths():
    for f in ASSETS.rglob("*.txt"):
        t = f.read_text(encoding="utf-8-sig")
        assert not re.search(r"\{[A-Za-z_]+\}|TODO|XXX|<입력 필요>", t) or f.name.endswith("GPL-3.0.txt"), f.name
        assert "C:\\Users\\" not in t and "/Users/" not in t, f.name


def test_legacy_readme_exists_and_points_to_the_same_engine_and_rollback():
    t = read("README-LEGACY.txt")
    assert "Tkinter" in t and "같은 변환 엔진" in t and "되돌" in t


def test_license_texts_are_the_official_lgpl_and_gpl_version_3():
    lgpl = (ASSETS / "LICENSES" / "LGPL-3.0.txt").read_text(encoding="utf-8")
    gpl = (ASSETS / "LICENSES" / "GPL-3.0.txt").read_text(encoding="utf-8")
    assert lgpl.lstrip().startswith("GNU LESSER GENERAL PUBLIC LICENSE") and "Version 3, 29 June 2007" in lgpl and "END OF TERMS AND CONDITIONS" not in lgpl
    assert gpl.lstrip().startswith("GNU GENERAL PUBLIC LICENSE") and "Version 3, 29 June 2007" in gpl and "END OF TERMS AND CONDITIONS" in gpl
    assert "Combined Works" in lgpl and "Corresponding Application Code" in lgpl


def test_licenses_readme_states_open_items_instead_of_claiming_compliance():
    t = read("LICENSES/README-LICENSES.txt")
    assert "LGPL" in t and "미결정" in t and "소스" in t and "교체" in t and "RELINK" in t
    for claim in ("준수 완료", "문제 없", "법적 검토를 마", "승인되었"):
        assert claim not in t
    r = read("LICENSES/RELINK-Qt.txt")
    assert "_internal" in r and "수행하지 않았" in r                                 # 교체 절차의 실제 검증은 아직 하지 않았음을 밝힌다


def test_no_policy_template_or_workbook_is_shipped_as_an_asset():
    shipped = [p.name for p in ASSETS.rglob("*") if p.is_file()]
    assert not [n for n in shipped if n.endswith((".xlsx", ".xlsm", ".xls", ".json")) or n.startswith(("policy_", "template_"))]


# ---------- 제3자 고지문 ----------
def test_notices_cover_every_runtime_requirement_of_the_qt_app():
    covered = {notices.normalize(n) for n, _ in notices.PACKAGES}
    missing = sorted(notices.runtime_requirement_names("gui") - covered)
    assert missing == []                                                           # 의존성이 늘면 고지문 목록도 검토해야 한다


@needs_qt_installed
def test_notices_list_real_installed_versions_and_license_expressions():
    text = notices.render("qt")
    import importlib.metadata as m
    assert f"PySide6-Essentials {m.version('PySide6-Essentials')}" in text and "LGPL-3.0-only" in text
    assert f"openpyxl {m.version('openpyxl')}" in text and "MIT" in text
    assert "LGPL-3.0.txt" in text and "GPL-3.0.txt" in text and "라이선스 전문" in text
    assert "제공하지 않" in text or "포함되어 있지 않" in text                         # PySide6 휠에 전문이 없어 별도 파일을 참조한다는 설명


def test_legacy_notices_do_not_mention_qt():
    text = notices.render("legacy")
    assert "PySide6" not in text and "shiboken" not in text and "openpyxl" in text


def test_notices_fail_loudly_when_a_required_package_is_missing(monkeypatch):
    import importlib.metadata as m
    real = m.distribution
    monkeypatch.setattr(notices.metadata, "distribution", lambda n: (_ for _ in ()).throw(m.PackageNotFoundError(n)) if n == "olefile" else real(n))
    with pytest.raises(RuntimeError):
        notices.render("qt")


# ---------- 빌드 스크립트(명령 구성·SHA256SUMS·자료 복사) ----------
def test_qt_build_command_uses_the_production_entry_and_excludes_development_and_tk_modules():
    cmd = build.pyinstaller_args("qt", "0.3.0-rc.1", windowed=True)
    s = " ".join(cmd)
    assert "run_gui_qt.py" in s and "--name ScholarshipPayment-v0.3.0-rc.1" in s and "--windowed" in s and "--version-file" in s
    for mod in ("scholarship_payment.ui.gallery", "scholarship_payment.ui.e2e_smoke", "scholarship_payment.ui.__main__", "tkinter", "scholarship_payment.gui", "PySide6.QtNetwork"):
        assert f"--exclude-module {mod}" in s, mod
    assert "--onedir" in s and "--onefile" not in s and "--collect-submodules msoffcrypto" in s and "upx" not in s.lower()


def test_legacy_and_dev_builds_keep_their_own_entries_and_names():
    legacy = " ".join(build.pyinstaller_args("legacy", "0.3.0-rc.1", windowed=True))
    dev = " ".join(build.pyinstaller_args("dev", "0.3.0-rc.1", windowed=True))
    assert "run_gui.py" in legacy and "ScholarshipPaymentLegacyTk-v0.3.0-rc.1" in legacy and "PySide6" not in legacy.replace("--exclude-module PySide6", "")
    assert "run_ui_dev.py" in dev and "--name ScholarshipPaymentUI-dev" in dev and "e2e_smoke" not in dev and "--version-file" not in dev


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        build.pyinstaller_args("other", "0.3.0-rc.1", windowed=False)


def test_checksums_cover_exe_docs_and_licenses_and_are_verifiable(tmp_path):
    d = tmp_path / "app"
    (d / "LICENSES").mkdir(parents=True)
    (d / "app.exe").write_bytes(b"exe")
    (d / "README-설치.txt").write_text("r", encoding="utf-8")
    (d / "LICENSES" / "a.txt").write_text("a", encoding="utf-8")
    (d / "_internal").mkdir()
    (d / "_internal" / "big.dll").write_bytes(b"dll")
    lines = build.write_checksums(d, "app.exe")
    names = {l.split(" *", 1)[1] for l in lines}
    assert names == {"app.exe", "README-설치.txt", "LICENSES/a.txt"} and (d / "SHA256SUMS.txt").is_file()
    import hashlib
    for l in lines:
        digest, name = l.split(" *", 1)
        assert hashlib.sha256((d / name).read_bytes()).hexdigest() == digest


@needs_qt_installed
def test_assets_are_copied_without_overwriting_the_exe_and_notices_are_generated(tmp_path):
    d = tmp_path / "app"
    d.mkdir()
    (d / "app.exe").write_bytes(b"exe")
    build.install_assets("qt", d)
    assert (d / "README-설치.txt").is_file() and (d / "LICENSES" / "LGPL-3.0.txt").is_file() and (d / "LICENSES" / "THIRD-PARTY-NOTICES.txt").is_file() and (d / "BUILD-INFO.txt").is_file()
    assert (d / "app.exe").read_bytes() == b"exe"
    info = (d / "BUILD-INFO.txt").read_text(encoding="utf-8")
    import scholarship_payment
    assert scholarship_payment.__version__ in info and "PySide6" in info and "Python" in info
    leg = tmp_path / "legacy"
    leg.mkdir()
    build.install_assets("legacy", leg)
    assert (leg / "README-LEGACY.txt").is_file() and not (leg / "LICENSES" / "LGPL-3.0.txt").exists() or "PySide6" not in (leg / "LICENSES" / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")


@needs_qt_installed
def test_build_info_carries_commit_when_provided(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef")
    d = tmp_path / "app"
    d.mkdir()
    build.install_assets("qt", d)
    assert "0123456" in (d / "BUILD-INFO.txt").read_text(encoding="utf-8")


# ---------- 산출물 점검 도구 ----------
def make_fake_dist(root: Path, kind="qt", with_licenses=True, extra=()):
    (root / "_internal" / "PySide6" / "plugins" / "platforms").mkdir(parents=True)
    names = ["Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "shiboken6.abi3.dll"]
    for n in names:
        (root / "_internal" / "PySide6" / n).write_bytes(b"x")
    (root / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll").write_bytes(b"x")
    (root / "_internal" / "openpyxl").mkdir()
    (root / "_internal" / "msoffcrypto").mkdir()
    (root / "app.exe").write_bytes(b"x")
    (root / "SHA256SUMS.txt").write_text("x", encoding="utf-8")
    if with_licenses:
        (root / "README-설치.txt").write_text("r", encoding="utf-8")
        (root / "LICENSES").mkdir()
        for n in ("LGPL-3.0.txt", "GPL-3.0.txt", "THIRD-PARTY-NOTICES.txt", "README-LICENSES.txt", "RELINK-Qt.txt"):
            (root / "LICENSES" / n).write_text("t", encoding="utf-8")
        (root / "BUILD-INFO.txt").write_text("b", encoding="utf-8")
    for e in extra:
        p = root / e
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    return root


def test_inventory_passes_a_complete_windows_style_dist_and_lists_qt_modules(tmp_path):
    d = make_fake_dist(tmp_path / "dist")
    r = inv.inspect(d, "qt", platform="windows", check_pyz=False)
    assert r["problems"] == [] and set(r["qt_libraries"]) == {"Qt6Core", "Qt6Gui", "Qt6Widgets"} and r["plugins"] == ["platforms/qwindows.dll"]
    assert set(r["pyside_modules"]) == {"QtCore", "QtGui", "QtWidgets"}


@pytest.mark.parametrize("missing", ["Qt6Widgets.dll", "shiboken6.abi3.dll"])
def test_inventory_fails_when_a_required_qt_file_is_missing(tmp_path, missing):
    d = make_fake_dist(tmp_path / "dist")
    (d / "_internal" / "PySide6" / missing).unlink()
    assert inv.inspect(d, "qt", platform="windows", check_pyz=False)["problems"]


def test_inventory_fails_without_the_windows_platform_plugin(tmp_path):
    d = make_fake_dist(tmp_path / "dist")
    (d / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll").unlink()
    assert any("플랫폼" in p for p in inv.inspect(d, "qt", platform="windows", check_pyz=False)["problems"])


@pytest.mark.parametrize("extra,needle", [(["policy_daechung.json"], "정책"), (["template_ai.xlsx"], "xlsx"), (["_internal/data/sample.xlsx"], "xlsx"), (["_internal/PySide6/QtNetwork.pyd"], "QtNetwork")])
def test_inventory_rejects_network_bindings_policies_templates_and_workbooks(tmp_path, extra, needle):
    d = make_fake_dist(tmp_path / "dist", extra=extra)
    assert any(needle in p for p in inv.inspect(d, "qt", platform="windows", check_pyz=False)["problems"])


def test_inventory_requires_licenses_and_docs_for_release_kinds(tmp_path):
    d = make_fake_dist(tmp_path / "dist", with_licenses=False)
    assert len(inv.inspect(d, "qt", platform="windows", check_pyz=False)["problems"]) >= 3
    assert inv.inspect(d, "dev", platform="windows", check_pyz=False)["problems"] == []                # 개발용 빌드는 배포 자료가 필요 없다


def test_inventory_flags_unexpected_qt_modules_for_license_review_without_failing(tmp_path):
    d = make_fake_dist(tmp_path / "dist", extra=["_internal/PySide6/Qt6Svg.dll", "_internal/PySide6/plugins/imageformats/qsvg.dll"])
    r = inv.inspect(d, "qt", platform="windows", check_pyz=False)
    assert r["problems"] == [] and "Qt6Svg" in r["review_qt_libraries"] and "imageformats/qsvg.dll" in r["plugins"]


def test_inventory_cli_writes_json_and_returns_nonzero_on_problems(tmp_path, capsys):
    d = make_fake_dist(tmp_path / "dist", extra=["policy_ai.json"])
    out = tmp_path / "inv.json"
    assert inv.main([str(d), "--kind", "qt", "--platform", "windows", "--no-pyz", "--json", str(out)]) == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["problems"] and "Qt6Core" in data["qt_libraries"]


def test_source_code_imports_only_the_expected_qt_modules():
    """코드가 쓰는 Qt 모듈은 QtCore/QtGui/QtWidgets 뿐이다(테스트 전용 QtTest 제외). 라이선스 모듈 점검의 근거."""
    used = set()
    for p in (ROOT / "src").rglob("*.py"):
        used |= set(re.findall(r"from PySide6\.(Qt\w+) import|import PySide6\.(Qt\w+)", p.read_text(encoding="utf-8")) and
                    [a or b for a, b in re.findall(r"from PySide6\.(Qt\w+) import|import PySide6\.(Qt\w+)", p.read_text(encoding="utf-8"))])
    assert used == {"QtCore", "QtGui", "QtWidgets"}


# ---------- 실제 빌드에서 발견한 결함의 회귀 ----------
def test_builds_copy_package_metadata_so_versions_and_licenses_are_readable_at_runtime():
    qt = " ".join(build.pyinstaller_args("qt", "0.3.0-rc.1", windowed=True))
    legacy = " ".join(build.pyinstaller_args("legacy", "0.3.0-rc.1", windowed=True))
    for dist in ("openpyxl", "et-xmlfile", "msoffcrypto-tool", "cryptography", "olefile", "PySide6-Essentials", "shiboken6"):
        assert f"--copy-metadata {dist}" in qt, dist
    assert "--copy-metadata openpyxl" in legacy and "--copy-metadata PySide6-Essentials" not in legacy


def test_version_text_falls_back_to_the_module_version_when_package_metadata_is_missing(monkeypatch):
    import importlib.metadata as m
    from scholarship_payment.ui import app_main
    monkeypatch.setattr(app_main.metadata, "version", lambda n: (_ for _ in ()).throw(m.PackageNotFoundError(n)))
    assert app_main._version_of("openpyxl") not in ("", "확인 불가")


def test_inventory_finds_a_versioned_executable_name_and_macos_frameworks(tmp_path):
    d = tmp_path / "dist"
    (d / "_internal" / "PySide6" / "Qt" / "lib" / "QtCore.framework" / "Versions" / "A").mkdir(parents=True)
    (d / "_internal" / "PySide6" / "Qt" / "lib" / "QtCore.framework" / "Versions" / "A" / "QtCore").write_bytes(b"x")
    assert "Qt6Core" in inv.inspect(d, "dev", platform="darwin", check_pyz=False)["qt_libraries"]
    (d / "ScholarshipPayment-v0.3.0-rc.1").write_bytes(b"x")
    assert inv.find_executable(d).name == "ScholarshipPayment-v0.3.0-rc.1"
    (d / "ScholarshipPayment-v0.3.0-rc.1.exe").write_bytes(b"x")
    assert inv.find_executable(d).name.endswith(".exe")


def test_a_bundled_qt_network_library_is_a_review_item_not_a_failure_but_the_binding_is(tmp_path):
    """QtNetwork 바인딩을 제외해도 다른 Qt 모듈의 전이 의존성으로 Qt6Network 라이브러리가 들어올 수 있다. 코드가 쓰는 것은 아니므로 라이선스 검토 항목으로만 남긴다."""
    d = make_fake_dist(tmp_path / "dist", extra=["_internal/PySide6/Qt6Network.dll"])
    r = inv.inspect(d, "qt", platform="windows", check_pyz=False)
    assert r["problems"] == [] and "Qt6Network" in r["review_qt_libraries"]


def test_inventory_reads_macos_style_plugin_paths(tmp_path):
    d = make_fake_dist(tmp_path / "dist")
    (d / "_internal" / "PySide6" / "Qt" / "plugins" / "platforms").mkdir(parents=True)
    (d / "_internal" / "PySide6" / "Qt" / "plugins" / "platforms" / "libqcocoa.dylib").write_bytes(b"x")
    r = inv.inspect(d, "qt", platform="darwin", check_pyz=False)
    assert "platforms/libqcocoa.dylib" in r["plugins"] and not [p for p in r["problems"] if "플랫폼" in p]


# ---------- 두 EXE(Qt·legacy)가 같은 변환 엔진을 담고 있는지 비교 ----------
parity = _load(ROOT / "tools" / "ci" / "compare_engine.py", "compare_engine")


def test_engine_module_selection_covers_the_conversion_pipeline_but_not_the_screens():
    names = ["scholarship_payment.adapters.daechung", "scholarship_payment.validation.validator", "scholarship_payment.writers.template_writer",
             "scholarship_payment.io.safe_save", "scholarship_payment.core.bank_codes", "scholarship_payment.models.payment", "scholarship_payment.config.policy_file",
             "scholarship_payment.app.convert", "scholarship_payment.errors", "scholarship_payment.ui.step3", "scholarship_payment.gui.app", "scholarship_payment.app.controller",
             "scholarship_payment.app.workflow", "scholarship_payment.config.user_settings", "openpyxl.workbook"]
    chosen = parity.engine_modules(names)
    assert "scholarship_payment.app.convert" in chosen and "scholarship_payment.adapters.daechung" in chosen and "scholarship_payment.errors" in chosen
    assert not [n for n in chosen if n.startswith(("scholarship_payment.ui", "scholarship_payment.gui", "openpyxl")) or n.endswith(("controller", "workflow", "user_settings"))]


def test_comparison_reports_identical_missing_and_different_engine_modules():
    a = {"scholarship_payment.app.convert": "d1", "scholarship_payment.adapters.daechung": "d2", "scholarship_payment.errors": "d3"}
    assert parity.compare(a, dict(a)) == []
    b = dict(a)
    b["scholarship_payment.adapters.daechung"] = "different"
    del b["scholarship_payment.errors"]
    b["scholarship_payment.core.extra"] = "d9"
    problems = " | ".join(parity.compare(a, b))
    assert "내용이 다르다: scholarship_payment.adapters.daechung" in problems and "legacy 에 없다: scholarship_payment.errors" in problems and "Qt 에 없다: scholarship_payment.core.extra" in problems


def test_comparison_refuses_an_empty_selection():
    assert parity.compare({}, {})                                                  # 엔진 모듈을 하나도 못 찾으면 통과로 치지 않는다


# ---------- 재현 가능한 빌드: 고정 버전 ----------
def _pins():
    out = {}
    for line in (ROOT / "packaging" / "rc-constraints.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, ver = line.split("==")
            out[notices.normalize(name)] = ver
    return out


def test_constraints_pin_exact_versions_and_satisfy_the_project_requirements():
    from packaging.requirements import Requirement
    pins = _pins()
    assert all(re.fullmatch(r"\d+(\.\d+)*", v) for v in pins.values())
    import tomllib
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    reqs = cfg["project"]["dependencies"] + cfg["project"]["optional-dependencies"]["gui"]
    for r in map(Requirement, reqs):
        assert notices.normalize(r.name) in pins and r.specifier.contains(pins[notices.normalize(r.name)]), r.name


def test_every_notice_package_is_pinned_for_the_release_build():
    pins = _pins()
    missing = [n for n, _ in notices.PACKAGES if notices.normalize(n) not in pins]
    assert missing == []


def test_workflow_uses_the_build_script_the_constraints_and_the_release_names():
    wf = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert wf.count("packaging/rc-constraints.txt") >= 2                              # 두 작업 모두 고정 버전으로 설치
    for needle in ("build_release.py --kind legacy", "build_release.py --kind qt", "build_release.py --kind dev", "release_info.py artifact-name",
                   "inventory_dist.py", "compare_engine.py", "--synthetic-e2e-smoke", "--gallery"):
        assert needle in wf, needle
    assert "run_gui_qt.py" not in wf and "pyinstaller --noconfirm" not in wf          # 명령은 스크립트 한 곳에만 둔다


def test_dev_build_has_its_own_artifact_name_and_the_release_artifact_is_the_qt_build():
    wf = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert 'artifact-name dev' in wf and 'artifact-name qt' in wf and 'artifact-name legacy' in wf
    assert "ScholarshipPaymentUI-dev" not in wf.replace("(ScholarshipPaymentUI-dev, 합성 E2E 전용·사용자 배포 금지)", "")        # 이름은 release_info 에서만 정한다
    for kind in ("qt", "legacy", "dev"):
        assert f"steps.{ {'qt': 'qt', 'legacy': 'build', 'dev': 'dev'}[kind] }.outputs.artifact" in wf


def test_workflow_rejects_development_flags_on_the_production_exe_with_exit_code_2():
    wf = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert '@("--gallery")' in wf and '@("--synthetic-e2e-smoke")' in wf and "ExitCode -ne 2" in wf
    assert "--kind dev" in wf and wf.index("--kind qt") < wf.index("--kind dev")


# ---------- 고지문에 라이선스 전문이 실제로 들어가는지 ----------
@needs_qt_installed
def test_notices_include_the_real_license_texts_of_every_package_that_ships_them():
    text = notices.render("qt")
    assert "Permission is hereby granted, free of charge" in text                       # MIT 계열 전문(openpyxl 등)
    assert "Apache License" in text and "BSD" in text                                    # cryptography 의 이중 라이선스 전문
    assert text.count("이 패키지에서 라이선스 파일을 찾지 못했습니다") == 0                  # 전문이 있는 패키지를 놓치지 않는다


def test_missing_python_license_text_is_stated_explicitly_not_silently_omitted(monkeypatch, tmp_path):
    monkeypatch.setattr(notices.sys, "base_prefix", str(tmp_path))
    assert "Python 라이선스 전문을 이 빌드 환경에서 찾지 못했습니다" in notices.render("legacy")


def test_inventory_flags_notices_that_lack_license_texts(tmp_path):
    d = make_fake_dist(tmp_path / "dist")
    (d / "LICENSES" / "THIRD-PARTY-NOTICES.txt").write_text("x 이 패키지에서 라이선스 파일을 찾지 못했습니다 y", encoding="utf-8")
    assert any("전문" in p for p in inv.inspect(d, "qt", platform="windows", check_pyz=False)["problems"])
