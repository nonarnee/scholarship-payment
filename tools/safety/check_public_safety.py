#!/usr/bin/env python3
"""공개 저장소 반입 전 검사 (표준 라이브러리만 사용).

사용:
  python3 -I tools/safety/check_public_safety.py --staged        # 커밋 직전(훅)
  python3 -I tools/safety/check_public_safety.py --tracked       # 인덱스(커밋/스테이징된 내용) 전체
  python3 -I tools/safety/check_public_safety.py --worktree      # 작업트리의 추적+미추적(무시 안 된) 파일 전체
  python3 -I tools/safety/check_public_safety.py <파일> ...      # 지정 파일(작업트리)

검사 규칙 (위반 시 종료 코드 1):
  P1 경로      : 차단 디렉터리/확장자, 허용 위치 밖의 엑셀
  P2 엑셀 이름 : `synthetic_*.xlsx` 만 허용 (허용 디렉터리: templates/, tests/fixtures/synthetic/)
  X1 엑셀 속성 : 문서 속성에 SYNTHETIC-TEST-DATA 표식이 없거나 작성자가 일반 값이 아님
  X2 엑셀 구조 : 외부 링크, 매크로, 숨김 시트 등 금지
  T1 패턴      : 사업자번호·계좌·주민번호·전화·이메일·8자리 숫자(학번/날짜 의심) — 합성 예약값은 허용
  T2 로컬 금지어: .safety/denylist.local.txt (git 제외)에 적은 실제 값이 문서·코드·엑셀 어디에도 없어야 함

출력에는 **일치한 값을 절대 표시하지 않는다**(규칙 ID, 파일, 줄 번호, 길이만).
"""
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
DENYLIST = ROOT / ".safety" / "denylist.local.txt"
MARKER = "SYNTHETIC-TEST-DATA"
ALLOWED_AUTHORS = {"", "synthetic", "openpyxl", "synthetic-generator"}

BLOCKED_DIR_PREFIXES = ("samples/", "private/", "real/", ".safety/", ".venv/", "output/", "out/", "tmp/", "scratch/")
BLOCKED_EXT = {".xls", ".xlsm", ".xlsb", ".csv", ".tsv", ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".ppt", ".pptx", ".zip", ".db", ".sqlite", ".bak", ".log"}
EXCEL_ALLOWED_DIRS = ("templates/", "tests/fixtures/synthetic/")
TEXT_EXT = {".md", ".py", ".txt", ".toml", ".cfg", ".ini", ".yml", ".yaml", ".json", ".sh", ".gitignore", ""}

# 합성 예약값: 학번 00NNNNNN(문자열)/90NNNNNN(숫자), 년월 9999NNNN, 사업자번호 000-00-NNNNN, 계좌 000-000-NNNNNN, 이름 가상NNN
PATTERNS = [
    ("biz_no", re.compile(r"(?<!\d)(?!000-00-)\d{3}-\d{2}-\d{5}(?!\d)")),
    ("account", re.compile(r"(?<!\d)(?!000-000-|000-00-)\d{2,6}-\d{2,6}-\d{3,8}(?!\d)")),
    ("rrn", re.compile(r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)")),
    ("phone", re.compile(r"(?<!\d)01[016-9]-?\d{3,4}-?\d{4}(?!\d)")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("digits8", re.compile(r"(?<![\d-])(?!(?:00\d{6}|90\d{6}|9999\d{4})(?!\d))\d{8}(?![\d-])")),
]
# 문서 설명용으로 허용하는 이메일 도메인
EMAIL_OK = ("noreply@anthropic.com", "users.noreply.github.com")


def git_bytes(args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def load_denylist():
    if not DENYLIST.exists():
        return []
    items = []
    for line in DENYLIST.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            items.append(s)
    return items


# 패턴 검사기 자신과 그 시험은 '실값처럼 보이는 가짜 예시'를 포함해야 하므로 T1만 면제한다(T2 금지어는 그대로 적용).
T1_EXEMPT = {"tools/safety/check_public_safety.py", "tests/test_public_safety.py"}


def scan_text(label, text, deny, out, patterns=True):
    for ln, line in enumerate(text.splitlines(), 1):
        for rid, rx in (PATTERNS if patterns else []):
            for m in rx.finditer(line):
                if rid == "email" and any(ok in m.group(0) for ok in EMAIL_OK):
                    continue
                out.append((f"T1:{rid}", label, ln, f"len={len(m.group(0))}"))
        for d in deny:
            if d in line:
                out.append(("T2:denylist", label, ln, f"len={len(d)}"))


def xlsx_texts(data):
    """엑셀 내부의 모든 문자열/수식/속성 텍스트를 (파트, 텍스트)로 반환."""
    z = zipfile.ZipFile(io.BytesIO(data))
    for name in z.namelist():
        if name.endswith((".xml", ".rels")):
            raw = z.read(name).decode("utf-8", "replace")
            yield name, re.sub(r"<[^>]+>", "\n", raw)
    return


def check_xlsx(path, data, deny, out):
    name = Path(path).name
    if not re.fullmatch(r"synthetic[_-][\w.\-]*\.xlsx", name):
        out.append(("P2:excel_name", path, 0, "xlsx 이름은 synthetic_*.xlsx"))
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    if any(n.startswith("xl/externalLinks/") for n in names) or "xl/vbaProject.bin" in names:
        out.append(("X2:external_or_macro", path, 0, ""))
    core = z.read("docProps/core.xml").decode("utf-8", "replace") if "docProps/core.xml" in names else ""
    if MARKER not in core:
        out.append(("X1:no_synthetic_marker", path, 0, "docProps/core.xml 의 subject/keywords"))
    for tag in ("dc:creator", "cp:lastModifiedBy"):
        m = re.search(rf"<{tag}>([^<]*)</{tag}>", core)
        if m and m.group(1).strip().lower() not in ALLOWED_AUTHORS:
            out.append(("X1:author", path, 0, f"{tag} len={len(m.group(1))}"))
    wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
    if re.search(r'<sheet [^>]*state="(hidden|veryHidden)"', wb):
        out.append(("X2:hidden_sheet", path, 0, ""))
    for part, text in xlsx_texts(data):
        scan_text(f"{path}!{part}", text, deny, out)


def classify_and_check(path, data, deny, out):
    p = path.replace("\\", "/")
    if p.startswith(BLOCKED_DIR_PREFIXES):
        out.append(("P1:blocked_dir", p, 0, ""))
        return
    ext = Path(p).suffix.lower()
    if ext in BLOCKED_EXT:
        out.append(("P1:blocked_ext", p, 0, ext))
        return
    if ext == ".xlsx":
        if not p.startswith(EXCEL_ALLOWED_DIRS):
            out.append(("P1:excel_outside_allowed_dir", p, 0, ""))
            return
        check_xlsx(p, data, deny, out)
        return
    if p.endswith(".DS_Store") or "/__pycache__/" in p or ext == ".pyc":
        out.append(("P1:junk", p, 0, ""))
        return
    if ext in TEXT_EXT or Path(p).name in {".gitignore", "pre-commit"}:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            out.append(("P1:binary_unknown", p, 0, ""))
            return
        scan_text(p, text, deny, out, patterns=p not in T1_EXEMPT)
    else:
        out.append(("P1:unknown_type", p, 0, ext))


def main(argv):
    deny = load_denylist()
    out = []
    if "--staged" in argv:
        files = git_bytes(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]).decode().split("\0")
        items = [(f, git_bytes(["show", f":{f}"])) for f in files if f]
    elif "--worktree" in argv:
        files = git_bytes(["ls-files", "-co", "--exclude-standard", "-z"]).decode().split("\0")
        items = [(f, (ROOT / f).read_bytes()) for f in files if f and (ROOT / f).is_file()]
    elif "--tracked" in argv:
        files = git_bytes(["ls-files", "-z"]).decode().split("\0")
        items = [(f, git_bytes(["show", f":{f}"])) for f in files if f]
    else:
        items = []
        for a in argv:
            if a.startswith("--"):
                continue
            fp = Path(a).resolve()
            items.append((str(fp.relative_to(ROOT)), fp.read_bytes()))
    if not DENYLIST.exists():
        print("경고: .safety/denylist.local.txt 가 없어 T2(로컬 금지어) 검사를 건너뜁니다. "
              "tools/safety/build_denylist.py 로 생성하세요.", file=sys.stderr)
    for path, data in items:
        classify_and_check(path, data, deny, out)
    if out:
        print(f"공개 안전성 검사 실패: {len(out)}건 (일치한 값은 표시하지 않음)", file=sys.stderr)
        agg = {}
        for rid, path, ln, note in out:
            key = (rid, path.split("!")[0])
            first = agg.setdefault(key, [0, f"{path}:{ln}" if ln else path, note])
            first[0] += 1
        for (rid, base), (cnt, where, note) in sorted(agg.items()):
            print(f"  [{rid}] {base} x{cnt} (예: {where}) {note}", file=sys.stderr)
        return 1
    print(f"공개 안전성 검사 통과: {len(items)}개 파일, 로컬 금지어 {len(deny)}개 적용")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
