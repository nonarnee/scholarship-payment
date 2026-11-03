from scholarship_payment.config.default_paths import default_policy_path, search_dirs


def test_finds_first_existing_in_order(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    assert default_policy_path("daechung", [a, b]) is None
    (b / "policy_daechung.json").write_text("{}", encoding="utf-8")
    assert default_policy_path("daechung", [a, b]) == b / "policy_daechung.json"
    (a / "policy_daechung.json").write_text("{}", encoding="utf-8")
    assert default_policy_path("daechung", [a, b]) == a / "policy_daechung.json"


def test_other_programs_and_directories_do_not_match(tmp_path):
    (tmp_path / "policy_other.json").write_text("{}", encoding="utf-8")
    (tmp_path / "policy_daechung.json").mkdir()
    assert default_policy_path("daechung", [tmp_path]) is None


def test_appdata_dir_is_used_on_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert search_dirs()[-1] == tmp_path / "ScholarshipPayment"


def test_content_is_never_read(tmp_path):
    (tmp_path / "policy_daechung.json").write_bytes(b"\xff\xfe not json")
    assert default_policy_path("daechung", [tmp_path]) is not None


def test_default_template_path(tmp_path):
    from scholarship_payment.config.default_paths import default_template_path
    assert default_template_path("daechung", [tmp_path]) is None
    (tmp_path / "policy_daechung.json").write_text("{}", encoding="utf-8")
    assert default_template_path("daechung", [tmp_path]) is None          # 정책 파일과 혼동하지 않는다
    (tmp_path / "template_daechung.xlsx").write_bytes(b"x")
    assert default_template_path("daechung", [tmp_path]).name == "template_daechung.xlsx"
