#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""가명처리 파이프라인 — 명렬 인식, 토큰 발급·치환, 재결합, 유출 검사.

식별정보(실명·학번)는 이 로컬 모듈과 매핑표에만 존재한다. LLM에는 토큰만 노출된다.
매칭 키는 이름이 아니라 학번이다(동명이인 원천 차단).
"""
from __future__ import annotations

import json
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
    # utf-8-sig: 메모장·PowerShell 5.1 -Encoding utf8 기본값은 UTF-8 BOM을 붙인다.
    # BOM이 있으면 제거하고, 없으면 그대로 읽으므로 항상 안전하다.
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
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
        if not name or name not in out:
            continue
        token = mapping.get("map", {}).get(sid)
        # 이름은 경계 없이 무조건 치환 (과소탐 방지 — 개인정보 누락이 최악)
        # 한글은 조사로 어절 경계가 흐려지므로 경계 검사를 하면 안 됨
        # 과탐 가능성(긴 단어 내 포함)은 경고로 교사에게 보고
        if token:
            out, count = re.subn(re.escape(name), token, out)
            if count > 0:
                warnings.append(f"본문에서 이름 '{name}'을 토큰으로 치환함(학번 {sid}, {count}회)")
        else:
            # 토큰이 없는 명렬 이름 = 미제출자. 제출자 본문에 미제출 급우 이름이
            # 나오면 실명이 그대로 전송되므로 중립 대체어로 치환한다.
            out, count = re.subn(re.escape(name), "급우", out)
            if count > 0:
                warnings.append(f"본문에서 미제출자 이름 '{name}'을 급우로 치환함")
    return out, warnings


def reidentify(text: str, mapping: dict) -> str:
    """토큰을 학번으로 되돌린다(로컬 재결합).

    LLM이 토큰 코어를 소문자로 출력할 수 있으므로 대소문자를 무시하고 치환한다.
    """
    out = text
    for sid, token in mapping.get("map", {}).items():
        # 토큰도 앞뒤가 숫자가 아닐 때만 치환 (경계 보호)
        out = re.sub(rf"(?<!\d){re.escape(token)}(?!\d)", sid, out, flags=re.IGNORECASE)
    return out


TOKEN_PATTERN = re.compile(r"(?<![0-9A-Za-z])S-[0-9A-Fa-f]{4}(?![0-9A-Fa-f])")


def scan_leak(text: str, roster: dict, scope: str = "구조"):
    """LLM 전송 전후 텍스트에서 식별정보를 찾는다.

    학번은 어디서 발견되든 FAIL(오탐이 없는 강한 신호).
    이름은 구조 필드에서만 FAIL이고 본문에서는 WARN이다 — 일반명사와 겹치는
    이름('봄' 등)은 원리적으로 100% 탐지가 불가능하므로 게이트로 삼지 않는다.
    """
    issues: list[tuple[str, str, str]] = []
    for sid in {str(s.get("학번", "")) for s in roster.get("students", [])}:
        # 학번은 숫자 경계로 검사한다 — pseudonymize_text가 일부러 보존하는
        # "101010번" 같은 무관한 숫자열 안의 부분 문자열을 오탐하면 교착이 생긴다.
        if sid and re.search(rf"(?<!\d){re.escape(sid)}(?!\d)", text):
            issues.append(("FAIL", "ID_LEAK", f"학번 {sid} 노출"))
    level = "FAIL" if scope == "구조" else "WARN"
    for name in {s.get("이름", "") for s in roster.get("students", [])}:
        if name and name in text:
            issues.append((level, "NAME_LEAK", f"이름 '{name}' 노출({scope})"))
    return issues


def scan_token_residue(text: str) -> list[str]:
    """최종 산출물에 남은 토큰을 찾는다(재결합 누락 감지)."""
    return TOKEN_PATTERN.findall(text)


def scan_id_in_narrative(text: str, roster: dict) -> list[str]:
    """최종 서술문에 학번이 그대로 남아 있는지 찾는다.

    재결합은 토큰을 학번으로 되돌리므로, 본문 이름 자리에 있던 토큰이
    학번 숫자로 복원되어 문장에 남을 수 있다. 토큰 잔존 검사로는 잡히지
    않으므로(S-XXXX가 이미 사라진 상태) 별도로 검사한다.
    """
    found: list[str] = []
    for student in roster.get("students", []):
        sid = str(student.get("학번", ""))
        if sid and re.search(rf"(?<!\d){re.escape(sid)}(?!\d)", text):
            found.append(sid)
    return found


MEMO_HEADER_ALIASES = {"관찰메모", "메모", "특기사항"}


def _normalize_header(cell) -> str:
    """헤더 셀 비교용 정규화 — 공백을 무시한다('관찰 메모' == '관찰메모')."""
    return re.sub(r"\s+", "", cell or "")


def _find_memo_header_indices(rows):
    """헤더 행에서 (학번열, 메모열, 헤더행번호)를 찾는다. 없으면 (None, None, -1)."""
    for i, row in enumerate(rows):
        id_idx = next((j for j, c in enumerate(row) if c in ("학번", "번호")), None)
        memo_idx = next(
            (j for j, c in enumerate(row) if _normalize_header(c) in MEMO_HEADER_ALIASES), None
        )
        if id_idx is not None and memo_idx is not None:
            return (id_idx, memo_idx, i)
    return (None, None, -1)


def parse_memo_xlsx(path):
    """관찰 메모 xlsx에서 (학번, 메모) 쌍을 추출한다.

    메모 열 헤더('관찰 메모'/'관찰메모'/'메모'/'특기사항' 중 하나, 공백 무시)를
    찾지 못하면 None을 반환한다(호출부가 exit 1 + 안내로 처리).
    """
    rows = _rows_from_xlsx(path)
    id_idx, memo_idx, header_row_idx = _find_memo_header_indices(rows)
    if id_idx is None or memo_idx is None:
        return None

    pairs = []
    for i, row in enumerate(rows):
        if i == header_row_idx:
            continue
        if id_idx >= len(row) or memo_idx >= len(row):
            continue
        sid = row[id_idx]
        memo = row[memo_idx]
        if not sid or not STUDENT_ID.fullmatch(sid):
            continue
        if not memo:
            continue
        pairs.append((sid, memo))
    return pairs


_MEMO_LINE = re.compile(r"^(\d+)\s*[:]?\s*(.*)$")


def parse_memo_text(path):
    """`학번: 메모` 또는 `학번 메모` 형식의 텍스트에서 (학번, 메모) 쌍을 추출한다."""
    # utf-8-sig: BOM 붙은 파일(메모장·PowerShell 기본 저장)도 조용히 실패하지 않게 한다.
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    pairs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _MEMO_LINE.match(line)
        if not m:
            continue
        sid, memo = m.group(1), m.group(2).strip()
        if not memo:
            continue
        pairs.append((sid, memo))
    return pairs


def _xlsx_is_empty(path) -> bool:
    """워크북에 실제 내용(비공백 셀)이 하나도 없는지 확인한다."""
    rows = _rows_from_xlsx(path)
    return not any(any(c.strip() for c in row) for row in rows)


MAPPING_GLOB = "매핑*.json"


def save_mapping(mapping: dict, path) -> None:
    """매핑표를 로컬에 저장한다. 이 파일은 가명처리의 '추가 정보'이므로 로컬 전용이다."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)


def load_mapping(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def destroy_mapping(path) -> bool:
    """지정 경로의 매핑표를 파기한다. 파기 = 파일 부존재 확인 수준."""
    path = Path(path)
    if path.exists():
        path.unlink()
        return True
    return False


def detect_stale_mapping(dir_path) -> list:
    """이전 실행이 비정상 종료돼 남은 매핑표를 찾는다(실행 전 점검용)."""
    return sorted(Path(dir_path).glob(MAPPING_GLOB))


# ---------------------------------------------------------------------------
# CLI — 명렬(실명·학번)이 LLM 컨텍스트로 들어가지 않도록, 에이전트는 이 CLI를
# subprocess로 실행하고 stdout의 요약(인원수·건수)만 읽는다.
# stdout/stderr에는 이름·학번을 절대 출력하지 않는다 — 이 계약이 기능의 전부다.
# ---------------------------------------------------------------------------

def _read_json(path):
    # utf-8-sig: 교사가 명렬.json/활동프로파일.json 등을 메모장에서 열어 다시
    # 저장하면 BOM이 붙는다 — 붙어 있으면 제거하고, 없으면 그대로 읽는다.
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(obj, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def _cmd_roster(args) -> int:
    roster = detect_roster(args.input)
    n = len(roster.get("students", []))
    if n == 0:
        print("명렬 인식: 0명. 학번·이름 두 열이 있는 표(엑셀) 또는 '학번 이름' 형식의 "
              "텍스트로 다시 붙여넣어 주세요.")
        return 1
    _write_json(roster, args.out)
    print(f"명렬 인식: {n}명 (방식: {roster.get('방식', '?')}). 이름은 출력하지 않습니다.")
    if roster.get("확인필요"):
        print("확인필요: 표 헤더를 찾지 못해 패턴으로 추정한 결과입니다. 원본 표를 확인해 주세요.")
    return 0


def _load_submitted_ids(args) -> list[str]:
    if args.submitted:
        return [s.strip() for s in args.submitted.split(",") if s.strip()]
    with open(args.submitted_from, encoding="utf-8-sig") as f:
        return [line.strip() for line in f if line.strip()]


def _cmd_issue(args) -> int:
    roster = _read_json(args.roster)
    submitted_ids = _load_submitted_ids(args)
    existing = None
    if Path(args.out).exists():
        existing = _read_json(args.out)
    mapping = issue_tokens(roster, submitted_ids, existing=existing)
    _write_json(mapping, args.out)
    total = len(roster.get("students", []))
    issued = len(mapping.get("map", {}))
    not_issued = max(total - issued, 0)
    print(f"토큰 발급: 제출자 {issued}명, 미발급(미제출) {not_issued}명.")
    return 0


def _cmd_mask(args) -> int:
    data = _read_json(args.input)
    roster = _read_json(args.roster)
    mapping = _read_json(args.mapping)

    out_items = []
    total_warnings = 0
    for item in data.get("items", []):
        sid = str(item.get("학번", ""))
        token = mapping.get("map", {}).get(sid)
        if token is None:
            print("가명화 중단: 입력 항목에 매핑(토큰)이 없는 학번이 있습니다. "
                  "issue 명령을 먼저 실행해 토큰을 발급하세요.")
            return 1
        text, warnings = pseudonymize_text(item.get("본문", ""), roster, mapping)
        total_warnings += len(warnings)
        out_items.append({"토큰": token, "본문": text})

    leak_count = 0
    for item in out_items:
        issues = scan_leak(item["본문"], roster, scope="본문")
        leak_count += sum(1 for level, code, _ in issues if level == "FAIL" and code == "ID_LEAK")

    if leak_count > 0:
        print(f"가명화 중단: 학번 유출 {leak_count}건이 발견되어 저장하지 않았습니다.")
        return 1

    _write_json({"items": out_items}, args.out)
    print(f"가명화: {len(out_items)}건 처리, 본문 이름 치환 경고 {total_warnings}건, 학번 유출 0건.")
    return 0


def _cmd_memo(args) -> int:
    """교사 관찰 메모(파일)를 토큰화한다.

    대화창에 실명·학번을 입력하는 채널을 원천 차단하기 위한 명령이다 — 메모는
    반드시 파일(채점표의 메모 열 또는 별도 텍스트)로 받고, 여기서 토큰화한 뒤에만
    에이전트에게 결과 파일을 넘긴다.
    """
    roster = _read_json(args.roster)
    mapping = _read_json(args.mapping)

    input_path = Path(args.input)
    suffix = input_path.suffix.lower()
    if suffix == ".xlsx":
        if _xlsx_is_empty(input_path):
            print("메모 파일이 비어 있습니다.")
            return 1
        pairs = parse_memo_xlsx(input_path)
        if pairs is None:
            print("메모 열 헤더를 '관찰 메모'로 지정해 주세요")
            return 1
    elif suffix in (".txt", ".md"):
        # utf-8-sig로 먼저 읽어 BOM 유무와 무관하게 "완전히 비었는지"를 정확히 판정한다.
        raw = input_path.read_text(encoding="utf-8-sig", errors="replace")
        if not raw.strip():
            print("메모 파일이 비어 있습니다.")
            return 1
        pairs = parse_memo_text(input_path)
    else:
        print("지원하지 않는 입력 형식입니다. xlsx 또는 txt/md 파일을 사용해 주세요.")
        return 1

    if not pairs:
        print(
            "메모를 한 건도 읽지 못했습니다. 텍스트 파일은 '학번: 메모' 형식인지, "
            "엑셀은 메모 열 헤더가 '관찰 메모'인지 확인해 주세요."
        )
        return 1

    out_items = []
    excluded = 0
    total_warnings = 0
    for sid, memo in pairs:
        token = mapping.get("map", {}).get(str(sid))
        if token is None:
            excluded += 1
            continue
        text, warnings = pseudonymize_text(memo, roster, mapping)
        total_warnings += len(warnings)
        out_items.append({"토큰": token, "메모": text})

    leak_count = 0
    for item in out_items:
        issues = scan_leak(item["메모"], roster, scope="본문")
        leak_count += sum(1 for level, code, _ in issues if level == "FAIL" and code == "ID_LEAK")

    if leak_count > 0:
        print(f"관찰 메모 중단: 학번 유출 {leak_count}건이 발견되어 저장하지 않았습니다.")
        return 1

    _write_json({"items": out_items}, args.out)

    if not out_items:
        # 후보는 있었으나 전부 매핑에 없는 학번(=미제출자)이라 제외된 경우.
        # 형식 오류로 인한 0건과 구분되도록 경고를 명확히 한다.
        print(f"수집 0건 — 읽은 메모 {excluded}건이 모두 매핑에 없는 학번입니다(미제출자 확인 필요).")
        return 0

    print(
        f"관찰 메모: {len(out_items)}건 수집({excluded}건은 매핑 없음으로 제외). "
        f"본문 이름 치환 경고 {total_warnings}건, 학번 유출 0건."
    )
    return 0


def _cmd_finalize(args) -> int:
    draft = _read_json(args.input)
    roster = _read_json(args.roster)
    mapping = _read_json(args.mapping)

    token_to_sid = {t: s for s, t in mapping.get("map", {}).items()}
    sid_to_name = {str(s.get("학번", "")): s.get("이름", "") for s in roster.get("students", [])}

    new_classes = []
    restored = 0
    for cls in draft.get("classes", []):
        new_students = []
        for student in cls.get("students", []):
            token = student.get("토큰")
            sid = token_to_sid.get(token)
            if sid is None:
                print("재결합 실패: 매핑에 없는 토큰이 있어 1:1 복원을 완료할 수 없습니다.")
                return 1
            new_student = {"학번": sid, "이름": sid_to_name.get(sid, "")}
            for key, value in student.items():
                if key == "토큰":
                    continue
                if isinstance(value, str):
                    value = reidentify(value, mapping)
                new_student[key] = value
            new_students.append(new_student)
            restored += 1
        new_classes.append({"name": cls.get("name", ""), "students": new_students})

    _write_json({"classes": new_classes}, args.out)
    print(f"재결합: {restored}명 복원 완료.")
    return 0


def main(argv=None) -> int:
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="가명처리 CLI — 명렬(실명·학번)을 로컬에서만 다루고, "
                    "에이전트는 stdout 요약(인원수·건수)만 읽는다."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_roster = sub.add_parser("roster", help="명렬 감지")
    p_roster.add_argument("input", help="명단 원본 파일(xlsx 또는 텍스트)")
    p_roster.add_argument("--out", required=True, help="명렬.json 저장 경로")
    p_roster.set_defaults(func=_cmd_roster)

    p_issue = sub.add_parser("issue", help="제출자 토큰 발급")
    p_issue.add_argument("--roster", required=True, help="명렬.json 경로")
    group = p_issue.add_mutually_exclusive_group(required=True)
    group.add_argument("--submitted", help="쉼표로 구분한 제출자 학번 목록")
    group.add_argument("--submitted-from", help="제출자 학번이 한 줄에 하나씩 있는 텍스트 파일")
    p_issue.add_argument("--out", required=True, help="매핑.json 저장 경로(기존 파일이 있으면 재사용·추가 발급)")
    p_issue.set_defaults(func=_cmd_issue)

    p_mask = sub.add_parser("mask", help="본문·학번 가명화")
    p_mask.add_argument("input", help='입력 JSON({"items":[{"학번","본문"}]})')
    p_mask.add_argument("--roster", required=True, help="명렬.json 경로")
    p_mask.add_argument("--mapping", required=True, help="매핑.json 경로")
    p_mask.add_argument("--out", required=True, help="토큰본.json 저장 경로")
    p_mask.set_defaults(func=_cmd_mask)

    p_memo = sub.add_parser("memo", help="교사 관찰 메모 토큰화(파일 입력 전용)")
    p_memo.add_argument("input", help="관찰 메모 원본 파일(xlsx 또는 txt/md)")
    p_memo.add_argument("--roster", required=True, help="명렬.json 경로")
    p_memo.add_argument("--mapping", required=True, help="매핑.json 경로")
    p_memo.add_argument("--out", required=True, help="관찰메모.json 저장 경로")
    p_memo.set_defaults(func=_cmd_memo)

    p_finalize = sub.add_parser("finalize", help="토큰 → 실명 재결합")
    p_finalize.add_argument("input", help='토큰 초안 JSON({"classes":[{"name","students":[{"토큰",...}]}]})')
    p_finalize.add_argument("--roster", required=True, help="명렬.json 경로")
    p_finalize.add_argument("--mapping", required=True, help="매핑.json 경로")
    p_finalize.add_argument("--out", required=True, help="실명초안.json 저장 경로")
    p_finalize.set_defaults(func=_cmd_finalize)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
