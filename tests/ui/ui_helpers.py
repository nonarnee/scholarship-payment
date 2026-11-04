"""UI 테스트 공용 상수(완전 합성 값만)."""
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
SYNTH_VALUES = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
