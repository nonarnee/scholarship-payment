"""CI 전용: 패키징된 exe 가 합성 E2E 에서 만든 출력을 **exe 바깥(러너 파이썬)** 에서 검증한다.
- 결과 JSON 의 각 단계가 통과했는가, 실제로 패키징(frozen) 상태였는가
- 출력 XLSX 가 골든과 같은가(셀 값·타입·스타일·수식·병합·행 높이·열 너비·조건부 서식·인쇄 설정·시트 순서)
- 기존 파일 무덮어쓰기, 이전 임시 파일 보존, 이번 작업의 임시 파일 정리
사용: python tools/ci/verify_e2e_outputs.py <작업 폴더> <결과 JSON> [--require-frozen]   (문제가 있으면 목록을 출력하고 종료 코드 1)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "ci"))

from prepare_e2e_inputs import LEFTOVER_NAME, sha  # noqa: E402
from xlsx_dump import diff, dump  # noqa: E402

GOLDEN = ROOT / "tests" / "fixtures" / "golden" / "daechung_plain.json"


def verify(work_dir, result_json, require_frozen: bool = False) -> list[str]:
    work = Path(work_dir)
    problems: list[str] = []
    result = json.loads(Path(result_json).read_text(encoding="utf-8"))
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if require_frozen and not result.get("frozen"):
        problems.append("exe 가 패키징(frozen) 상태로 실행되지 않았다")
    if result.get("error"):
        problems.append(f"실행 중 예외: {result['error']}")
    for step in result.get("steps", []):
        if not step.get("ok"):
            problems.append(f"단계 실패: {step.get('name')} ({step.get('detail', '')})")
    missing_modules = [m for m, ok in result.get("modules", {}).items() if not ok]
    if missing_modules:
        problems.append(f"패키징에 빠진 모듈: {missing_modules}")
    if not result.get("steps"):
        problems.append("실행된 단계가 없다")

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    outputs = result.get("outputs", {})
    if set(outputs) != {"overwrite_avoided", "encrypted", "retry_after_folder_error"}:
        problems.append(f"예상한 출력 3개가 아니다: {sorted(outputs)}")
    for label, path in outputs.items():
        p = Path(path)
        if not p.is_file():
            problems.append(f"출력 파일 없음: {label}")
            continue
        got = dump(p)
        merged = {**got, **{k: golden[k] for k in ("filename", "count", "warnings", "notes")}}          # 파일 이름은 따로 확인한다
        d = diff(merged, golden)
        if d:
            problems.append(f"골든과 다름({label}): {d[:5]}")
    # 이름 규칙
    names = {k: Path(v).name for k, v in outputs.items()}
    if names.get("overwrite_avoided") != manifest["expected_name"].replace(".xlsx", "_2.xlsx"):
        problems.append("같은 이름이 있을 때 안전한 새 이름(_2)으로 저장하지 않았다")
    if names.get("encrypted") != manifest["expected_name"] or names.get("retry_after_folder_error") != manifest["expected_name"]:
        problems.append("출력 파일 이름이 예상과 다르다")
    # 무덮어쓰기 · 이전 임시 파일 보존 · 이번 작업의 임시 파일 정리
    ow = work / "out_overwrite"
    if sha(ow / manifest["expected_name"]) != manifest["existing_sha"]:
        problems.append("기존 결과 파일이 바뀌었다(덮어씀)")
    if not (ow / manifest["leftover_name"]).is_file() or sha(ow / manifest["leftover_name"]) != manifest["leftover_sha"]:
        problems.append("이전 실행의 임시 파일이 바뀌거나 지워졌다")
    stray = sorted(str(p.relative_to(work)) for p in work.rglob(".~*.xlsx") if p.name != LEFTOVER_NAME)
    if stray:
        problems.append(f"이번 작업의 임시 파일이 남았다: {stray}")
    return problems


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    issues = verify(args[0], args[1], "--require-frozen" in sys.argv)
    for line in issues:
        print("실패:", line)
    print("합성 E2E 출력 검증 " + ("통과" if not issues else f"실패({len(issues)}건)"))
    sys.exit(1 if issues else 0)
