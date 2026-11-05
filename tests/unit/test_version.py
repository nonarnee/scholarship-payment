import re
import tomllib
from pathlib import Path

import scholarship_payment


def test_version_is_semver_or_release_candidate_and_pyproject_reads_it_dynamically():
    assert re.fullmatch(r"\d+\.\d+\.\d+(-rc\.\d+)?", scholarship_payment.__version__)
    cfg = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in cfg["project"]["dynamic"] and "version" not in cfg["project"]
    assert cfg["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "scholarship_payment.__version__"}
