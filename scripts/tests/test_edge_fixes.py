# -*- coding: utf-8 -*-
"""엣지 감사(3축 실측)가 찾은 결함 6건의 회귀 테스트. 등장인물은 전부 가상이다.

- 이메일이 마스킹을 통과해 LLM에 새던 경로(구글폼 CSV)
- 콤마 CSV 명렬이 0명이 되던 경로
- 4·6자리 학번 학교에서 점수·명렬이 통째로 실패하던 경로
- 활동명에 가운뎃점·붙임표가 있으면 저장 불가가 되던 교착
- 같은 학번이 두 반에 있어도 verify가 통과하던 구멍
- review-bundle이 짝 데이터를 흘리지 않아 검수 화면 짝 표시가 실전 0명이던 경로
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pseudonymize as P
import verify_seteuk as V


ROSTER = {"students": [{"학번": "30101", "이름": "김가상"}, {"학번": "30102", "이름": "이가상"}]}


def _mapping():
    return P.issue_tokens(ROSTER, ["30101", "30102"])


# ── 이메일 유출 차단 ─────────────────────────────────────────
def test_email_is_masked_in_body():
    out, warns = P.pseudonymize_text(
        "설문 응답: gasang.kim@example.com 으로 제출함.", ROSTER, _mapping(), owner_id="30101")
    assert "gasang.kim" not in out
    assert "[메일]" in out
    assert any("이메일" in w for w in warns)


def test_email_leak_is_caught_by_scan():
    issues = P.scan_leak("잔존 확인 tester@school.ac.kr 끝", ROSTER)
    assert any(code == "EMAIL_LEAK" and level == "FAIL" for level, code, _ in issues)


def test_clean_text_has_no_email_issue():
    issues = P.scan_leak("이메일 없는 평범한 문장.", ROSTER)
    assert not any(code == "EMAIL_LEAK" for _, code, _ in issues)


# ── CSV 명렬 ────────────────────────────────────────────────
def test_comma_csv_roster_is_parsed(tmp_path):
    f = tmp_path / "응답.csv"
    f.write_text('학번,이름\n30101,김가상\n30102,"이가상"\n', encoding="utf-8")
    r = P.detect_roster(f)
    assert len(r["students"]) == 2
    assert r["students"][0]["학번"] == "30101"


def test_tab_text_still_works(tmp_path):
    f = tmp_path / "명단.txt"
    f.write_text("학번\t이름\n30101\t김가상\n", encoding="utf-8")
    r = P.detect_roster(f)
    assert len(r["students"]) == 1


# ── 4·6자리 학번 ─────────────────────────────────────────────
def test_four_and_six_digit_ids_are_recognized(tmp_path):
    for sid in ("1101", "250101"):
        f = tmp_path / f"명단{sid}.txt"
        f.write_text(f"{sid} 김가상\n", encoding="utf-8")
        r = P.detect_roster(f)
        assert len(r["students"]) == 1, sid
        assert r["students"][0]["학번"] == sid


def test_score_accepts_four_digit_ids(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["학번", "이름", "점수"])
    ws.append(["1101", "김가상", 15])
    ws.append(["1102", "이가상", 13])
    f = tmp_path / "채점표.xlsx"; wb.save(str(f))
    roster4 = {"students": [{"학번": "1101", "이름": "김가상"}, {"학번": "1102", "이름": "이가상"}]}
    m = P.issue_tokens(roster4, ["1101", "1102"])
    result = P.parse_score_xlsx(f)
    assert result is not None and not (isinstance(result, dict) and result.get("ambiguous"))
    pairs = result[0]
    assert ("1101", 15) in [(s, v) for s, v in pairs]


# ── 활동명 특수문자 교착 해소 ─────────────────────────────────
PROFILE_DOT = {"활동명": "시·소설 비교-감상", "문두": "시·소설 비교-감상 활동에서",
               "목표바이트": 700, "상한바이트": 760, "평가자료": "가상 채점표 (확인)"}


def test_prefix_with_banned_chars_passes():
    text = PROFILE_DOT["문두"] + " 인물의 갈등에 주목하며 비평문을 작성함."
    _, issues = V.check_text(text, PROFILE_DOT)
    assert not any(code in ("BANNED_CHAR", "OPENING") for _, code, _ in issues), issues


def test_banned_char_in_body_still_fails():
    text = PROFILE_DOT["문두"] + ' 그는 "말했다"고 적음.'
    _, issues = V.check_text(text, PROFILE_DOT)
    assert any(code == "BANNED_CHAR" for _, code, _ in issues)


# ── 프로파일 규칙 오버라이드 (과목별 조정) ─────────────────────
def test_profile_can_override_banned_chars():
    math_profile = {**PROFILE_DOT, "문두": "수학 탐구 활동에서",
                    "금지문자패턴": "[\"“”]"}   # 수학은 부등호 허용
    text = "수학 탐구 활동에서 2^n>n^2 임을 귀납적으로 정리함."
    _, issues = V.check_text(text, math_profile)
    assert not any(code == "BANNED_CHAR" for _, code, _ in issues), issues


def test_global_rules_still_apply_without_override():
    text = PROFILE_DOT["문두"] + " 크기 비교 2>1 을 다룸."
    _, issues = V.check_text(text, PROFILE_DOT)
    assert any(code == "BANNED_CHAR" for _, code, _ in issues)


# ── 중복 학번 게이트 ─────────────────────────────────────────
GOOD = "가상 활동에서 '가상의 책(작가)'을 선정하여 인물의 갈등에 주목하며 비평문을 작성함."


def _draft(sid, cls="1반"):
    return {"학번": sid, "이름": "김가상", "핵심소재": "", "톤등급": "중",
            "세특": GOOD, "비고": "", "예외": True}


def test_duplicate_id_across_classes_fails():
    drafts = {"classes": [
        {"name": "1반", "students": [_draft("30101")]},
        {"name": "2반", "students": [_draft("30101")]},
    ]}
    report = V.verify_drafts(drafts, {"활동명": "가상 활동", "문두": "가상 활동에서",
                                      "목표바이트": 700, "상한바이트": 760, "평가자료": "확인"})
    all_issues = [c for row in report["rows"] for _, c, _ in row["issues"]]
    assert "DUP_ID" in all_issues


def test_unique_ids_pass():
    drafts = {"classes": [{"name": "1반", "students": [_draft("30101"), _draft("30102")]}]}
    report = V.verify_drafts(drafts, {"활동명": "가상 활동", "문두": "가상 활동에서",
                                      "목표바이트": 700, "상한바이트": 760, "평가자료": "확인"})
    all_issues = [c for row in report["rows"] for _, c, _ in row["issues"]]
    assert "DUP_ID" not in all_issues


# ── review-bundle 짝 흘려보내기 ──────────────────────────────
def test_pairs_flow_into_bundle():
    m = _mapping()
    drafts = {"classes": [{"name": "1반", "students": [
        {"학번": "30101", "이름": "김가상", "핵심소재": "", "톤등급": "중",
         "세특": GOOD, "비고": "", "예외": False,
         "짝": [{"n": 1, "세특": "인물의 갈등", "원문": "주인공의 갈등"}],
         "짝없음": ["모둠 토의에서"]}]}]}
    bundle = P.build_review_bundle(drafts, m)
    s = bundle["students"][0]
    assert s.get("짝") and s["짝"][0]["n"] == 1
    assert s.get("짝없음") == ["모둠 토의에서"]


def test_bundle_without_pairs_unchanged():
    m = _mapping()
    drafts = {"classes": [{"name": "1반", "students": [
        {"학번": "30101", "이름": "김가상", "핵심소재": "", "톤등급": "중",
         "세특": GOOD, "비고": "", "예외": False}]}]}
    bundle = P.build_review_bundle(drafts, m)
    assert "짝" not in bundle["students"][0]
