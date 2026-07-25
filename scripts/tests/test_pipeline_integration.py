# -*- coding: utf-8 -*-
"""가명처리 파이프라인 통합 검증 — 수용 기준 5종.

1. 학번은 LLM 입력 전체에서 0건, 구조 필드 이름 0건
2. 학번 키 기준 토큰↔학번 1:1 전원 복원
3. 최종 세특 본문에 토큰 잔존 0건
4. 미제출자 토큰 미발급
5. 종료 시 매핑표 부존재 + 잔존 감지
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pseudonymize import (destroy_mapping, detect_stale_mapping, issue_tokens,
                          pseudonymize_text, reidentify, save_mapping, scan_leak,
                          scan_token_residue)

ROSTER = {"students": [
    {"학번": "10101", "이름": "김가상"},
    {"학번": "10102", "이름": "이허구"},
    {"학번": "10103", "이름": "박미정"},  # 미제출자
]}
SUBMITTED = ["10101", "10102"]
BODIES = {
    "10101": "10101 김가상. 봄을 노래한 시를 읽고 화자의 정서를 분석함.",
    "10102": "10102 이허구. 김가상과 함께 토론하며 관점을 넓힘.",
}
MEMO = "김가상은 수업 중 질문이 많았음."


def test_acceptance_criteria_end_to_end(tmp_path):
    mapping = issue_tokens(ROSTER, submitted_ids=SUBMITTED)

    # 기준 4: 미제출자 토큰 미발급
    assert "10103" not in mapping["map"]

    # 기준 1: LLM에 보낼 데이터에 학번 0건, 구조 필드 이름 0건
    llm_payload = []
    for sid, body in BODIES.items():
        masked, _ = pseudonymize_text(body, ROSTER, mapping)
        llm_payload.append({"학생": mapping["map"][sid], "본문": masked})
    memo_masked, _ = pseudonymize_text(MEMO, ROSTER, mapping)  # 관찰 메모도 가명화
    llm_payload.append({"학생": "", "본문": memo_masked})

    for item in llm_payload:
        assert not [i for i in scan_leak(item["본문"], ROSTER, scope="본문") if i[0] == "FAIL"]
        assert scan_leak(item["학생"], ROSTER, scope="구조") == []

    # 기준 2: 학번 키 1:1 전원 복원
    restored = {reidentify(item["학생"], mapping) for item in llm_payload if item["학생"]}
    assert restored == set(SUBMITTED)
    assert len(set(mapping["map"].values())) == len(SUBMITTED)

    # 기준 3: 최종 세특 본문 토큰 잔존 0건
    finals = [reidentify(item["본문"], mapping) for item in llm_payload]
    for text in finals:
        assert scan_token_residue(text) == []

    # 기준 5: 매핑표 파기와 잔존 감지
    mpath = tmp_path / "매핑.json"
    save_mapping(mapping, mpath)
    assert detect_stale_mapping(tmp_path)
    assert destroy_mapping(mpath) is True
    assert detect_stale_mapping(tmp_path) == []


def test_body_name_is_warning_not_blocker():
    """본문에 남은 이름은 경고이지 차단이 아니다(일반명사 이름 탐지의 한계 반영)."""
    mapping = issue_tokens(ROSTER, submitted_ids=SUBMITTED)
    issues = scan_leak("김가상과 함께 조사함.", ROSTER, scope="본문")
    assert issues and all(level == "WARN" for level, _, _ in issues)
