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


def test_detect_roster_from_plain_text_with_bom(tmp_path):
    """메모장·PowerShell 기본 저장(UTF-8 BOM)으로 만든 명단 텍스트도 조용히 실패하지
    않고 정상 인식되어야 한다."""
    p = tmp_path / "명단.txt"
    p.write_bytes("10101 김가상\n10102 이허구\n".encode("utf-8-sig"))
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


# ---------------------------------------------------------------------------
# 재현된 실제 버그: 헤더가 명시적으로 "이름"이라고 지목한 열조차 KOREAN_NAME
# 형식 검사({2,4}자 한글)를 통과해야 채택되어, 다문화·공백·영문·1자 이름을 가진
# 실재 학생이 명렬에서 조용히 누락되었다. 헤더가 있으면 그 열을 신뢰해야 한다.
# ---------------------------------------------------------------------------

def test_detect_roster_header_accepts_diverse_real_name_formats(tmp_path):
    """실제 존재하는 학생 이름 형식(다문화 성명·공백·영문·1자)이 헤더 열 신뢰로
    모두 인식되어야 한다 — 이름 형식 검사를 헤더 경로에 적용하면 안 된다."""
    path = _make_xlsx(
        tmp_path,
        [
            ("10101", "응우옌티탄흐엉"),  # 7자 다문화 성명
            ("10102", "박 서준"),  # 공백 포함
            ("10103", "Nguyen"),  # 영문
            ("10104", "봄"),  # 1자
        ],
    )
    roster = detect_roster(path)
    names = {s["이름"] for s in roster["students"]}
    assert names == {"응우옌티탄흐엉", "박 서준", "Nguyen", "봄"}
    assert len(roster["students"]) == 4


def test_detect_roster_header_skips_rows_missing_name_and_counts(tmp_path):
    """헤더 경로에서 이름 열이 비어 있는 데이터 행은 건너뛰고 '건너뜀' 카운트가 증가한다."""
    path = _make_xlsx(
        tmp_path,
        [("10101", "김가상"), ("10102", ""), ("10103", "이허구")],
    )
    roster = detect_roster(path)
    assert len(roster["students"]) == 2
    assert roster["건너뜀"] == 1


def test_detect_roster_header_skips_rows_missing_id_and_counts(tmp_path):
    """학번 열이 비어 있는 데이터 행도 마찬가지로 건너뛰고 집계된다."""
    path = _make_xlsx(
        tmp_path,
        [("10101", "김가상"), ("", "이허구"), ("10103", "박미정")],
    )
    roster = detect_roster(path)
    assert len(roster["students"]) == 2
    assert roster["건너뜀"] == 1


def test_detect_roster_header_no_skip_when_clean(tmp_path):
    """건너뛴 행이 없으면 '건너뜀'은 0이어야 한다(키 자체는 항상 존재)."""
    path = _make_xlsx(tmp_path, [("10101", "김가상"), ("10102", "이허구")])
    roster = detect_roster(path)
    assert roster["건너뜀"] == 0


def test_detect_roster_pattern_mode_recognizes_long_korean_names(tmp_path):
    """패턴 경로(헤더 없음)에서도 5~8자 한글 이름(다문화 성명)을 인식한다."""
    path = _make_xlsx(tmp_path, [("10101", "응우옌티탄흐엉")], headers=None)
    roster = detect_roster(path)
    assert len(roster["students"]) == 1
    assert roster["students"][0]["이름"] == "응우옌티탄흐엉"


# ---------------------------------------------------------------------------
# 성 열 + 이름 열 결합 — 명렬에 성 열과 이름 열이 분리되어 있으면(흔한 명렬 형식)
# 1자 이름('봄')으로 조용히 오인되지 않도록 성+이름을 합쳐 전체 이름으로 쓴다.
# ---------------------------------------------------------------------------

def test_detect_roster_combines_surname_and_given_name_columns(tmp_path):
    """성='김', 이름='봄'인 명렬은 '김봄'으로 결합되고 결합 플래그가 남아야 한다."""
    path = _make_xlsx(
        tmp_path,
        [("10104", "김", "봄")],
        headers=("학번", "성", "이름"),
    )
    roster = detect_roster(path)
    assert roster["students"] == [{"학번": "10104", "이름": "김봄"}]
    assert roster.get("성이름결합") is True


def test_detect_roster_combines_surname_alias_seongssi(tmp_path):
    """'성씨' 표기도 성 열로 인식해 결합한다."""
    path = _make_xlsx(
        tmp_path,
        [("10104", "김", "봄")],
        headers=("학번", "성씨", "이름"),
    )
    roster = detect_roster(path)
    assert roster["students"] == [{"학번": "10104", "이름": "김봄"}]
    assert roster.get("성이름결합") is True


def test_detect_roster_no_surname_column_no_combine_flag(tmp_path):
    """성 열이 없는 명렬은 결합 플래그가 없어야 한다(기존 동작 보존)."""
    path = _make_xlsx(tmp_path, [("10101", "김가상")])
    roster = detect_roster(path)
    assert not roster.get("성이름결합")


# ---------------------------------------------------------------------------
# 상태 표기 행 제외 (FIX 3) — 실제 채점표에서 학번은 살아 있는데 이름 칸에
# '자퇴' 같은 상태 문구가 적힌 행을 학생으로 잘못 인식해 48명이 49명으로
# 집계된 버그가 있었다. 이런 행은 명렬에서 제외되고 건너뜀에 반영되어야 한다.
# ---------------------------------------------------------------------------

def test_detect_roster_excludes_status_word_row(tmp_path):
    """이름 칸이 '자퇴'인 행은 학생으로 잡지 않고 건너뜀에 반영한다."""
    path = _make_xlsx(
        tmp_path,
        [("10101", "김가상"), ("10102", "이허구"), ("10114", "자퇴")],
    )
    roster = detect_roster(path)
    assert len(roster["students"]) == 2
    assert {s["학번"] for s in roster["students"]} == {"10101", "10102"}
    assert roster["건너뜀"] == 1
    assert roster.get("상태표기건너뜀") == 1


def test_detect_roster_status_word_ignores_surrounding_whitespace(tmp_path):
    """상태 표기어 비교는 공백을 제거한 뒤 완전 일치로 판정한다."""
    path = _make_xlsx(tmp_path, [("10101", "김가상"), ("10102", " 자퇴 ")])
    roster = detect_roster(path)
    assert len(roster["students"]) == 1
    assert roster["건너뜀"] == 1
    assert roster.get("상태표기건너뜀") == 1


def test_detect_roster_no_status_words_zero_count(tmp_path):
    """상태 표기 행이 없으면 상태표기건너뜀은 0이어야 한다(키는 항상 존재)."""
    path = _make_xlsx(tmp_path, [("10101", "김가상"), ("10102", "이허구")])
    roster = detect_roster(path)
    assert roster.get("상태표기건너뜀") == 0


from pseudonymize import issue_tokens, pseudonymize_text, reidentify, SHORT_NAME_WARNING

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
    # 토큰 형식만 결정론적으로 검사한다(무작위성 자체는 secrets 모듈이 보장)
    import re as _re
    assert all(_re.fullmatch(r"S-[0-9A-F]{4}", t) for t in tokens)
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


def test_scan_token_residue_detects_lowercase_hex_token():
    """LLM이 토큰 코어를 소문자로 출력해도 잔존 게이트가 잡아야 한다(I3)."""
    assert scan_token_residue("S-3f7a 학생은 분석함.") == ["S-3f7a"]


def test_reidentify_restores_lowercase_hex_token():
    """소문자로 출력된 토큰도 재결합에서 학번으로 복원되어야 한다(I3)."""
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])
    token = mapping["map"]["10101"]
    lower_token = token[:2] + token[2:].lower()
    assert reidentify(f"{lower_token} 학생의 세특", mapping) == "10101 학생의 세특"


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


def test_pseudonymize_masks_name_glued_to_previous_word():
    """앞 단어에 붙은 이름도 반드시 치환된다(과소탐 방지 — 개인정보 누락이 최악).

    갱신 사유: owner_id 없이 호출하는 구버전 호환 경로는 이제 명렬 이름을
    "자기 토큰"이 아니라 항상 중립어 "급우"로 치환한다(남의 토큰이 본문에
    박히는 오귀속 경로를 없애는 정책 변경). 이 테스트는 원래 치환 자체가
    일어나는지를 검증하려는 목적이었으므로, 기대값을 토큰에서 "급우"로 갱신한다.
    """
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])
    out, warnings = pseudonymize_text("급우김가상은 발표를 잘했다.", ROSTER, mapping)
    assert "김가상" not in out
    assert "급우" in out
    assert warnings


def test_pseudonymize_over_redaction_is_reported_as_warning():
    """과탐이 발생하면 경고로 보고되어 교사가 인지할 수 있다."""
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])
    out, warnings = pseudonymize_text("김가상이해력이 뛰어나다.", ROSTER, mapping)
    assert "김가상" not in out
    assert warnings  # 치환 사실이 보고됨


def test_pseudonymize_replaces_non_submitter_name_with_neutral_word():
    """미제출자(토큰 없음)의 이름이 본문에 있으면 실명 그대로 전송되지 않고
    중립 대체어 '급우'로 치환되며 경고가 남아야 한다(I2)."""
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])  # 박미정(10103)은 미제출
    text = "박미정과 함께 토론한 내용을 반영함."
    out, warnings = pseudonymize_text(text, ROSTER, mapping)
    assert "박미정" not in out
    assert "급우" in out
    assert any("박미정" in w and "급우" in w for w in warnings)


# ---------------------------------------------------------------------------
# 재현된 실제 버그 #1(심각) — 동명이인일 때 본문의 자기 이름이 남의 토큰이 됨.
# 30105, 30110 두 명 모두 "이서준"인 골든 명렬 재현. owner_id를 넘기면 각자의
# 글에서 자기 이름은 반드시 자기 토큰이 되어야 하고, 절대 남의 토큰이 되면
# 안 된다(오귀속은 이 프로젝트가 정의한 최악의 실패).
# ---------------------------------------------------------------------------

DUP_NAME_ROSTER = {"students": [
    {"학번": "30105", "이름": "이서준"},
    {"학번": "30110", "이름": "이서준"},
]}


def test_pseudonymize_duplicate_names_each_get_own_token_via_owner_id():
    mapping = issue_tokens(DUP_NAME_ROSTER, submitted_ids=["30105", "30110"])
    token_a = mapping["map"]["30105"]
    token_b = mapping["map"]["30110"]

    out_a, _ = pseudonymize_text("이서준은 '나목'을 분석함.", DUP_NAME_ROSTER, mapping, owner_id="30105")
    out_b, _ = pseudonymize_text(
        "이서준. '아몬드(손원평)'를 선정했다", DUP_NAME_ROSTER, mapping, owner_id="30110"
    )

    assert token_a in out_a
    assert token_b not in out_a
    assert token_b in out_b
    assert token_a not in out_b


def test_pseudonymize_other_students_name_becomes_neutral_not_token():
    """본문에 등장한 남의 이름은 남의 토큰이 아니라 중립어 '급우'가 되어야 한다."""
    mapping = issue_tokens(ROSTER, submitted_ids=["10101", "10102"])
    text = "이허구와 토론한 내용을 정리함."  # 10101의 글에 10102(이허구)가 언급됨
    out, warnings = pseudonymize_text(text, ROSTER, mapping, owner_id="10101")
    assert "이허구" not in out
    assert mapping["map"]["10102"] not in out
    assert "급우" in out
    assert warnings


# ---------------------------------------------------------------------------
# 재현된 실제 버그 #2(품질 훼손) — 1자 이름('봄')이 작품명 '봄봄(김유정)'을 파괴함.
# 1자 이름은 본문 치환 대상에서 제외하고 경고로만 남긴다.
# ---------------------------------------------------------------------------

SHORT_NAME_ROSTER = {"students": [{"학번": "10104", "이름": "봄"}]}


def test_pseudonymize_single_char_name_excluded_from_replacement_and_warned():
    mapping = issue_tokens(SHORT_NAME_ROSTER, submitted_ids=["10104"])
    text = "봄이라는 계절을 다룬 시를 분석함."
    out, warnings = pseudonymize_text(text, SHORT_NAME_ROSTER, mapping)
    assert out == text  # 1자 이름은 치환되지 않는다
    assert any(w == SHORT_NAME_WARNING for w in warnings)  # 경고 카운트에는 잡힌다


def test_pseudonymize_single_char_name_preserves_unrelated_work_title():
    """1자 이름이 있어도 작품명 '봄봄(김유정)'은 온전히 보존되어야 한다(품질 회귀)."""
    mapping = issue_tokens(SHORT_NAME_ROSTER, submitted_ids=["10104"])
    text = "'봄봄(김유정)'을 선정하여 해학성을 분석함."
    out, _ = pseudonymize_text(text, SHORT_NAME_ROSTER, mapping)
    assert "봄봄(김유정)" in out


from pseudonymize import scan_leak, scan_token_residue, scan_id_in_narrative


def _codes(issues):
    return [(lv, code) for lv, code, _ in issues]


def test_scan_leak_flags_student_id_as_fail_everywhere():
    for scope in ("구조", "본문"):
        issues = scan_leak("10101 학생의 감상문", ROSTER, scope=scope)
        assert ("FAIL", "ID_LEAK") in _codes(issues)


def test_scan_leak_name_is_fail_in_structured_field():
    issues = scan_leak("김가상", ROSTER, scope="구조")
    assert ("FAIL", "NAME_LEAK") in _codes(issues)


def test_scan_leak_name_is_warn_in_body():
    issues = scan_leak("김가상과 함께 조사함.", ROSTER, scope="본문")
    assert ("WARN", "NAME_LEAK") in _codes(issues)
    assert not any(lv == "FAIL" for lv, _ in _codes(issues))


def test_scan_leak_clean_text_has_no_issues():
    assert scan_leak("봄을 노래한 시를 분석함.", ROSTER, scope="본문") == []


def test_scan_leak_does_not_deadlock_on_preserved_longer_number():
    """pseudonymize_text가 일부러 보존하는 '101010번' 안의 학번 부분 문자열은
    ID_LEAK로 잡히면 안 된다(I1 — 숫자 경계 없인 교착 발생)."""
    issues = scan_leak("101010번 자료를 읽음.", ROSTER, scope="본문")
    assert not any(code == "ID_LEAK" for _, code, _ in issues)


def test_scan_leak_flags_bare_id_with_digit_boundary():
    issues = scan_leak("10101 학생", ROSTER, scope="본문")
    assert any(code == "ID_LEAK" for _, code, _ in issues)


def test_scan_token_residue_detects_leftover_tokens():
    assert scan_token_residue("S-3F7A 학생은 분석함.") == ["S-3F7A"]
    assert scan_token_residue("학생은 분석함.") == []


def test_scan_token_residue_detects_token_glued_both_sides():
    """토큰이 한글에 앞뒤로 붙어 있어도 잔존을 탐지한다(개인정보 게이트는 대칭이어야 함)."""
    assert scan_token_residue("김S-3F7A 학생") == ["S-3F7A"]
    assert scan_token_residue("김S-3F7A의 갈등") == ["S-3F7A"]
    assert scan_token_residue("S-3F7A의 갈등") == ["S-3F7A"]


def test_scan_token_residue_does_not_match_longer_hex_run():
    """더 긴 16진 문자열의 일부는 토큰으로 오인하지 않는다."""
    assert scan_token_residue("S-3F7AB 코드") == []
    assert scan_token_residue("S-3F7A1 코드") == []


def test_scan_id_in_narrative_finds_bare_student_id():
    assert scan_id_in_narrative("10101은 감상문을 작성함.", ROSTER) == ["10101"]


def test_scan_id_in_narrative_ignores_unrelated_numbers():
    assert scan_id_in_narrative("101010번 자료를 읽고 2026년을 언급함.", ROSTER) == []


from pseudonymize import save_mapping, load_mapping, destroy_mapping, detect_stale_mapping


def test_save_and_load_mapping_roundtrip(tmp_path):
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])
    p = tmp_path / "매핑.json"
    save_mapping(mapping, p)
    assert load_mapping(p)["map"] == mapping["map"]


def test_destroy_mapping_removes_file(tmp_path):
    p = tmp_path / "매핑.json"
    save_mapping(issue_tokens(ROSTER, submitted_ids=["10101"]), p)
    assert destroy_mapping(p) is True
    assert not p.exists()
    assert destroy_mapping(p) is False


def test_detect_stale_mapping_finds_leftovers(tmp_path):
    save_mapping(issue_tokens(ROSTER, submitted_ids=["10101"]), tmp_path / "매핑.json")
    stale = detect_stale_mapping(tmp_path)
    assert len(stale) == 1
    assert stale[0].name == "매핑.json"


def test_detect_stale_mapping_empty_when_clean(tmp_path):
    assert detect_stale_mapping(tmp_path) == []


def test_load_mapping_handles_bom(tmp_path):
    """교사가 매핑.json을 메모장에서 열어 다시 저장해도(BOM 부여) 로드가 실패하면 안 된다."""
    import json

    p = tmp_path / "매핑.json"
    mapping = issue_tokens(ROSTER, submitted_ids=["10101"])
    p.write_bytes(json.dumps(mapping, ensure_ascii=False).encode("utf-8-sig"))
    loaded = load_mapping(p)
    assert loaded is not None
    assert loaded["map"] == mapping["map"]


def test_detect_stale_artifacts_finds_roster_memo_score_tokenbody(tmp_path):
    """적대적 감사 FINDING 3: 명렬·관찰메모·점수·토큰본도 잔존 감지 대상이어야 한다."""
    from pseudonymize import detect_stale_artifacts

    (tmp_path / "매핑.json").write_text("{}", encoding="utf-8")
    (tmp_path / "명렬.json").write_text("{}", encoding="utf-8")
    (tmp_path / "관찰메모.json").write_text("{}", encoding="utf-8")
    (tmp_path / "점수.json").write_text("{}", encoding="utf-8")
    (tmp_path / "토큰본.json").write_text("{}", encoding="utf-8")
    (tmp_path / "무관.json").write_text("{}", encoding="utf-8")

    found = {p.name for p in detect_stale_artifacts(tmp_path)}
    assert found == {"매핑.json", "명렬.json", "관찰메모.json", "점수.json", "토큰본.json"}


def test_detect_stale_mapping_alias_also_finds_roster():
    """하위 호환: detect_stale_mapping도 명렬 등 확장된 대상을 함께 찾아야 한다."""
    from pseudonymize import detect_stale_artifacts

    assert detect_stale_mapping is detect_stale_artifacts


# ---------------------------------------------------------------------------
# 골든리포트 §6 "false sense of safety" — 이름 표기 변형(공백·성 제외)을
# 탐지하지 못하면서 "경고 0건"으로 보고되어 안전하다고 오인되는 문제.
# FIX A: 공백 내성 치환(이름 글자 사이, 학번 숫자 사이 공백 허용, 숫자 경계 유지)
# FIX B: 성 제외 이름 치환("하윤이는"처럼 성을 빼고 부르는 경우, 3자 이상 이름만)
# ---------------------------------------------------------------------------

def test_pseudonymize_replaces_name_with_single_internal_space():
    roster = {"students": [{"학번": "30301", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30301"])
    token = mapping["map"]["30301"]
    out, warnings = pseudonymize_text("김 하윤 학생이 발표했다.", roster, mapping, owner_id="30301")
    assert token in out
    assert "김" not in out
    assert "하윤" not in out
    assert warnings


def test_pseudonymize_replaces_name_with_double_internal_space():
    roster = {"students": [{"학번": "30301", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30301"])
    token = mapping["map"]["30301"]
    out, _ = pseudonymize_text("김  하윤 학생이 발표했다.", roster, mapping, owner_id="30301")
    assert token in out
    assert "김" not in out


def test_pseudonymize_replaces_id_with_internal_space():
    roster = {"students": [{"학번": "30101", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30101"])
    token = mapping["map"]["30101"]
    out, _ = pseudonymize_text("301 01 학생의 발표", roster, mapping)
    assert token in out
    assert "301 01" not in out


def test_pseudonymize_spaced_id_pattern_does_not_corrupt_unrelated_numbers():
    """FIX A가 공백을 허용하더라도 숫자 경계는 유지되어 무관한 숫자열은 보존된다
    (기존 회귀: 101010, 2026년, 84일)."""
    roster = {"students": [{"학번": "30101", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30101"])
    text = "101010번 자료를 읽고 2026년 3월에 84일째 되는 날 썼다."
    out, _ = pseudonymize_text(text, roster, mapping)
    assert "101010" in out
    assert "2026년" in out
    assert "84일" in out


def test_pseudonymize_given_name_without_surname_gets_owner_token():
    """'하윤이는'처럼 인명 전용 접미(호칭 조사)가 붙어 성을 빼고 부르면
    3자 이상 이름의 나머지(2자 이상)도 치환 대상이 되어야 한다(FIX B).
    접미('이는')는 문장이 깨지지 않도록 치환 후에도 보존되어야 한다."""
    roster = {"students": [{"학번": "30201", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30201"])
    token = mapping["map"]["30201"]
    out, warnings = pseudonymize_text("하윤이는 최선을 다했다.", roster, mapping, owner_id="30201")
    assert token in out
    assert "하윤" not in out
    assert "이는" in out  # 접미 보존
    assert out == f"{token}이는 최선을 다했다."
    assert warnings


def test_pseudonymize_given_name_with_vocative_suffix_replaced():
    """'하윤아'(호격 조사)도 치환 대상이며 접미는 보존된다."""
    roster = {"students": [{"학번": "30201", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30201"])
    token = mapping["map"]["30201"]
    out, _ = pseudonymize_text("하윤아, 발표 준비를 정말 잘했더라.", roster, mapping, owner_id="30201")
    assert token in out
    assert "하윤" not in out
    assert out.startswith(f"{token}아")


def test_pseudonymize_given_name_with_subject_particle_suffix_replaced():
    """'하윤이가'(주격 조사)도 치환 대상이며 접미는 보존된다."""
    roster = {"students": [{"학번": "30201", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30201"])
    token = mapping["map"]["30201"]
    out, _ = pseudonymize_text("하윤이가 발표를 맡았다.", roster, mapping, owner_id="30201")
    assert token in out
    assert "하윤" not in out
    assert out.startswith(f"{token}이가")


def test_pseudonymize_given_name_bare_without_honorific_suffix_not_replaced():
    """실측(학생 답안 69,034자) 결과: 성 제외 이름이 맨몸으로 등장하면 시어·
    일반어와 충돌 위험이 실재한다(예: 성 제외 이름이 '하늘'인 경우 '하늘을
    우러러'). 인명 전용 접미가 없으면 건드리지 않는다 — 가상 인물로 재현."""
    roster = {"students": [{"학번": "30401", "이름": "김하늘"}]}
    mapping = issue_tokens(roster, submitted_ids=["30401"])
    text = "하늘을 우러러 한 점 부끄럼이 없기를 바라는 마음을 다뤘다."
    out, warnings = pseudonymize_text(text, roster, mapping, owner_id="30401")
    assert out == text
    assert not warnings


def test_pseudonymize_given_name_without_surname_becomes_neutral_for_non_owner():
    roster = {"students": [{"학번": "30201", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30201"])
    out, warnings = pseudonymize_text("하윤이는 최선을 다했다.", roster, mapping)  # owner_id 없음
    assert "급우" in out
    assert "하윤" not in out
    assert "이는" in out  # 접미 보존
    assert warnings


def test_pseudonymize_replaces_longest_name_first_no_orphan_surname_char():
    """치환 순서가 뒤집혀 성 제외 이름을 먼저 치환하면 '김'+토큰 형태의 잔재가
    남는다 — 반드시 전체 이름(김하윤)을 먼저 치환해야 한다."""
    roster = {"students": [{"학번": "30201", "이름": "김하윤"}]}
    mapping = issue_tokens(roster, submitted_ids=["30201"])
    token = mapping["map"]["30201"]
    out, _ = pseudonymize_text("김하윤은 시집을 분석했다.", roster, mapping, owner_id="30201")
    assert out.count(token) == 1
    assert "김" not in out
    assert "하윤" not in out


def test_pseudonymize_two_char_name_without_surname_not_added_as_target():
    """2자 이름('박봄')에서 성을 빼면 1자('봄')가 되므로 추가 치환 대상에
    넣지 않는다 — 기존 회귀(작품명 '봄봄(김유정)' 보존)와 동일한 원칙이다."""
    roster = {"students": [{"학번": "10105", "이름": "박봄"}]}
    mapping = issue_tokens(roster, submitted_ids=["10105"])
    text = "'봄봄(김유정)'을 선정하여 해학성을 분석했다."
    out, _ = pseudonymize_text(text, roster, mapping, owner_id="10105")
    assert "봄봄(김유정)" in out


DUP_GIVEN_NAME_ROSTER = {"students": [
    {"학번": "30105", "이름": "김하윤"},
    {"학번": "30110", "이름": "이하윤"},
]}


def test_pseudonymize_no_surname_duplicate_given_name_keeps_owner_classmate_split():
    """동명이인(성 제외 이름이 같은 '하윤')이어도 owner_id에 따라 각자 자기
    토큰만 받아야 한다(FIX B에도 오귀속 방지가 유지되어야 함)."""
    mapping = issue_tokens(DUP_GIVEN_NAME_ROSTER, submitted_ids=["30105", "30110"])
    token_a = mapping["map"]["30105"]
    token_b = mapping["map"]["30110"]

    out_a, _ = pseudonymize_text("하윤이는 성실하게 참여했다.", DUP_GIVEN_NAME_ROSTER, mapping, owner_id="30105")
    out_b, _ = pseudonymize_text("하윤이는 꾸준히 노력했다.", DUP_GIVEN_NAME_ROSTER, mapping, owner_id="30110")

    assert token_a in out_a
    assert token_b not in out_a
    assert token_b in out_b
    assert token_a not in out_b


# ---------------------------------------------------------------------------
# scan_leak: 공백 낀 학번은 FAIL, 성 제외 이름은 WARN(FAIL 아님) — FIX A/B
# ---------------------------------------------------------------------------

def test_scan_leak_flags_spaced_id_as_fail():
    roster = {"students": [{"학번": "30101", "이름": "김하윤"}]}
    issues = scan_leak("301 01 학생의 감상문", roster, scope="본문")
    assert ("FAIL", "ID_LEAK") in _codes(issues)


def test_scan_leak_given_name_with_honorific_suffix_is_warn_even_in_structured_scope():
    """인명 전용 접미(호칭 조사)가 붙은 성 제외 이름은 오탐 위험이 있으므로
    구조 필드에서도 FAIL이 아니라 WARN이다."""
    roster = {"students": [{"학번": "30101", "이름": "김하윤"}]}
    issues = scan_leak("하윤아 함께 발표했다", roster, scope="구조")
    assert ("WARN", "NAME_LEAK") in _codes(issues)
    assert not any(lv == "FAIL" for lv, _ in _codes(issues))


def test_scan_leak_given_name_bare_without_suffix_is_not_warned():
    """실측 근거(맨몸 성 제외 이름 오탐 4건, 조사 동반 0건)에 따라 치환 조건과
    검사 조건을 일치시킨다 — 맨몸 등장은 WARN도 내지 않는다."""
    roster = {"students": [{"학번": "30401", "이름": "김하늘"}]}
    issues = scan_leak("하늘을 우러러 다짐한다.", roster, scope="본문")
    assert issues == []


def test_destroy_artifacts_removes_all_and_returns_names_no_pii(tmp_path, capsys):
    """destroy_artifacts는 여러 산출물을 지우고 파일명 목록을 반환하되,
    이름·학번 등 내용은 출력하지 않아야 한다(적대적 감사 FINDING 3)."""
    import json

    from pseudonymize import destroy_artifacts

    (tmp_path / "매핑.json").write_text(
        json.dumps(issue_tokens(ROSTER, submitted_ids=["10101"]), ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "명렬.json").write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "관찰메모.json").write_text(
        json.dumps({"items": [{"토큰": "S-ABCD", "메모": "김가상은 성실함."}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    capsys.readouterr()  # 이전 캡처 비우기
    destroyed = destroy_artifacts(tmp_path)
    captured = capsys.readouterr()

    assert set(destroyed) == {"매핑.json", "명렬.json", "관찰메모.json"}
    assert not (tmp_path / "매핑.json").exists()
    assert not (tmp_path / "명렬.json").exists()
    assert not (tmp_path / "관찰메모.json").exists()
    assert captured.out == ""
    assert "김가상" not in captured.out
    assert "10101" not in captured.out
