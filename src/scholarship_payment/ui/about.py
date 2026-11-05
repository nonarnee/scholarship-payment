"""앱 정보 화면: 버전과 라이선스 안내.
- 버전·라이브러리 정보는 실제로 설치(패키징)된 메타데이터에서 읽는다(하드코딩 추측 없음).
- 이 화면은 **라이선스 준수가 끝났다고 주장하지 않는다.** 전문과 고지는 설치 폴더의 LICENSES 폴더에 있고, 정식 배포 전 확인 조건은 docs/LICENSE-REVIEW.md 에 있다.
- 앱 자체의 라이선스는 아직 결정되지 않았으므로 이 화면에 쓰지 않는다.
"""
from __future__ import annotations

import importlib.metadata as metadata
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from scholarship_payment import __version__
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import AppButton

LIBRARIES = (("PySide6", "PySide6-Essentials"), ("shiboken6", "shiboken6"), ("openpyxl", "openpyxl"), ("msoffcrypto-tool", "msoffcrypto-tool"), ("cryptography", "cryptography"))


@dataclass(frozen=True)
class LibraryRow:
    name: str
    version: str
    license: str


def _license_of(dist: str) -> str:
    try:
        md = metadata.metadata(dist)
    except metadata.PackageNotFoundError:
        return "확인 불가"
    return (md.get("License-Expression") or md.get("License") or "확인 불가").splitlines()[0][:60]


def library_rows() -> list[LibraryRow]:
    from scholarship_payment.ui.app_main import _version_of

    return [LibraryRow(name, _version_of(dist), _license_of(dist)) for name, dist in LIBRARIES]


def licenses_dir() -> Path | None:
    """패키징된 실행 파일 옆의 LICENSES 폴더(개발 환경에서는 None)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "LICENSES"
    return None


class AboutDialog(QDialog):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtCore import qVersion

        self.setWindowTitle("정보")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._ctx = context
        col = QVBoxLayout(self)
        m = SPACING["lg"]
        col.setContentsMargins(m, m, m, m)
        col.setSpacing(SPACING["md"])
        title = QLabel("장학금 지급명단 변환")
        title.setProperty("role", "headline")
        col.addWidget(title)
        rc = "-rc." in __version__
        self.version_label = QLabel(f"버전 {__version__}" + (" (배포 후보 — 정식 배포 전 학교 PC 검증이 끝나지 않았습니다)" if rc else ""))
        self.version_label.setWordWrap(True)
        col.addWidget(self.version_label)

        libs = QFrame()
        libs.setObjectName("Panel")
        ll = QVBoxLayout(libs)
        ll.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
        head = QLabel("사용한 구성 요소 (실제 설치된 버전)")
        head.setProperty("role", "section")
        ll.addWidget(head)
        import PySide6

        ll.addWidget(QLabel(f"Python {platform.python_version()}"))
        ll.addWidget(QLabel(f"Qt {qVersion()} (PySide6 {PySide6.__version__})"))
        for r in library_rows():
            ll.addWidget(QLabel(f"{r.name} {r.version} — {r.license}"))
        col.addWidget(libs)

        notice = QLabel("이 프로그램은 Qt(PySide6)를 사용합니다. Qt 는 GNU LGPL v3 라이선스로 제공됩니다. 라이선스 전문과 사용한 라이브러리의 고지는 "
                        "설치 폴더의 LICENSES 폴더에서 확인할 수 있습니다.")
        notice.setWordWrap(True)
        col.addWidget(notice)
        row = QHBoxLayout()
        self.licenses_button = AppButton("LICENSES 폴더 열기", "secondary")
        self.close_button = AppButton("닫기", "primary")
        self.licenses_hint = QLabel("")
        self.licenses_hint.setProperty("role", "hint")
        self.licenses_hint.setWordWrap(True)
        row.addWidget(self.licenses_button)
        row.addWidget(self.licenses_hint, 1)
        row.addWidget(self.close_button)
        col.addLayout(row)
        self._dir = licenses_dir()
        if self._dir is None:
            self.licenses_button.setEnabled(False)
            self.licenses_hint.setText("개발 환경입니다. 설치된 프로그램의 설치 폴더에 LICENSES 폴더가 있습니다.")
        elif not self._dir.is_dir():
            self.licenses_button.setEnabled(False)
            self.licenses_hint.setText("설치 폴더에서 LICENSES 폴더를 찾을 수 없습니다. 배포 파일이 온전한지 확인하세요.")
        self.licenses_button.clicked.connect(self._open_licenses)
        self.close_button.clicked.connect(self.accept)

    def _open_licenses(self) -> None:
        ok = self._dir is not None and self._ctx.system_actions.open_folder(self._dir)
        self.licenses_hint.setText("" if ok else "폴더를 열지 못했습니다. 설치 폴더의 LICENSES 폴더를 직접 여세요.")
