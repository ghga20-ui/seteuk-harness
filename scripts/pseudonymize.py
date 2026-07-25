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


def _find_header_indices(rows):
    """헤더 행을 찾아 (id_idx, name_idx, 헤더행번호)를 반환. 없으면 (None, None, -1)."""
    for i, row in enumerate(rows):
        id_idx = next((j for j, c in enumerate(row) if c in ("학번", "번호")), None)
        name_idx = next((j for j, c in enumerate(row) if c == "이름"), None)
        if id_idx is not None and name_idx is not None:
            return (id_idx, name_idx, i)
    return (None, None, -1)


def _pairs_from_rows_with_indices(rows, id_idx, name_idx, header_row_idx):
    """헤더 행의 열 인덱스를 사용해 (학번, 이름) 쌍을 추출."""
    pairs, seen = [], set()
    for i, row in enumerate(rows):
        if i == header_row_idx:  # 헤더 행 자체는 데이터에서 제외
            continue
        # 인덱스 범위 확인
        if id_idx >= len(row) or name_idx >= len(row):
            continue
        sid = row[id_idx]
        name = row[name_idx]
        # 학번이 5자리 숫자, 이름이 한글 2~4자 확인
        if (
            sid
            and STUDENT_ID.fullmatch(sid)
            and name
            and KOREAN_NAME.fullmatch(name)
            and sid not in seen
        ):
            seen.add(sid)
            pairs.append({"학번": sid, "이름": name})
    return pairs


def _pairs_from_rows_pattern(rows):
    """행 목록에서 (학번, 이름) 쌍을 뽑는다(패턴 기반, 낮은 신뢰도). 긴 본문 셀은 이름 후보에서 제외."""
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

    id_idx, name_idx, header_row_idx = _find_header_indices(rows)

    if id_idx is not None and name_idx is not None:
        # 헤더 기반 추출
        students = _pairs_from_rows_with_indices(rows, id_idx, name_idx, header_row_idx)
        if not students:
            방식 = "실패"
        else:
            방식 = "표헤더"
        return {"students": students, "출처": str(path), "방식": 방식, "확인필요": False}
    else:
        # 헤더가 없으므로 패턴 기반 추출 (낮은 신뢰도)
        students = _pairs_from_rows_pattern(rows)
        if not students:
            방식 = "실패"
        else:
            방식 = "패턴"
        return {"students": students, "출처": str(path), "방식": 방식, "확인필요": True}
