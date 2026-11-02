#!/usr/bin/env python3
"""실제(비공개) 업무자료에서 '공개되면 안 되는 값' 목록을 로컬에만 생성한다.

사용: .venv/bin/python -I tools/safety/build_denylist.py <비공개 xlsx> [<비공개 xlsx> ...]
결과: .safety/denylist.local.txt  (.gitignore 대상. 절대 커밋·공유·출력하지 않는다)

수집 대상: 셀의 문자열·숫자 중 식별 가능성이 있는 값 전부(이름, 기관명, 학과, 사업자번호, 학번, 계좌,
상수 코드, 적요/제목 문자열, 금액 합계 후보). 값 자체는 화면에 출력하지 않고 개수만 보고한다.
기존 목록이 있으면 합집합으로 갱신한다.
"""
import re
import sys
from pathlib import Path
from openpyxl import load_workbook

# 일반 용어라 금지어로 쓰면 오탐만 늘어나는 값
GENERIC = {"year", "month", "money", "remark", "순번", "성명", "학번", "학과", "은행명", "계좌번호", "비고", "합계", "합 계", "미처리", "일치", "시간", "시급", "년월"}
MIN_LEN = 3


def candidates(wb):
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if v is None or isinstance(v, bool):
                    continue
                if isinstance(v, str):
                    s = v.strip()
                    if s.startswith("="):
                        continue
                    for part in re.split(r"[\n\r]+", s):
                        part = part.strip()
                        if re.fullmatch(r"\d+시간(\d+분)?", part):   # 활동시간 표기는 일반 값이라 제외
                            continue
                        if len(part) >= MIN_LEN and part not in GENERIC:
                            yield part
                elif isinstance(v, (int, float)):
                    n = int(v)
                    if abs(n) >= 100000:                      # 학번·금액·합계 후보
                        yield str(n)
                        yield f"{n:,}"


def public_strings(root):
    """공개 가능한 구조 문자열(합성 파일의 라벨 + public_terms.txt)은 금지어에서 뺀다."""
    ok = set()
    for pat in ("templates/synthetic_*.xlsx", "tests/fixtures/synthetic/synthetic_*.xlsx"):
        for f in root.glob(pat):
            ok |= set(candidates(load_workbook(f, data_only=False)))
    pt = root / "tools" / "safety" / "public_terms.txt"
    if pt.exists():
        ok |= {l.strip() for l in pt.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
    return ok


def main(paths):
    root = Path(__file__).resolve().parents[2]
    out = root / ".safety" / "denylist.local.txt"
    out.parent.mkdir(exist_ok=True)
    existing = set(out.read_text(encoding="utf-8").splitlines()) if out.exists() else set()
    found = set()
    public = public_strings(root)
    for p in paths:
        wb = load_workbook(p, data_only=True)
        found |= set(candidates(wb))
        # 파일명 자체의 날짜/식별 조각(확장자 제외)
        stem = Path(p).stem
        found.add(stem)
        found.update(re.findall(r"\d{8}", stem))
    merged = sorted(((existing | found) - public) - {""})
    out.write_text("# 로컬 전용. 커밋 금지.\n" + "\n".join(x for x in merged if not x.startswith("#")) + "\n", encoding="utf-8")
    print(f"금지어 {len(merged)}개 기록(신규 {len(found - existing)}개) → {out.relative_to(root)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
