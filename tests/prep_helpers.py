"""Phase 3 테스트 공용(완전 합성): 정책 파일 만들기, 암호 파일 만들기, 변경 시뮬레이션."""
import os
from pathlib import Path

from msoffcrypto.format.ooxml import OOXMLFile

from scholarship_payment.config.policy_builder import make_policy_file

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "synthetic_payment_template.xlsx"
PW = "가짜-pw-0000!"
SYNTH_VALUES = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}


def make_policy(tmp_path, program="daechung"):
    return make_policy_file(TEMPLATE, SYNTH_VALUES, Path(tmp_path) / f"policy_{program}.json", program)


def encrypt(plain, dst, password=PW):
    with open(plain, "rb") as f, open(dst, "wb") as o:
        OOXMLFile(f).encrypt(password, o)
    return Path(dst)


def flip_byte_keep_size_and_mtime(path):
    st = os.stat(path)
    data = bytearray(Path(path).read_bytes())
    data[-1] ^= 0x01
    Path(path).write_bytes(bytes(data))
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
