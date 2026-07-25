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
