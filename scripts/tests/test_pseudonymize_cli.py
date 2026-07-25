# -*- coding: utf-8 -*-
"""pseudonymize.py CLI 서브커맨드 테스트.

핵심 계약: 명렬(실명·학번)이 이 CLI를 거치는 동안 stdout에 절대 등장하지 않는다.
LLM(에이전트)은 이 CLI의 stdout만 읽으므로, stdout에 이름·학번이 새면 이 기능의
존재 이유가 사라진다.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parents[1] / "pseudonymize.py")

ROSTER = {"students": [
    {"학번": "10101", "이름": "김가상"},
    {"학번": "10102", "이름": "이허구"},
    {"학번": "10103", "이름": "박미정"},
]}

NAMES = ["김가상", "이허구", "박미정"]
IDS = ["10101", "10102", "10103"]


def run(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def assert_no_pii(text):
    for name in NAMES:
        assert name not in text
    for sid in IDS:
        assert sid not in text


def _make_roster_xlsx(tmp_path):
    from openpyxl import Workbook

    p = tmp_path / "명단.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["학번", "이름"])
    for s in ROSTER["students"]:
        ws.append([s["학번"], s["이름"]])
    wb.save(p)
    return p


# ---------------------------------------------------------------------------
# roster
# ---------------------------------------------------------------------------

def test_roster_cli_happy_path(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    proc = run("roster", str(src), "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["students"]) == 3
    assert "명렬 인식: 3명" in proc.stdout
    assert "표헤더" in proc.stdout
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)


def test_roster_cli_pattern_mode_adds_warning(tmp_path):
    from openpyxl import Workbook

    p = tmp_path / "명단.xlsx"
    wb = Workbook()
    ws = wb.active
    for s in ROSTER["students"][:2]:
        ws.append([s["학번"], s["이름"]])
    wb.save(p)
    out = tmp_path / "명렬.json"
    proc = run("roster", str(p), "--out", str(out))
    assert proc.returncode == 0
    assert "패턴" in proc.stdout
    assert "확인" in proc.stdout
    assert_no_pii(proc.stdout)


def test_roster_cli_zero_detected_fails(tmp_path):
    p = tmp_path / "빈파일.txt"
    p.write_text("아무 명단도 없는 문서입니다.\n", encoding="utf-8")
    out = tmp_path / "명렬.json"
    proc = run("roster", str(p), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert "0명" in proc.stdout


# ---------------------------------------------------------------------------
# issue
# ---------------------------------------------------------------------------

def _write_roster_json(tmp_path):
    p = tmp_path / "명렬.json"
    p.write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
    return p


def test_issue_cli_happy_path(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    out = tmp_path / "매핑.json"
    proc = run("issue", "--roster", str(roster_path), "--submitted", "10101,10102", "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()
    mapping = json.loads(out.read_text(encoding="utf-8"))
    assert set(mapping["map"]) == {"10101", "10102"}
    assert "제출자 2명" in proc.stdout
    assert "미발급(미제출) 1명" in proc.stdout
    assert_no_pii(proc.stdout)


def test_issue_cli_submitted_from_file(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    submitted_file = tmp_path / "제출자.txt"
    submitted_file.write_text("10101\n10102\n", encoding="utf-8")
    out = tmp_path / "매핑.json"
    proc = run("issue", "--roster", str(roster_path), "--submitted-from", str(submitted_file), "--out", str(out))
    assert proc.returncode == 0
    mapping = json.loads(out.read_text(encoding="utf-8"))
    assert set(mapping["map"]) == {"10101", "10102"}
    assert_no_pii(proc.stdout)


def test_issue_cli_reuses_existing_mapping(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    out = tmp_path / "매핑.json"
    run("issue", "--roster", str(roster_path), "--submitted", "10101", "--out", str(out))
    first = json.loads(out.read_text(encoding="utf-8"))
    proc = run("issue", "--roster", str(roster_path), "--submitted", "10101,10102", "--out", str(out))
    assert proc.returncode == 0
    second = json.loads(out.read_text(encoding="utf-8"))
    assert second["map"]["10101"] == first["map"]["10101"]
    assert "10102" in second["map"]
    assert_no_pii(proc.stdout)


# ---------------------------------------------------------------------------
# mask
# ---------------------------------------------------------------------------

def _write_mapping(tmp_path, roster_path, submitted):
    out = tmp_path / "매핑.json"
    run("issue", "--roster", str(roster_path), "--submitted", ",".join(submitted), "--out", str(out))
    return out, json.loads(out.read_text(encoding="utf-8"))


def test_mask_cli_happy_path(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101", "10102"])

    input_json = tmp_path / "입력.json"
    input_json.write_text(json.dumps({"items": [
        {"학번": "10101", "본문": "10101 김가상은 이허구와 함께 발표함."},
        {"학번": "10102", "본문": "봄을 노래한 시를 분석함."},
    ]}, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "토큰본.json"
    proc = run("mask", str(input_json), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 2
    for item in saved["items"]:
        assert "토큰" in item
        assert item["토큰"].startswith("S-")
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)
    # 저장된 파일 자체에도 실명·학번이 없어야 한다(치환이 실제로 됐는지 확인)
    saved_text = out.read_text(encoding="utf-8")
    assert_no_pii(saved_text)
    assert "가명화: 2건 처리" in proc.stdout
    assert "학번 유출 0건" in proc.stdout


def test_mask_cli_leak_blocks_save(tmp_path):
    """미발급자(미제출자)의 학번이 다른 학생 본문에 그대로 남으면 저장하지 않고 exit 1."""
    roster_path = _write_roster_json(tmp_path)
    # 10103(박미정)은 미제출 → 토큰 미발급
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    input_json = tmp_path / "입력.json"
    input_json.write_text(json.dumps({"items": [
        {"학번": "10101", "본문": "10103 학생의 답안을 참고해 정리함."},
    ]}, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "토큰본.json"
    proc = run("mask", str(input_json), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)


def test_mask_cli_unissued_own_id_fails_closed(tmp_path):
    """입력 항목의 학번 자체가 매핑에 없으면(토큰 발급 누락) 저장하지 않고 exit 1."""
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    input_json = tmp_path / "입력.json"
    input_json.write_text(json.dumps({"items": [
        {"학번": "10102", "본문": "발표를 준비함."},
    ]}, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "토큰본.json"
    proc = run("mask", str(input_json), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert_no_pii(proc.stdout)


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------

def test_finalize_cli_happy_path(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101", "10102"])
    token1 = mapping["map"]["10101"]
    token2 = mapping["map"]["10102"]

    draft = {"classes": [{"name": "1반", "students": [
        {"토큰": token1, "핵심소재": "가상의 책", "톤등급": "중", "세특": "작품을 분석함.", "비고": "", "예외": False},
        {"토큰": token2, "핵심소재": "가상의 시", "톤등급": "상", "세특": "감상을 정리함.", "비고": "", "예외": False},
    ]}]}
    draft_path = tmp_path / "토큰초안.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "실명초안.json"
    proc = run("finalize", str(draft_path), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()
    saved = json.loads(out.read_text(encoding="utf-8"))
    students = saved["classes"][0]["students"]
    assert {"학번": "10101", "이름": "김가상"}.items() <= students[0].items()
    assert {"학번": "10102", "이름": "이허구"}.items() <= students[1].items()
    assert "재결합: 2명 복원 완료" in proc.stdout
    # stdout 자체에는 실명·학번이 등장하면 안 된다(에이전트가 읽는 것은 stdout뿐)
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)


def test_finalize_cli_unmapped_token_fails(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    draft = {"classes": [{"name": "1반", "students": [
        {"토큰": "S-FFFF", "핵심소재": "가상의 책", "톤등급": "중", "세특": "작품을 분석함.", "비고": "", "예외": False},
    ]}]}
    draft_path = tmp_path / "토큰초안.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "실명초안.json"
    proc = run("finalize", str(draft_path), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert_no_pii(proc.stdout)


# ---------------------------------------------------------------------------
# memo — 교사 관찰 메모를 대화가 아니라 파일로 받아 토큰화한다.
# 핵심 계약: 이름·학번·메모 내용이 stdout/stderr에 등장하면 안 된다.
# ---------------------------------------------------------------------------

def test_memo_cli_xlsx_happy_path(tmp_path):
    from openpyxl import Workbook

    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101", "10102"])

    p = tmp_path / "채점표.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["학번", "관찰 메모"])
    ws.append(["10101", "10101 김가상은 발표 때 질문이 좋았다."])
    ws.append(["10102", "이허구와 함께 성실히 참여함."])
    wb.save(p)

    out = tmp_path / "관찰메모.json"
    proc = run("memo", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 2
    for item in saved["items"]:
        assert item["토큰"].startswith("S-")
        assert "메모" in item

    saved_text = out.read_text(encoding="utf-8")
    assert_no_pii(saved_text)
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)
    assert "관찰 메모: 2건 수집" in proc.stdout
    assert "학번 유출 0건" in proc.stdout


def test_memo_cli_xlsx_header_variants(tmp_path):
    """헤더 공백·표기 변형(특기사항, 관찰메모)도 자동 탐지한다."""
    from openpyxl import Workbook

    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    p = tmp_path / "채점표.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["학번", "특기사항"])
    ws.append(["10101", "성실히 참여함."])
    wb.save(p)

    out = tmp_path / "관찰메모.json"
    proc = run("memo", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 1
    assert_no_pii(proc.stdout)


def test_memo_cli_xlsx_missing_header_fails(tmp_path):
    from openpyxl import Workbook

    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    p = tmp_path / "채점표.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["학번", "비고"])
    ws.append(["10101", "성실히 참여함."])
    wb.save(p)

    out = tmp_path / "관찰메모.json"
    proc = run("memo", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert "메모 열 헤더를 '관찰 메모'로 지정해 주세요" in proc.stdout
    assert_no_pii(proc.stdout)


def test_memo_cli_xlsx_skips_empty_memo_cells(tmp_path):
    from openpyxl import Workbook

    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101", "10102"])

    p = tmp_path / "채점표.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["학번", "관찰 메모"])
    ws.append(["10101", "발표가 인상적이었다."])
    ws.append(["10102", ""])
    wb.save(p)

    out = tmp_path / "관찰메모.json"
    proc = run("memo", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 1
    assert "관찰 메모: 1건 수집" in proc.stdout


def test_memo_cli_text_happy_path(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101", "10102"])

    p = tmp_path / "메모.txt"
    p.write_text(
        "10101: 김가상은 발표 때 질문이 좋았다.\n"
        "10102 이허구와 함께 성실히 참여함.\n",
        encoding="utf-8",
    )

    out = tmp_path / "관찰메모.json"
    proc = run("memo", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 2
    for item in saved["items"]:
        assert item["토큰"].startswith("S-")

    saved_text = out.read_text(encoding="utf-8")
    assert_no_pii(saved_text)
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)
    assert "관찰 메모: 2건 수집" in proc.stdout


def test_memo_cli_unmapped_id_excluded(tmp_path):
    """명렬에 없거나(미제출) 매핑이 없는 학번의 메모는 건수만 반영하고 제외한다."""
    roster_path = _write_roster_json(tmp_path)
    # 10103(박미정)은 미제출 → 토큰 미발급
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    p = tmp_path / "메모.txt"
    p.write_text(
        "10101: 발표가 좋았다.\n"
        "10103: 박미정은 미제출이지만 메모가 남아 있다.\n",
        encoding="utf-8",
    )

    out = tmp_path / "관찰메모.json"
    proc = run("memo", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 1
    assert saved["items"][0]["토큰"] == mapping["map"]["10101"]
    assert "1건 수집(1건은 매핑 없음으로 제외)" in proc.stdout
    assert_no_pii(proc.stdout)
    assert_no_pii(out.read_text(encoding="utf-8"))


def test_memo_cli_leak_blocks_save(tmp_path):
    """메모 본문에 매핑 없는(미제출자) 학번이 그대로 남으면 저장하지 않고 exit 1."""
    roster_path = _write_roster_json(tmp_path)
    # 10103(박미정)은 미제출 → 토큰 미발급이라 pseudonymize_text가 치환할 수 없다
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    p = tmp_path / "메모.txt"
    p.write_text("10101: 10103 학생과 비교하면 발표가 좋았다.\n", encoding="utf-8")

    out = tmp_path / "관찰메모.json"
    proc = run("memo", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)
