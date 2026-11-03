"""사업별 출력 정책(상수·문구·머리글 지문).

공개 저장소에는 **합성 기본값만** 둔다. 실제 근로구분명·구분코드·적요·실제 머리글은 이 객체를 외부 설정으로 만들어 주입한다
(docs/PUBLIC-SAFETY.md §5). 값이 확정되지 않은 사업(OPEN H3)은 기본값을 쓰지 않고 정책을 명시해야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputPolicy:
    list_title: str = "합성 데이터 — 가상 사업 지급 명단 ({month}월분)"      # 명단 A1. {year}, {month} 치환
    wins_work_name: str = "SYN-근로구분"
    wris_gub_a: str = "SYN-GUB-A"
    wris_gub_b: str = "SYN-GUB-B"
    remit_info: str = "가상사업({month}월)"                                  # WRIS 적요. {year}, {month} 치환
    wris_headers: tuple[str, ...] = ("gub_a", "gub_b", "verify_no", "payee_name", "total_money",
                                     "bank_code", "account_no", "depositor", "remit_info", "remark")
    excluded_sheets: tuple[str, ...] = ("업로드 결과(이력)",)               # 출력에서 제거하는 시트
    file_prefix: str = "지급명단"

    def title(self, year: int, month: int) -> str:
        return self.list_title.format(year=year, month=month)

    def remittance(self, year: int, month: int) -> str:
        return self.remit_info.format(year=year, month=month)


SYNTHETIC_POLICY = OutputPolicy()
