"""배포 후보 빌드의 버전·산출물 이름 규칙(워크플로와 테스트가 함께 쓴다). 버전은 scholarship_payment.__version__ 하나만 쓴다.
사용: python packaging/release_info.py version | exe-name <qt|legacy|dev> | artifact-name <qt|legacy|dev> <커밋 SHA>
- qt: 신규 PySide6 화면(기본 산출물) / legacy: 기존 Tkinter 화면(한 릴리스 병행) / dev: 개발용 확인 빌드(합성 E2E 전용, 사용자에게 배포하지 않음)
"""
from __future__ import annotations

import re
import sys

_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?")
KINDS = ("qt", "legacy", "dev")


def parse(version: str) -> tuple[int, int, int, int | None]:
    """`1.2.3` 또는 `1.2.3-rc.N` 만 받는다. 반환: (major, minor, patch, rc 번호 또는 None)."""
    m = _VERSION.fullmatch(version)
    if not m:
        raise ValueError("version must look like 1.2.3 or 1.2.3-rc.1")
    major, minor, patch, rc = m.groups()
    return int(major), int(minor), int(patch), int(rc) if rc is not None else None


def current_version() -> str:
    from scholarship_payment import __version__

    parse(__version__)
    return __version__


def exe_name(kind: str, version: str) -> str:
    parse(version)
    if kind == "qt":
        return f"ScholarshipPayment-v{version}"
    if kind == "legacy":
        return f"ScholarshipPaymentLegacyTk-v{version}"
    if kind == "dev":
        return "ScholarshipPaymentUI-dev"
    raise ValueError("unknown kind")


def artifact_name(kind: str, version: str, sha: str) -> str:
    return f"{exe_name(kind, version)}-{sha[:7]}"


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "version":
        print(current_version())
    elif cmd == "exe-name":
        print(exe_name(argv[2], current_version()))
    elif cmd == "artifact-name":
        print(artifact_name(argv[2], current_version(), argv[3]))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
