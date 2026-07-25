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
