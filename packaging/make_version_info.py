"""PyInstaller 용 Windows 버전 리소스(파일 속성의 '자세히' 탭)를 만든다. 버전은 scholarship_payment.__version__ 하나만 쓴다.
사용: python packaging/make_version_info.py <출력 파일>
"""
from __future__ import annotations

import sys
from pathlib import Path

PRODUCT = "장학금 지급명단 변환"
DESCRIPTION = "한국장학재단 월별지급승인 엑셀을 지급명단으로 변환하는 오프라인 도구"


def render(version: str, exe_name: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    tup = f"({major}, {minor}, {patch}, 0)"
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('ProductName', {PRODUCT!r}),
      StringStruct('FileDescription', {DESCRIPTION!r}),
      StringStruct('FileVersion', '{version}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('InternalName', {exe_name!r}),
      StringStruct('OriginalFilename', {exe_name + '.exe'!r}),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def main(argv: list[str]) -> int:
    from scholarship_payment import __version__
    out = Path(argv[1])
    out.write_text(render(__version__, f"ScholarshipPayment-v{__version__}"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
