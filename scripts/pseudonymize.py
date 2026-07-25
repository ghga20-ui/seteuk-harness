#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""가명처리 파이프라인 — 명렬 인식, 토큰 발급·치환, 재결합, 유출 검사.

식별정보(실명·학번)는 이 로컬 모듈과 매핑표에만 존재한다. LLM에는 토큰만 노출된다.
매칭 키는 이름이 아니라 학번이다(동명이인 원천 차단).
"""
from __future__ import annotations

import re
import secrets
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


def issue_tokens(roster: dict, submitted_ids, existing: dict | None = None) -> dict:
    """제출자에게만 무작위 토큰을 발급한다. 순번이 아닌 난수여야 역추적이 어렵다."""
    mapping = {"활동": (existing or {}).get("활동"), "map": dict((existing or {}).get("map", {}))}
    submitted = {str(s) for s in submitted_ids}
    used = set(mapping["map"].values())
    for student in roster.get("students", []):
        sid = str(student.get("학번", ""))
        if sid not in submitted or sid in mapping["map"]:
            continue
        while True:
            token = "S-" + secrets.token_hex(2).upper()
            if token not in used:
                break
        used.add(token)
        mapping["map"][sid] = token
    return mapping


def pseudonymize_text(text: str, roster: dict, mapping: dict):
    """학번과 명렬 이름을 토큰으로 치환한다. 본문 이름 치환은 경고로 보고한다."""
    warnings: list[str] = []
    out = text
    for sid, token in mapping.get("map", {}).items():
        # 학번은 앞뒤가 숫자가 아닐 때만 치환 (경계 보호)
        out = re.sub(rf"(?<!\d){re.escape(sid)}(?!\d)", token, out)
    for student in roster.get("students", []):
        name = student.get("이름", "")
        sid = str(student.get("학번", ""))
        token = mapping.get("map", {}).get(sid)
        if not name or not token or name not in out:
            continue
        # 이름은 경계 없이 무조건 치환 (과소탐 방지 — 개인정보 누락이 최악)
        # 한글은 조사로 어절 경계가 흐려지므로 경계 검사를 하면 안 됨
        # 과탐 가능성(긴 단어 내 포함)은 경고로 교사에게 보고
        out, count = re.subn(re.escape(name), token, out)
        if count > 0:
            warnings.append(f"본문에서 이름 '{name}'을 토큰으로 치환함(학번 {sid}, {count}회)")
    return out, warnings


def reidentify(text: str, mapping: dict) -> str:
    """토큰을 학번으로 되돌린다(로컬 재결합)."""
    out = text
    for sid, token in mapping.get("map", {}).items():
        # 토큰도 앞뒤가 숫자가 아닐 때만 치환 (경계 보호)
        out = re.sub(rf"(?<!\d){re.escape(token)}(?!\d)", sid, out)
    return out
