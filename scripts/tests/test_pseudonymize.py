# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pseudonymize import detect_roster


def _make_xlsx(tmp_path, rows, headers=("학번", "이름")):
    from openpyxl import Workbook

    p = tmp_path / "명단.xlsx"
    wb = Workbook()
    ws = wb.active
    if headers:
        ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    wb.save(p)
    return p


def test_detect_roster_from_header_table(tmp_path):
    path = _make_xlsx(tmp_path, [("10101", "김가상"), ("10102", "이허구")])
    roster = detect_roster(path)
    assert roster["방식"] == "표헤더"
    assert {"학번": "10101", "이름": "김가상"} in roster["students"]
    assert len(roster["students"]) == 2


def test_detect_roster_without_header_uses_pattern(tmp_path):
    path = _make_xlsx(tmp_path, [("10101", "김가상"), ("10102", "이허구")], headers=None)
    roster = detect_roster(path)
    assert len(roster["students"]) == 2
    assert roster["방식"] in ("표헤더", "패턴")


def test_detect_roster_from_plain_text(tmp_path):
    p = tmp_path / "명단.txt"
    p.write_text("10101 김가상\n10102 이허구\n", encoding="utf-8")
    roster = detect_roster(p)
    assert len(roster["students"]) == 2
    assert roster["students"][0]["학번"] == "10101"


def test_detect_roster_ignores_long_body_column(tmp_path):
    """학생 원본(행마다 긴 본문)은 명렬이 아니다 — 본문 열은 이름으로 오인하지 않는다."""
    path = _make_xlsx(
        tmp_path,
        [("10101", "김가상", "가" * 300), ("10102", "이허구", "나" * 300)],
        headers=("학번", "이름", "본문"),
    )
    roster = detect_roster(path)
    assert len(roster["students"]) == 2
    for s in roster["students"]:
        assert len(s["이름"]) <= 4


def test_detect_roster_failure_reports_method(tmp_path):
    p = tmp_path / "빈파일.txt"
    p.write_text("아무 명단도 없는 문서입니다.\n", encoding="utf-8")
    roster = detect_roster(p)
    assert roster["방식"] == "실패"
    assert roster["students"] == []


def test_detect_roster_uses_header_column_for_name(tmp_path):
    """헤더가 있으면 이름은 '이름' 열에서만 가져온다(중간 열 오인 방지)."""
    path = _make_xlsx(
        tmp_path,
        [("10101", "결석", "김가상"), ("10102", "우수", "이허구")],
        headers=("학번", "비고", "이름"),
    )
    roster = detect_roster(path)
    names = {s["이름"] for s in roster["students"]}
    assert names == {"김가상", "이허구"}


def test_detect_roster_header_column_order_independent(tmp_path):
    """이름 열이 학번 열보다 앞에 있어도 정확히 집는다."""
    path = _make_xlsx(
        tmp_path,
        [("김가상", "10101"), ("이허구", "10102")],
        headers=("이름", "학번"),
    )
    roster = detect_roster(path)
    assert {s["학번"] for s in roster["students"]} == {"10101", "10102"}
    assert {s["이름"] for s in roster["students"]} == {"김가상", "이허구"}


def test_detect_roster_pattern_mode_flags_low_confidence(tmp_path):
    """헤더 없는 패턴 추정은 신뢰도 낮음으로 표시해 사용자 확인을 유도한다."""
    path = _make_xlsx(tmp_path, [("10101", "김가상"), ("10102", "이허구")], headers=None)
    roster = detect_roster(path)
    assert roster["방식"] == "패턴"
    assert roster.get("확인필요") is True


from pseudonymize import issue_tokens, pseudonymize_text, reidentify

ROSTER = {"students": [
    {"학번": "10101", "이름": "김가상"},
    {"학번": "10102", "이름": "이허구"},
    {"학번": "10103", "이름": "박미정"},
]}


def test_issue_tokens_skips_non_submitters():
    mapping = issue_tokens(ROSTER, submitted_ids=["10101", "10102"])
    assert set(mapping["map"]) == {"10101", "10102"}
    assert "10103" not in mapping["map"]


def test_issue_tokens_are_unique_and_not_sequential():
    mapping = issue_tokens(ROSTER, submitted_ids=["10101", "10102", "10103"])
    tokens = list(mapping["map"].values())
    assert len(set(tokens)) == 3
    assert tokens != sorted(tokens, key=lambda t: t)  # 순번 유추 방지: 학번 순 = 토큰 순이 아님
    for t in tokens:
        assert t.startswith("S-")


def test_issue_tokens_reuses_existing_and_adds_new():
    first = issue_tokens(ROSTER, submitted_ids=["10101"])
    second = issue_tokens(ROSTER, submitted_ids=["10101", "10102"], existing=first)
    assert second["map"]["10101"] == first["map"]["10101"]
    assert "10102" in second["map"]


def test_pseudonymize_replaces_ids_and_names():
    mapping = issue_tokens(ROSTER, submitted_ids=["10101", "10102"])
    text = "10101 김가상 학생은 이허구와 함께 발표함."
    out, warnings = pseudonymize_text(text, ROSTER, mapping)
    assert "10101" not in out
    assert "김가상" not in out
    assert "이허구" not in out
    assert mapping["map"]["10101"] in out
    assert warnings  # 본문 이름 치환 경고


def test_pseudonymize_leaves_unrelated_text_intact():
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])
    text = "봄이 오는 길목에서 희망을 노래함."
    out, _ = pseudonymize_text(text, ROSTER, mapping)
    assert out == text


def test_reidentify_restores_student_ids():
    mapping = issue_tokens(ROSTER, submitted_ids=["10101", "10102"])
    token = mapping["map"]["10102"]
    assert reidentify(f"{token} 학생의 세특", mapping) == "10102 학생의 세특"


def test_pseudonymize_does_not_corrupt_longer_number():
    """학번이 다른 숫자열의 일부일 때 그 숫자를 훼손하지 않는다."""
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])
    text = "101010번 사물함을 쓰는 10101 학생"
    out, _ = pseudonymize_text(text, ROSTER, mapping)
    assert "101010" in out
    assert mapping["map"]["10101"] in out
    assert " 10101 " not in out


def test_pseudonymize_roundtrip_preserves_unrelated_numbers():
    """치환 후 재결합하면 원문이 그대로 복원된다."""
    mapping = issue_tokens(ROSTER, submitted_ids=["10101", "10102"])
    text = "2026년 3월 15일, 101010번 자료를 읽고 10101 김가상이 발표함."
    out, _ = pseudonymize_text(text, ROSTER, mapping)
    restored = reidentify(out, mapping)
    assert "101010" in restored
    assert "10101" in restored
    assert "2026년 3월 15일" in restored
