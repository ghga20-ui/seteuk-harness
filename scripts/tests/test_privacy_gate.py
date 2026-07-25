# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_seteuk import verify_drafts

PROFILE = {"활동명": "가상 활동", "문두": "가상 활동에서", "목표바이트": 700,
           "상한바이트": 760, "평가자료": "가상 채점표(테스트)"}

BODY = (
    "가상 활동에서 '가상의 책(작가)'을 선정하여 인물의 갈등에 주목하며 감상문을 작성함. "
    "서술 시점의 효과를 짚고 인물의 내적 갈등이 심화되는 과정을 정리함. "
    "작품에 반영된 사회 현실을 비판적으로 읽어냄. "
    "자신의 경험과 견주어 삶의 태도를 성찰하는 다짐을 밝힘. "
    "감상의 근거를 본문에서 찾아 제시하는 태도가 돋보임. "
    "작품을 자기 이해의 계기로 삼는 모습을 보임."
)


def _drafts(text):
    return {"classes": [{"name": "1반", "students": [
        {"학번": "10101", "이름": "김가상", "핵심소재": "가상의 책(작가)",
         "톤등급": "중", "세특": text, "비고": "", "예외": False}
    ]}]}


def test_token_residue_in_body_fails():
    report = verify_drafts(_drafts(BODY.replace("인물의 갈등", "S-3F7A의 갈등")), PROFILE)
    assert report["fail"] >= 1
    assert any(code == "TOKEN_RESIDUE" for r in report["rows"] for _, code, _ in r["issues"])


def test_clean_body_has_no_token_residue_fail():
    report = verify_drafts(_drafts(BODY), PROFILE)
    assert not any(code == "TOKEN_RESIDUE" for r in report["rows"] for _, code, _ in r["issues"])


def test_bare_student_id_in_body_fails():
    roster = {"students": [{"학번": "10101", "이름": "김가상"}]}
    body = BODY.replace("인물의 갈등", "10101의 갈등")
    report = verify_drafts(_drafts(body), PROFILE, roster=roster)
    assert any(code == "ID_IN_BODY" for r in report["rows"] for _, code, _ in r["issues"])


def test_unrelated_number_in_body_passes():
    roster = {"students": [{"학번": "10101", "이름": "김가상"}]}
    body = BODY.replace("인물의 갈등", "101010번 자료의 갈등")
    report = verify_drafts(_drafts(body), PROFILE, roster=roster)
    assert not any(code == "ID_IN_BODY" for r in report["rows"] for _, code, _ in r["issues"])
