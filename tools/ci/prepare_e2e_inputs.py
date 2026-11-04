"""CI 전용: 패키징된 exe 의 합성 E2E 검증(`--synthetic-e2e-smoke`)에 쓸 입력을 **완전 합성**으로 만든다. 실제 자료는 쓰지 않는다.
사용: python tools/ci/prepare_e2e_inputs.py <작업 폴더>
만드는 것: inputs/plain.xlsx, inputs/encrypted.xlsx, template.xlsx, policy.json, out_* 폴더(이전 결과·이전 임시 파일 포함), manifest.json
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from msoffcrypto.format.ooxml import OOXMLFile

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "e2e-synthetic-pw!"
BASE_DATE = "2099.10.07"
EXPECTED_NAME = "지급명단_DAECHUNG_9999_09.xlsx"
EXISTING_BYTES = b"EXISTING-SYNTHETIC-RESULT"
LEFTOVER_NAME = ".~leftover_run.xlsx"
LEFTOVER_BYTES = b"LEFTOVER-SYNTHETIC-TEMP"
ROWS = 5


def _synthetic():
    spec = importlib.util.spec_from_file_location("make_synthetic", ROOT / "tools" / "synthetic" / "make_synthetic.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(work_dir) -> dict:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    (work / "inputs").mkdir(exist_ok=True)
    mk = _synthetic()
    plain = work / "inputs" / "plain.xlsx"
    mk.save_input(plain, ROWS, "numeric")                       # 테스트의 make_input 과 같은 합성 입력(빈 문자열 칸 포함)
    encrypted = work / "inputs" / "encrypted.xlsx"
    with open(plain, "rb") as f, open(encrypted, "wb") as o:
        OOXMLFile(f).encrypt(PASSWORD, o)
    (work / "template.xlsx").write_bytes((ROOT / "templates" / "synthetic_payment_template.xlsx").read_bytes())
    (work / "policy.json").write_bytes((ROOT / "templates" / "synthetic_policy.json").read_bytes())
    for name in ("out_overwrite", "out_encrypted", "out_retry_missing", "out_retry_new"):
        (work / name).mkdir(exist_ok=True)
    (work / "out_overwrite" / EXPECTED_NAME).write_bytes(EXISTING_BYTES)      # 같은 이름의 이전 결과(덮어쓰면 안 됨)
    (work / "out_overwrite" / LEFTOVER_NAME).write_bytes(LEFTOVER_BYTES)     # 이전 실행이 남긴 임시 파일(지우면 안 됨)
    manifest = {"password": PASSWORD, "base_date": BASE_DATE, "expected_name": EXPECTED_NAME, "rows": ROWS,
                "existing_sha": sha(work / "out_overwrite" / EXPECTED_NAME), "leftover_name": LEFTOVER_NAME, "leftover_sha": sha(work / "out_overwrite" / LEFTOVER_NAME)}
    (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("사용: prepare_e2e_inputs.py <작업 폴더>")
    prepare(sys.argv[1])
    print("합성 E2E 입력 준비 완료")
