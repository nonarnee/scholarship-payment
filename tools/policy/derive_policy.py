"""실제 템플릿에서 정책 JSON 초안을 만든다 (**로컬 전용**, 실제 템플릿 필요).

읽을 수 있는 항목(제외 시트 이름, WRIS 머리글)만 채우고, 읽을 수 없는 상수(제목·근로구분명·구분코드·적요)는
`<입력 필요>` 자리표시자로 둔다. 자리표시자가 남은 정책은 로더가 차단하므로 사람이 채워야 한다. 값은 추정하지 않는다.
출력 파일은 저장소의 `private/` 폴더 안에만 만들 수 있고(git 무시), 기존 파일은 덮어쓰지 않는다. 화면에는 키 이름과 개수만 낸다.

사용: python3 tools/policy/derive_policy.py <템플릿.xlsx> private/policy.local.json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from openpyxl import load_workbook  # noqa: E402

from scholarship_payment.config.policy_file import KEYS, PLACEHOLDER  # noqa: E402

LIST_PREFIX = "지급대상자명단("
KNOWN = {"WINS", "WRIS", "은행코드"}


def derive(template: Path) -> dict:
    wb = load_workbook(template, read_only=False)
    if "WRIS" not in wb.sheetnames:
        raise SystemExit("오류: WRIS 시트가 없는 템플릿입니다.")
    headers = [c.value for c in wb["WRIS"][1]]
    while headers and (headers[-1] is None or str(headers[-1]).strip() == ""):
        headers.pop()
    if not headers or any(not isinstance(h, str) or not h.strip() for h in headers):
        raise SystemExit("오류: WRIS 머리글(1행)을 문자열로 읽을 수 없습니다.")
    extra = [n for n in wb.sheetnames if n not in KNOWN and not n.startswith(LIST_PREFIX)]
    d = {k: PLACEHOLDER for k in KEYS}
    d["wris_headers"], d["excluded_sheets"], d["file_prefix"] = headers, extra, "지급명단"
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("template", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args(argv)
    out = args.out.resolve()
    if (ROOT / "private").resolve() not in out.parents:
        print("오류: 출력은 저장소의 private/ 폴더 안이어야 합니다.", file=sys.stderr)
        return 2
    if out.exists():
        print("오류: 출력 파일이 이미 있습니다(덮어쓰지 않음).", file=sys.stderr)
        return 2
    d = derive(args.template)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    todo = [k for k, v in d.items() if v == PLACEHOLDER]
    print(f"초안 생성: 머리글 {len(d['wris_headers'])}칸, 제외 시트 {len(d['excluded_sheets'])}개")
    print("직접 채워야 할 키:", ", ".join(todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
