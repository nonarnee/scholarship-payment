"""학교 PC UAT 체크리스트와 결과 양식(Phase 5-B 준비 자료). 실행하지 않은 항목은 모두 '미검증'이고, 결과 문서에 개인정보·실제 파일명·민감한 통계를 쓰지 못하게 안내한다."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = (ROOT / "docs" / "UAT-CHECKLIST.md").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "docs" / "UAT-RESULT-TEMPLATE.md").read_text(encoding="utf-8")

REQUIRED_TOPICS = {
    "U01": "실제 창", "U02": "100%", "U03": "125%", "U04": "150%", "U05": "1366", "U06": "파일 대화상자", "U07": "드래그 앤 드롭", "U08": "설정 저장",
    "U09": "대청교", "U10": "다문화", "U11": "AI멘토링", "U12": "암호", "U13": "미리보기", "U14": "파일 변경", "U15": "저장 오류", "U16": "Excel", "U17": "인쇄",
    "U18": "서식", "U19": "WINS", "U20": "SmartScreen", "U21": "네트워크 드라이브", "U22": "OneDrive", "U23": "접근성", "U24": "롤백",
}


def ids(text):
    return set(re.findall(r"\bU\d{2}\b", text))


def rows(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"\|\s*(U\d{2})\s*\|(.*)\|\s*$", line)
        if m:
            out[m.group(1)] = [c.strip() for c in m.group(2).split("|")]
    return out


def test_checklist_covers_every_required_topic_with_one_section_each():
    for uid, topic in REQUIRED_TOPICS.items():
        sec = re.search(rf"^### {uid}\b.*?(?=^### U\d{{2}}\b|\Z)", CHECKLIST, re.S | re.M)
        assert sec, uid
        assert topic in sec.group(0), (uid, topic)
        for part in ("절차", "기대 결과"):
            assert part in sec.group(0), (uid, part)


def test_checklist_and_result_template_use_exactly_the_same_ids():
    assert ids(CHECKLIST) == ids(TEMPLATE) and set(REQUIRED_TOPICS) <= ids(CHECKLIST)


def test_every_result_row_is_unverified_by_default():
    r = rows(TEMPLATE)
    assert set(r) == ids(TEMPLATE) and r
    for uid, cells in r.items():
        assert cells[0] == "미검증" and cells[1] == "-", uid                   # 판정 칸은 미검증, 결함 등급은 비어 있음
        assert not re.search(r"통과|실패|\[x\]|✔|✅", " ".join(cells)), uid


def test_nothing_is_pre_checked_and_no_completion_is_claimed():
    for doc in (CHECKLIST, TEMPLATE):
        assert "[x]" not in doc.lower() and "✅" not in doc and "✔" not in doc
    assert "수행하지 않았" in CHECKLIST or "아직 수행하지 않았" in CHECKLIST                       # 이 문서 자체가 실행 결과가 아님을 밝힌다
    assert "미검증" in TEMPLATE


def test_data_handling_rules_forbid_personal_data_real_filenames_and_sensitive_statistics():
    for needle in ("학생 이름", "학번", "계좌번호", "실제 파일 이름", "금액", "인원", "로컬", "외부", "업로드", "private/"):
        assert needle in CHECKLIST, needle
    for needle in ("학생 이름", "학번", "계좌번호", "실제 파일 이름", "합계", "경로 전체", "사용자 이름"):
        assert needle in TEMPLATE, needle
    assert "스크린샷" in CHECKLIST and "저장소" in TEMPLATE                                      # 채운 결과는 저장소에 올리지 않는다


def test_result_template_has_metadata_fields_that_record_categories_not_identities():
    for needle in ("빌드 버전", "커밋", "Windows 버전", "Excel 버전", "DPI", "해상도", "계정 권한", "경로 유형", "결함 등급", "롤백"):
        assert needle in TEMPLATE, needle
    assert "이름:" not in TEMPLATE and "성명" not in TEMPLATE


def test_documents_contain_no_real_looking_personal_values():
    for doc in (CHECKLIST, TEMPLATE):
        assert not re.search(r"\b\d{6}-?\d{7}\b|\b\d{2,3}-\d{2,6}-\d{3,7}\b|@[a-z0-9.-]+\.(com|kr|net)|[A-Z]:\\Users\\", doc)


def test_checklist_lists_release_blocking_conditions_and_defect_severity():
    for needle in ("P0", "P1", "P2", "P3", "배포 불가", "중단"):
        assert needle in CHECKLIST, needle
