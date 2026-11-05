# 라이선스 점검 — 배포 후보 `0.3.0-rc.1`

> 작성: 2026-11-04. **실제로 확인한 사실과 미결정 사항을 구분한다. 법률 자문이 아니며 법적 결론을 내리지 않는다.**
> 이 문서가 "준수 완료"를 뜻하지 않는다. 정식 배포 전에 확인해야 할 조건은 §6 에 있다.

## 1. 포함되는 구성 요소 (정확한 버전과 라이선스 표기)
버전은 Windows CI 에서 실제로 설치되어 검증을 통과한 값이며 `packaging/rc-constraints.txt` 로 고정한다. 라이선스 표기는 각 패키지의 설치 메타데이터에서 읽은 값이다(빌드 때 `THIRD-PARTY-NOTICES.txt` 로 다시 생성된다).

| 구성 요소 | 버전 | 라이선스 표기(메타데이터) | 고지·전문 |
|---|---|---|---|
| PySide6-Essentials (Qt for Python, Qt 라이브러리 포함) | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | **pip 배포본에 전문 파일이 없다** → `LICENSES/LGPL-3.0.txt`·`GPL-3.0.txt` 동봉 |
| shiboken6 | 6.12.0 | 위와 같음 | 위와 같음 |
| openpyxl | 3.1.5 | MIT | 패키지의 라이선스 파일을 고지문에 포함 |
| et-xmlfile | 2.0.0 | MIT | 위와 같음 |
| msoffcrypto-tool | 6.1.0 (로컬 개발 환경은 6.0.0) | MIT | 위와 같음 |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Apache·BSD 전문을 고지문에 포함 |
| olefile | 0.47 | BSD | 패키지의 라이선스 파일 포함 |
| cffi | 2.1.1 | MIT-0 | 포함 |
| pycparser | 3.12 | BSD-3-Clause | 포함 |
| PyInstaller(부트로더가 실행 파일에 포함) | 6.11.1 | 메타데이터 표기는 GPLv2(부트로더 예외 조항 해석은 §5 확인 필요) | `COPYING.txt` 를 고지문에 포함 |
| Python 실행 환경 | 3.12(러너) | PSF License | Python 설치 폴더의 `LICENSE.txt` 를 고지문에 포함하도록 했으나 **Windows 러너에서 실제로 들어갔는지는 CI 산출물로 확인해야 한다(미확인)** |

legacy(Tkinter) 산출물에는 PySide6·shiboken6 가 없고, 나머지 구성 요소와 Tcl/Tk(Python 에 포함)가 있다. Tcl/Tk 고지는 Python 의 `LICENSE.txt` 범위로 보며 별도 확인이 필요하다(미확인).

## 2. Qt 사용 범위 (실제 확인)
- **코드가 직접 import 하는 Qt 모듈**: QtCore, QtGui, QtWidgets 뿐이다(`tests/unit/test_release_assets.py` 가 소스를 검사한다). QtNetwork 는 쓰지 않고 PyInstaller 에서 바인딩을 제외한다.
- **산출물에 실제로 들어 있는 Qt 라이브러리·플러그인**은 `tools/ci/inventory_dist.py` 로 목록을 만든다.
  - macOS 개발 머신에서 만든 예비 빌드의 결과: Qt6Core, Qt6Gui, Qt6Widgets(필수), 그리고 **코드가 직접 쓰지 않는데 들어 있는** Qt6DBus, Qt6Svg, Qt6Network(전이 의존성). 이 목록은 **macOS 산출물 기준**이며 Windows 산출물의 근거가 아니다.
  - **Windows 산출물의 목록은 CI 아티팩트 `release-inventory-qt-<커밋>` 에서 확인해야 한다 — 아직 Windows 빌드를 실행하지 않아 미확인이다.**
- 코드가 직접 쓰지 않는 Qt 라이브러리(위의 Qt6Svg, Qt6Network 등)는 "검토 필요" 목록으로 남기고, 각각의 라이선스 구분(LGPL 가능 여부)은 Qt 공식 라이선스 문서로 배포 전에 확인한다.
- 공식 Qt 문서에서 GPL 전용 모듈로 열거된 것에 QtCore·QtGui·QtWidgets 는 없다(`docs/UI-FRAMEWORK.md` §3 의 조회 결과). 전이 의존성으로 들어온 모듈에 대해서는 **미확인**이다.

## 3. LGPL v3 의무와 현재 준비 상태 (Qt 오픈소스 라이선스 FAQ 기준)
| 의무 | 현재 준비 | 상태 |
|---|---|---|
| LGPL 전문 제공과 사용 고지 | `LICENSES/LGPL-3.0.txt`·`GPL-3.0.txt`(공식 텍스트), `README-LICENSES.txt`, 설치·실행 안내문, 앱 '정보' 화면의 안내 | 준비됨. **문구는 배포 전 검토 필요** |
| 사용한 Qt 라이브러리의 소스 제공(링크만으로는 불충분) | `README-LICENSES.txt` 에 방식이 **미결정**임을 명시 | **미결정** |
| 사용자가 다른 버전의 Qt 로 교체할 수 있게 함 | onedir 폴더에 Qt 파일이 별도로 들어가는 구조, `RELINK-Qt.txt` 초안 | 구조상 가능해 보임. **다른 버전으로 실제 교체해 실행하는 검증은 수행하지 않음(미검증)** |
| 앱 자체 코드의 공개 의무 없음(동적 사용) | Qt FAQ 의 설명. 앱 코드는 Qt 를 수정하지 않고 사용 | 법무 확인 필요 |

**onedir 방식이라는 이유만으로 위 의무가 충족되었다고 보지 않는다.**

## 4. 이번 점검에서 발견한 것
1. PySide6/shiboken6 의 pip 배포본에는 라이선스 전문 파일이 없다 → 전문을 배포 폴더에 별도로 넣는다.
2. PyInstaller 가 일부 패키지의 설치 메타데이터를 기본으로 넣지 않아, 패키징된 exe 의 `--version`·정보 화면에서 버전이 "확인 불가"로 나왔다 → `--copy-metadata` 로 해결하고 회귀 테스트를 추가했다.
3. 제3자 고지문 생성기가 일부 패키지의 라이선스 파일을 읽지 못해 "찾지 못했습니다"로 남기던 결함을 고쳤다. 이제 빠지면 CI 점검이 실패한다.
4. 코드가 쓰지 않는 Qt6Network·Qt6Svg 라이브러리가 전이 의존성으로 들어온다(macOS 예비 빌드). 검토 목록으로 남겼다.
5. 빌드마다 최신 버전이 설치되어 고지 대상이 달라질 수 있었다 → 버전을 고정(`packaging/rc-constraints.txt`)하고, 고지 대상 목록이 의존성과 어긋나면 테스트가 실패하게 했다.

## 5. 미결정·법률 검토가 필요한 사항 (임의로 정하지 않음)
1. **배포 범위**: 같은 기관 내부 사용만인지, 다른 기관·외부에 전달하는지. Qt FAQ 는 내부 사용을 직접 다루지 않는다(미확인).
2. **Qt/PySide6 소스 제공 방식**: 정확한 버전의 소스를 배포물에 동봉할지, 서면 제안으로 할지, 보관·제공 책임자와 기간.
3. 다른 버전의 Qt 로 실제 교체해 동작을 확인하는 검증을 할지(그리고 누가).
4. **앱 자체의 라이선스**: 결정 전이므로 저장소에 LICENSE 파일을 추가하지 않았다. 앱 화면과 안내문에도 앱 라이선스를 쓰지 않았다.
5. 상용 Qt 라이선스: 구매하지 않았다. 구매 여부는 별도 결정이다.
6. PyInstaller 부트로더의 라이선스 예외 조항이 이 배포 방식에 적용되는지 확인.
7. cryptography 의 이중 라이선스(Apache-2.0 OR BSD-3-Clause) 중 어느 쪽을 적용·표기할지.
8. Python(PSF)·Tcl/Tk 고지 문구가 충분한지.
9. 전이 의존성으로 들어온 Qt 라이브러리 각각의 라이선스 구분.

## 6. 정식 배포 전에 확인해야 할 조건
- [ ] §5 의 1·2 가 결정되었고, 외부 전달이면 법무 확인을 받았다.
- [ ] 소스 제공 방식에 따른 산출물(소스 동봉 또는 서면 제안문)이 배포물에 들어 있다.
- [ ] Windows CI 산출물의 Qt 목록(`release-inventory-qt-…`)을 검토했고 검토 필요 항목의 라이선스 구분을 확인했다.
- [ ] 고지문이 Windows 빌드에서 생성되어 라이선스 전문 누락이 없음을 확인했다(CI 점검 통과 + 사람이 열어 봄).
- [ ] `RELINK-Qt.txt` 의 절차를 실제로 시험했거나, 시험하지 않기로 한 결정이 문서화되었다.
- [ ] 정보 화면·안내문의 문구를 검토했다(준수가 끝났다는 표현이 없음).
- [ ] 앱 자체 라이선스 결정(필요하면 LICENSE 파일 추가는 별도 승인).

## 7. 근거 자료
- Qt 오픈소스 라이선스 FAQ: https://www.qt.io/faq/qt-open-source-licensing
- Qt 라이선스 문서: https://doc.qt.io/qt-6/licensing.html
- LGPL v3·GPL v3 전문: https://www.gnu.org/licenses/ (동봉 파일은 이 공식 텍스트)
