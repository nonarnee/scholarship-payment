"""제3자 고지문(THIRD-PARTY-NOTICES.txt) 생성. **빌드할 때 실제로 설치된 패키지**의 이름·버전·라이선스 표기와 라이선스 파일을 읽어 만든다.
- 목록에 있는 패키지가 설치되어 있지 않으면 조용히 건너뛰지 않고 실패한다(빌드가 잘못된 환경에서 도는 것을 막는다).
- 런타임 의존성이 늘어 목록에 없는 패키지가 생기면 테스트가 실패한다(고지 대상 검토를 강제).
- PySide6 의 pip 배포본에는 라이선스 전문이 들어 있지 않아, 배포 폴더의 LICENSES/LGPL-3.0.txt·GPL-3.0.txt 를 가리킨다.
이 문서는 법률 자문이 아니다.
"""
from __future__ import annotations

import importlib.metadata as metadata
import platform
import re
import sys
from pathlib import Path

QT_PACKAGES = (("PySide6-Essentials", "Qt for Python(PySide6) — Qt 라이브러리를 포함"), ("shiboken6", "PySide6 의 바인딩 생성·런타임 지원 라이브러리"))
COMMON_PACKAGES = (("openpyxl", "엑셀(.xlsx) 읽기·쓰기"), ("et-xmlfile", "openpyxl 이 쓰는 XML 지원"), ("msoffcrypto-tool", "암호가 걸린 엑셀 파일 복호화"),
                   ("cryptography", "msoffcrypto-tool 이 쓰는 암호 라이브러리"), ("olefile", "msoffcrypto-tool 이 쓰는 OLE 파일 읽기"),
                   ("cffi", "cryptography 가 쓰는 C 연동"), ("pycparser", "cffi 가 쓰는 C 파서"), ("pyinstaller", "실행 파일 패키징 도구(부트로더가 실행 파일에 포함됨)"))
PACKAGES = QT_PACKAGES + COMMON_PACKAGES
_LICENSE_FILE = re.compile(r"licen[sc]e|copying|notice", re.I)


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def packages_for(kind: str):
    return PACKAGES if kind == "qt" else COMMON_PACKAGES


def runtime_requirement_names(extra: str | None = None) -> set[str]:
    """scholarship-payment[extra] 의 런타임 의존성 전체(재귀)의 정규화된 이름. 설치된 메타데이터에서 읽는다."""
    from packaging.requirements import Requirement

    seen: set[str] = set()

    def visit(dist_name: str, extras: tuple[str, ...]) -> None:
        try:
            reqs = metadata.requires(dist_name) or []
        except metadata.PackageNotFoundError:
            return
        for line in reqs:
            r = Requirement(line)
            if r.marker is not None and not any(r.marker.evaluate({"extra": e}) for e in (extras or ("",))):
                continue
            n = normalize(r.name)
            if n not in seen:
                seen.add(n)
                visit(r.name, tuple(sorted(r.extras)))

    visit("scholarship-payment", (extra,) if extra else ())
    return seen


def _dist(name: str):
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError:
        raise RuntimeError(f"고지 대상 패키지가 설치되어 있지 않습니다: {name}") from None


def _license_expression(dist) -> str:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    lic = (md.get("License") or "").strip().splitlines()
    if lic and len(lic[0]) < 80:
        return lic[0]
    cls = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    return ", ".join(cls) or "확인 불가"


def _license_files(dist):
    out = []
    for f in dist.files or []:
        s = str(f)
        if _LICENSE_FILE.search(Path(s).name) and ("dist-info" in s or s.count("/") <= 1) and not s.endswith((".py", ".pyc", ".html")):
            try:
                text = Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = None
            if text:
                out.append((Path(s).name, text.strip()))
    return out


def render(kind: str) -> str:
    lines = ["제3자 소프트웨어 고지 (이 빌드에 포함된 구성 요소)", "=" * 50, "",
             f"이 파일은 빌드할 때 설치되어 있던 패키지 정보에서 생성되었습니다. Python {platform.python_version()} 용 빌드입니다.",
             "이 문서는 법률 자문이 아니며, 배포 전 확인해야 할 사항은 LICENSES 폴더의 README-LICENSES.txt 에 있습니다.", ""]
    body = []
    for name, role in packages_for(kind):
        dist = _dist(name)
        lines.append(f"- {name} {dist.version} — {_license_expression(dist)}  ({role})")
        files = _license_files(dist)
        body.append(f"\n{'-' * 70}\n{name} {dist.version}  |  {_license_expression(dist)}\n{'-' * 70}")
        if name in ("PySide6-Essentials", "shiboken6"):
            body.append("이 패키지(pip 배포본)에는 라이선스 전문 파일이 포함되어 있지 않아 이 폴더의 LGPL-3.0.txt 와 GPL-3.0.txt 를 참조합니다.\n"
                        "Qt 는 GNU LGPL v3 로 사용합니다. 소스 제공 방식·교체 가능성 등 미결정 사항은 README-LICENSES.txt 를 보세요.")
        elif not files:
            body.append("이 패키지에서 라이선스 파일을 찾지 못했습니다. 위의 라이선스 표기를 따릅니다(해당 프로젝트의 공식 배포처에서 전문을 확인하세요).")
        for fname, text in files:
            body.append(f"\n[{fname}]\n{text}")
    lines += ["", "Python 실행 환경", f"- Python {platform.python_version()} — PSF License (Python Software Foundation)"]
    py_license = Path(sys.base_prefix) / "LICENSE.txt"
    if py_license.is_file():
        body.append(f"\n{'-' * 70}\nPython {platform.python_version()} (PSF License)\n{'-' * 70}\n{py_license.read_text(encoding='utf-8', errors='replace').strip()}")
    else:
        body.append(f"\n{'-' * 70}\nPython {platform.python_version()} (PSF License)\n{'-' * 70}\nPython 라이선스 전문을 이 빌드 환경에서 찾지 못했습니다. https://docs.python.org/3/license.html 과 Python 설치 폴더의 LICENSE.txt 를 확인하세요.")
    if kind == "qt":
        lines += ["", "라이선스 전문: LGPL-3.0.txt, GPL-3.0.txt (같은 LICENSES 폴더)"]
    return "\n".join(lines + body) + "\n"


def main(argv: list[str]) -> int:
    kind, out = argv[1], Path(argv[2])
    out.write_text(render(kind), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
