#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""가명처리 파이프라인 — 명렬 인식, 토큰 발급·치환, 재결합, 유출 검사.

식별정보(실명·학번)는 이 로컬 모듈과 매핑표에만 존재한다. LLM에는 토큰만 노출된다.
매칭 키는 이름이 아니라 학번이다(동명이인 원천 차단).
"""
from __future__ import annotations

import re
from pathlib import Path

STUDENT_ID = re.compile(r"\b\d{5}\b")
KOREAN_NAME = re.compile(r"^[가-힣]{2,4}$")


def _rows_from_xlsx(path):
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if c is None else str(c).strip() for c in row])
    wb.close()
    return rows


def _rows_from_text(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return [line.split() for line in text.splitlines() if line.strip()]


def _pairs_from_rows(rows):
    """행 목록에서 (학번, 이름) 쌍을 뽑는다. 긴 본문 셀은 이름 후보에서 제외된다."""
    pairs, seen = [], set()
    for row in rows:
        sid = next((c for c in row if STUDENT_ID.fullmatch(c or "")), None)
        if not sid or sid in seen:
            continue
        name = next((c for c in row if c and KOREAN_NAME.fullmatch(c)), None)
        if name:
            seen.add(sid)
            pairs.append({"학번": sid, "이름": name})
    return pairs


def detect_roster(path) -> dict:
    """명단 파일에서 학번·이름 쌍을 감지한다. LLM을 거치지 않는 로컬 판정."""
    path = Path(path)
    try:
        rows = _rows_from_xlsx(path) if path.suffix.lower() == ".xlsx" else _rows_from_text(path)
    except Exception:
        rows = []

    header_hit = any(
        any(c in ("학번", "번호") for c in row) and any(c == "이름" for c in row) for row in rows
    )
    students = _pairs_from_rows(rows)
    if not students:
        방식 = "실패"
    elif header_hit:
        방식 = "표헤더"
    else:
        방식 = "패턴"
    return {"students": students, "출처": str(path), "방식": 방식}
