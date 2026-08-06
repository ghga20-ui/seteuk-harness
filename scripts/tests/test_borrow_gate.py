# -*- coding: utf-8 -*-
"""소화 원칙 게이트(BORROWED) 테스트 — 등장인물·글은 전부 가상.

세특이 학생 원문의 표현에 붙어 있는 정도를 토큰 단계에서 WARN으로 보고한다.
실측(2026-07-31): 축자 인용(12자+)은 드물고(평균 2%), 문제는 조사만 바꾼
8자 수준 구절 차용(평균 8%, 최대 31%)이었다 — 그래서 창이 8자다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify_seteuk as V

PROFILE = {"활동명": "가상 활동", "문두": "가상 활동에서",
           "목표바이트": 700, "상한바이트": 760, "평가자료": "가상 채점표 (확인)"}

SRC = ("나는 가상의 책을 읽고 국가 폭력 앞에서 개인의 존엄이 어떻게 지켜지는지를 "
       "중심으로 비평하였다. 작가가 시점을 바꾼 것은 독자를 방관자로 두지 않겠다는 "
       "의도라고 생각한다.")

BORROWING = ("가상 활동에서 국가 폭력 앞에서 개인의 존엄이 어떻게 지켜지는지를 중심으로 "
             "비평문을 작성함. 독자를 방관자로 두지 않겠다는 의도를 읽어냄.")
DIGESTED = ("가상 활동에서 국가 권력과 인간 존엄의 관계를 중심 질문으로 세워 비평문을 "
            "작성함. 서술 시점의 선택을 작가의 전략으로 해석하는 안목을 보임.")


def _draft(token, text, exempt=False):
    return {"classes": [{"name": "1반", "students": [
        {"토큰": token, "핵심소재": "", "톤등급": "중", "세특": text,
         "비고": "", "예외": exempt}]}]}


def _codes(report):
    return [c for row in report["rows"] for _, c, _ in row["issues"]]


# ── borrow_stats 자체 ───────────────────────────────────────
def test_borrowing_text_measures_high():
    cov, run = V.borrow_stats(BORROWING, SRC)
    assert cov >= V.BORROW_COV
    assert run >= V.BORROW_RUN


def test_digested_text_measures_low():
    cov, run = V.borrow_stats(DIGESTED, SRC)
    assert cov < V.BORROW_COV
    assert run < V.BORROW_RUN


def test_quoted_span_is_exempt():
    # 작품명·핵심 개념어의 작은따옴표 인용은 차용으로 세지 않는다
    quoted = "가상 활동에서 '국가 폭력 앞에서 개인의 존엄이 어떻게 지켜지는지'를 탐구함."
    bare = "가상 활동에서 국가 폭력 앞에서 개인의 존엄이 어떻게 지켜지는지를 탐구함."
    cov_q, _ = V.borrow_stats(quoted, SRC)
    cov_b, _ = V.borrow_stats(bare, SRC)
    assert cov_q < cov_b


def test_empty_source_is_zero():
    assert V.borrow_stats(BORROWING, "") == (0.0, 0)


# ── 토큰 단계 편입 ──────────────────────────────────────────
def test_borrowing_student_gets_warn():
    report = V.verify_token_drafts(_draft("S-AB12", BORROWING), PROFILE,
                                   sources={"S-AB12": SRC})
    assert "BORROWED" in _codes(report)
    assert report["fail"] == 0  # WARN이지 FAIL이 아니다 — 평가자 주권


def test_digested_student_passes():
    report = V.verify_token_drafts(_draft("S-AB12", DIGESTED), PROFILE,
                                   sources={"S-AB12": SRC})
    assert "BORROWED" not in _codes(report)


def test_no_sources_skips_check():
    report = V.verify_token_drafts(_draft("S-AB12", BORROWING), PROFILE)
    assert "BORROWED" not in _codes(report)


def test_exempt_student_skips_check():
    report = V.verify_token_drafts(_draft("S-AB12", BORROWING, exempt=True), PROFILE,
                                   sources={"S-AB12": SRC})
    assert "BORROWED" not in _codes(report)


def test_student_without_source_skips_check():
    report = V.verify_token_drafts(_draft("S-AB12", BORROWING), PROFILE,
                                   sources={"S-CD34": SRC})
    assert "BORROWED" not in _codes(report)


def test_invalid_token_skips_borrow_check():
    # 선검증 위반 학생은 차용 검사 대상이 아니다(TOKEN_INVALID가 우선)
    report = V.verify_token_drafts(_draft("30101", BORROWING), PROFILE,
                                   sources={"30101": SRC})
    codes = _codes(report)
    assert "TOKEN_INVALID" in codes
    assert "BORROWED" not in codes
