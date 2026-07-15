# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_seteuk import check_text, find_name_intrusions

PROFILE = {"활동명": "가상 활동", "문두": "가상 활동에서", "목표바이트": 700, "상한바이트": 760}


def codes(issues):
    return [(lv, code) for lv, code, _ in issues]


def test_banned_word_detected():
    text = "가상 활동에서 작품을 읽고 또한 감상을 정리함."
    _, issues = check_text(text, PROFILE, exempt=True)
    assert ("FAIL", "BANNED_WORD") in codes(issues)


def test_ineun_word_boundary_no_false_positive():
    ok = "가상 활동에서 완벽해 보이는 존재를 분석함."
    _, issues = check_text(ok, PROFILE, exempt=True)
    assert ("FAIL", "BANNED_WORD") not in codes(issues)


def test_ineun_detected_as_word():
    bad = "가상 활동에서 분석함. 이는 큰 문제임을 밝힘."
    _, issues = check_text(bad, PROFILE, exempt=True)
    assert ("FAIL", "BANNED_WORD") in codes(issues)


def test_banned_char_hyphen():
    text = "가상 활동에서 두-세 가지 관점을 정리함."
    _, issues = check_text(text, PROFILE, exempt=True)
    assert ("FAIL", "BANNED_CHAR") in codes(issues)


def test_banned_char_straight_double_quote():
    text = '가상 활동에서 "인용문"을 정리함.'
    _, issues = check_text(text, PROFILE, exempt=True)
    assert ("FAIL", "BANNED_CHAR") in codes(issues)


def test_single_quote_allowed_for_book_title():
    text = "가상 활동에서 '가상의 책(작가)'을 읽고 감상을 정리함."
    _, issues = check_text(text, PROFILE, exempt=True)
    assert ("FAIL", "BANNED_CHAR") not in codes(issues)


def test_byte_over_fails():
    text = "가상 활동에서 " + "분석함. " * 80  # 760바이트 초과 유도
    _, issues = check_text(text, PROFILE)
    assert ("FAIL", "BYTE_OVER") in codes(issues)


def test_byte_under_warns_not_fails():
    text = "가상 활동에서 작품을 읽고 감상을 정리함."
    _, issues = check_text(text, PROFILE)
    assert ("WARN", "BYTE_UNDER") in codes(issues)
    assert not any(lv == "FAIL" and c == "BYTE_UNDER" for lv, c in codes(issues))


def test_opening_prefix_enforced():
    text = "이 학생은 작품을 열심히 분석함." + " 서술을 이어감." * 40
    _, issues = check_text(text, PROFILE)
    assert ("FAIL", "OPENING") in codes(issues)


def test_exempt_skips_opening_and_under():
    text = "가상 활동에 참여함."
    _, issues = check_text(text, PROFILE, exempt=True)
    assert ("FAIL", "OPENING") not in codes(issues)
    assert ("WARN", "BYTE_UNDER") not in codes(issues)


def test_name_intrusion_detected():
    assert find_name_intrusions("김가상 학생이 발표함.", ["김가상", "이허구"]) == ["김가상"]
    assert find_name_intrusions("작품을 분석함.", ["김가상", "이허구"]) == []
