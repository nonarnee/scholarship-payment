"""PyInstaller 용 Windows 버전 리소스(파일 속성의 '자세히' 탭)를 만든다. 버전은 scholarship_payment.__version__ 하나만 쓴다.
사용: python packaging/make_version_info.py <출력 파일> [exe 이름]
숫자 버전(filevers/prodvers)은 (major, minor, patch, 0)이다 — 4칸 숫자는 `-rc.N` 표시를 담지 못하므로 문자열 FileVersion/ProductVersion 이 정본이다.
배포 후보(rc)면 Comments 에 '정식 배포 전 후보 빌드'를 적는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PRODUCT = "장학금 지급명단 변환"
DESCRIPTION = "한국장학재단 월별지급승인 엑셀을 지급명단으로 변환하는 오프라인 도구"


def _parse(version: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location("release_info", Path(__file__).with_name("release_info.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse(version)


def render(version: str, exe_name: str) -> str:
    major, minor, patch, rc = _parse(version)
    tup = f"({major}, {minor}, {patch}, 0)"
    comments = "      StringStruct('Comments', '배포 후보(rc) 빌드 - 정식 배포 전 학교 PC 검증이 끝나지 않았습니다'),\n" if rc is not None else ""
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
{comments}    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def main(argv: list[str]) -> int:
    from scholarship_payment import __version__
    out = Path(argv[1])
    name = argv[2] if len(argv) > 2 else f"ScholarshipPayment-v{__version__}"
    out.write_text(render(__version__, name), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
