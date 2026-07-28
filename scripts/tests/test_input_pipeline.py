# -*- coding: utf-8 -*-
"""파일 직접 입력 파이프라인 테스트 (입력방식-결론 §5 CLI 항목 1~5).

다섯 기능을 검증한다:
1. detect — 채점표 후보 탐지(파일명·수정시각·시트 수만, 내용 미출력)
2. roster --profile — 파일 선언 + 구조 지문(불일치 시 exit 1)
3. ~$ 잠금 파일 감지(경고만, 차단 아님)
4. confirm-html — 읽기 전용 실명 확인 화면(stdout 무실명, 파기 그물 포함)
5. --clipboard — 비상구 전용 클립보드 리더(빈 클립보드 exit 1, 2연속 안내)

핵심 계약은 기존과 같다: stdout/stderr에 학생 이름·학번이 절대 등장하지 않는다
(단, 확인 HTML *파일*은 실명 확인이 목적이므로 실명을 담는다 — 로컬 전용·파기 대상).
클립보드 테스트는 실제 클립보드를 건드리지 않도록 읽기 함수를 monkeypatch한 뒤
main()을 인프로세스로 호출한다(실환경 실측은 스위트 밖에서 1회 수행).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pseudonymize

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


def _make_roster_xlsx(tmp_path, filename="명단.xlsx", extra_rows=(), extra_header=()):
    from openpyxl import Workbook

    p = tmp_path / filename
    wb = Workbook()
    ws = wb.active
    ws.append(["학번", "이름", *extra_header])
    for s in ROSTER["students"]:
        ws.append([s["학번"], s["이름"]])
    for r in extra_rows:
        ws.append(list(r))
    wb.save(p)
    return p


def _write_roster_json(tmp_path):
    p = tmp_path / "명렬.json"
    p.write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
    return p


def _write_mapping(tmp_path, roster_path, submitted):
    out = tmp_path / "매핑.json"
    run("issue", "--roster", str(roster_path), "--submitted", ",".join(submitted), "--out", str(out))
    return out, json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. detect — 채점표 후보 탐지
# ---------------------------------------------------------------------------

def test_detect_two_candidates_lists_newest_first_without_contents(tmp_path):
    """후보 2개 이상이면 수정시각순(최신 먼저) 목록을 exit 0으로 출력한다.
    파일명·수정시각·시트 수만 — 셀 내용(이름·학번)은 절대 출력하지 않는다."""
    old = _make_roster_xlsx(tmp_path, filename="채점표_백업_0315.xlsx")
    new = _make_roster_xlsx(tmp_path, filename="2026_1학기_수행평가_채점표.xlsx")
    past = 1700000000
    os.utime(old, (past, past))

    proc = run("detect", "--dir", str(tmp_path))
    assert proc.returncode == 0
    assert "2개" in proc.stdout
    assert "2026_1학기_수행평가_채점표.xlsx" in proc.stdout
    assert "채점표_백업_0315.xlsx" in proc.stdout
    # 최신 파일이 먼저 나와야 한다
    assert proc.stdout.index("2026_1학기_수행평가_채점표.xlsx") < proc.stdout.index("채점표_백업_0315.xlsx")
    # 시트 수는 표시하되 셀 내용은 없다
    assert "시트 1개" in proc.stdout
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)


def test_detect_single_candidate_reports_fact(tmp_path):
    _make_roster_xlsx(tmp_path, filename="채점표.xlsx")
    proc = run("detect", "--dir", str(tmp_path))
    assert proc.returncode == 0
    assert "1개" in proc.stdout
    assert "채점표.xlsx" in proc.stdout
    assert_no_pii(proc.stdout)


def test_detect_zero_candidates_fails_with_guidance(tmp_path):
    proc = run("detect", "--dir", str(tmp_path))
    assert proc.returncode == 1
    assert "보이지 않습니다" in proc.stdout


def test_detect_ignores_excel_lock_files(tmp_path):
    _make_roster_xlsx(tmp_path, filename="채점표.xlsx")
    (tmp_path / "~$채점표.xlsx").write_bytes(b"lock")
    proc = run("detect", "--dir", str(tmp_path))
    assert proc.returncode == 0
    assert "1개" in proc.stdout
    assert "~$" not in proc.stdout


def test_detect_lists_legacy_xls_with_format_note(tmp_path):
    """구형 .xls도 후보로 나열하되(교사는 이 파일을 쓰려던 것일 수 있다) 시트 수
    대신 형식 안내를 붙인다."""
    p = tmp_path / "옛채점표.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    proc = run("detect", "--dir", str(tmp_path))
    assert proc.returncode == 0
    assert "옛채점표.xls" in proc.stdout
    assert ".xlsx" in proc.stdout  # 재저장 안내


# ---------------------------------------------------------------------------
# 2. roster --profile — 파일 선언 + 구조 지문
# ---------------------------------------------------------------------------

def test_roster_profile_first_run_records_file_and_fingerprint(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    prof = tmp_path / "활동프로파일.json"
    proc = run("roster", str(src), "--out", str(out), "--profile", str(prof))
    assert proc.returncode == 0
    assert out.exists()
    saved = json.loads(prof.read_text(encoding="utf-8"))
    assert saved["명단파일"] == "명단.xlsx"
    fp = saved["구조지문"]
    assert fp["인원수"] == 3
    assert fp["시트명"]  # 시트명 목록이 비어 있지 않다
    assert fp["헤더행해시"]
    assert_no_pii(proc.stdout)
    assert_no_pii(prof.read_text(encoding="utf-8"))  # 지문에 실명·학번이 남으면 안 된다


def test_roster_profile_second_run_matches_and_proceeds(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    prof = tmp_path / "활동프로파일.json"
    run("roster", str(src), "--out", str(out), "--profile", str(prof))
    proc = run("roster", str(src), "--out", str(out), "--profile", str(prof))
    assert proc.returncode == 0
    assert "일치" in proc.stdout
    assert_no_pii(proc.stdout)


def test_roster_profile_count_mismatch_exits_1_with_readable_diff(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    prof = tmp_path / "활동프로파일.json"
    run("roster", str(src), "--out", str(out), "--profile", str(prof))

    # 학생 1명이 늘어난 명단으로 교체(전입 또는 다른 파일 오선택 상황)
    _make_roster_xlsx(tmp_path, extra_rows=[("10104", "최상상")])
    proc = run("roster", str(src), "--out", str(out), "--profile", str(prof))
    assert proc.returncode == 1
    assert "3명→4명" in proc.stdout
    # fail-closed: 불일치면 명렬.json을 새로 쓰지 않는다
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["students"]) == 3
    assert "최상상" not in proc.stdout
    assert_no_pii(proc.stdout)


def test_roster_profile_header_change_exits_1(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    prof = tmp_path / "활동프로파일.json"
    run("roster", str(src), "--out", str(out), "--profile", str(prof))

    # 인원수는 같지만 열 구성이 달라진 파일(헤더 행이 바뀜)
    _make_roster_xlsx(tmp_path, extra_header=("비고",))
    proc = run("roster", str(src), "--out", str(out), "--profile", str(prof))
    assert proc.returncode == 1
    assert "달라" in proc.stdout or "다릅니다" in proc.stdout
    assert_no_pii(proc.stdout)


def test_roster_profile_filename_change_exits_1(tmp_path):
    """구조가 같아도 파일이 바뀌면 멈춘다 — 백업본 오선택이 이 그물의 존재 이유다."""
    src_a = _make_roster_xlsx(tmp_path, filename="명단.xlsx")
    src_b = _make_roster_xlsx(tmp_path, filename="명단_백업.xlsx")
    out = tmp_path / "명렬.json"
    prof = tmp_path / "활동프로파일.json"
    run("roster", str(src_a), "--out", str(out), "--profile", str(prof))
    proc = run("roster", str(src_b), "--out", str(out), "--profile", str(prof))
    assert proc.returncode == 1
    assert "명단.xlsx" in proc.stdout
    assert "명단_백업.xlsx" in proc.stdout
    assert_no_pii(proc.stdout)


def test_roster_profile_preserves_existing_keys(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    prof = tmp_path / "활동프로파일.json"
    prof.write_text(json.dumps({"활동명": "소설 비평하기", "목표바이트": 700},
                               ensure_ascii=False), encoding="utf-8")
    proc = run("roster", str(src), "--out", str(out), "--profile", str(prof))
    assert proc.returncode == 0
    saved = json.loads(prof.read_text(encoding="utf-8"))
    assert saved["활동명"] == "소설 비평하기"
    assert saved["목표바이트"] == 700
    assert saved["명단파일"] == "명단.xlsx"
    assert "구조지문" in saved


def test_roster_without_profile_unchanged(tmp_path):
    """회귀: --profile 없는 기존 호출은 종전과 완전히 같아야 한다."""
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    proc = run("roster", str(src), "--out", str(out))
    assert proc.returncode == 0
    assert "명렬 인식: 3명" in proc.stdout
    assert_no_pii(proc.stdout)


# ---------------------------------------------------------------------------
# 3. ~$ 잠금 파일 감지 — 경고 한 줄, 차단은 아님
# ---------------------------------------------------------------------------

LOCK_WARNING = "이 파일이 엑셀에 열려 있습니다. 저장하셨는지 확인해 주세요."


def test_roster_lock_file_warns_but_proceeds(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    (tmp_path / ("~$" + src.name)).write_bytes(b"lock")
    out = tmp_path / "명렬.json"
    proc = run("roster", str(src), "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()
    assert LOCK_WARNING in proc.stdout
    assert_no_pii(proc.stdout)


def test_roster_no_lock_file_no_warning(tmp_path):
    src = _make_roster_xlsx(tmp_path)
    out = tmp_path / "명렬.json"
    proc = run("roster", str(src), "--out", str(out))
    assert proc.returncode == 0
    assert LOCK_WARNING not in proc.stdout


def test_score_lock_file_warns_but_proceeds(tmp_path):
    from openpyxl import Workbook

    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])

    p = tmp_path / "채점표.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["학번", "점수"])
    ws.append(["10101", "15"])
    wb.save(p)
    (tmp_path / ("~$" + p.name)).write_bytes(b"lock")

    out = tmp_path / "점수.json"
    proc = run("score", str(p), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    assert LOCK_WARNING in proc.stdout
    assert_no_pii(proc.stdout)


# ---------------------------------------------------------------------------
# 4. confirm-html — 읽기 전용 실명 확인 화면
# ---------------------------------------------------------------------------

def test_confirm_html_contains_all_students_but_stdout_is_masked(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    out = tmp_path / "확인.html"
    proc = run("confirm-html", "--roster", str(roster_path), "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    # 파일에는 전원(실명·학번·순번)이 있어야 한다 — 실명 대조가 목적이다
    for s in ROSTER["students"]:
        assert s["이름"] in html
        assert s["학번"] in html
    # 안내 문구
    assert "명단이 맞는지 훑어보세요" in html
    assert "이름은 치지 마시고" in html
    # JS 없음
    assert "<script" not in html.lower()
    # stdout/stderr에는 실명·학번이 절대 없다
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)
    assert "3명" in proc.stdout


def test_confirm_html_with_mapping_marks_submission(tmp_path):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101", "10102"])
    out = tmp_path / "확인.html"
    proc = run("confirm-html", "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))
    assert proc.returncode == 0
    html = out.read_text(encoding="utf-8")
    assert "제출" in html
    assert "미제출" in html
    assert_no_pii(proc.stdout)


def test_confirm_html_out_name_must_be_in_destroy_net(tmp_path):
    """산출 파일명이 파기 그물(확인*.html)에 걸리지 않으면 만들지 않는다 —
    실명 파일이 파기 대상 밖에 남는 것 자체가 사고다."""
    roster_path = _write_roster_json(tmp_path)
    out = tmp_path / "명단보기.html"
    proc = run("confirm-html", "--roster", str(roster_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert "확인" in proc.stdout
    assert_no_pii(proc.stdout)


def test_sensitive_globs_cover_confirm_and_review_html():
    assert "확인*.html" in pseudonymize.SENSITIVE_GLOBS
    assert "검수*.html" in pseudonymize.SENSITIVE_GLOBS


def test_destroy_removes_confirm_and_review_html_but_keeps_tool_html(tmp_path):
    (tmp_path / "확인.html").write_text("<p>가상</p>", encoding="utf-8")
    (tmp_path / "검수화면.html").write_text("<p>가상</p>", encoding="utf-8")
    (tmp_path / "도구.html").write_text("<p>keep</p>", encoding="utf-8")
    proc = run("destroy", "--dir", str(tmp_path), "--yes")
    assert proc.returncode == 0
    assert not (tmp_path / "확인.html").exists()
    assert not (tmp_path / "검수화면.html").exists()
    assert (tmp_path / "도구.html").exists()


# ---------------------------------------------------------------------------
# 5. --clipboard — 비상구 전용 클립보드 리더
# 실제 클립보드는 건드리지 않는다: 읽기 함수를 monkeypatch하고 main()을
# 인프로세스로 호출한다. 실환경(ctypes CF_UNICODETEXT) 실측은 스위트 밖 1회.
# ---------------------------------------------------------------------------

CLIP_ROSTER_TEXT = (
    "학번\t이름\r\n"
    "10101\t김가상\r\n"
    "10102\t이허구\r\n"
    "10103\t박미정\r\n"
)


def test_clipboard_rows_quoted_newline_cell_stays_one_row():
    """셀 안 줄바꿈(Alt+Enter)은 큰따옴표 + 생 \\n으로 온다 — 한 학생이 두
    행으로 쪼개지면 안 된다(csv.reader 인용 처리)."""
    text = '30104\t"가상\n한겨울"\r\n30105\t가상이바다\r\n'
    rows = pseudonymize._rows_from_clipboard_text(text)
    assert rows == [["30104", "가상한겨울"], ["30105", "가상이바다"]]


def test_clipboard_rows_comma_formatted_numbers_normalized():
    """엑셀 셀 서식(#,##0)이 값에 섞여 오면(30,101) 숫자에서 쉼표를 걷어낸다."""
    text = "30,101\t가상김하늘\r\n30,102\t가상이바다\r\n"
    rows = pseudonymize._rows_from_clipboard_text(text)
    assert rows == [["30101", "가상김하늘"], ["30102", "가상이바다"]]


def _fake_clip(monkeypatch, status, text):
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return (status, text)

    monkeypatch.setattr(pseudonymize, "_read_clipboard_text", fake)
    return calls


def test_roster_clipboard_happy_path(tmp_path, monkeypatch, capsys):
    _fake_clip(monkeypatch, "OK", CLIP_ROSTER_TEXT)
    out = tmp_path / "명렬.json"
    rc = pseudonymize.main(["roster", "--clipboard", "--out", str(out)])
    captured = capsys.readouterr()
    assert rc == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["students"]) == 3
    assert saved["출처"] == "클립보드"
    assert "3명" in captured.out
    assert_no_pii(captured.out)
    assert_no_pii(captured.err)


def test_roster_clipboard_extra_columns_still_detects(tmp_path, monkeypatch, capsys):
    """비인접 선택 오염(고르지 않은 점수 열이 딸려 옴)에도 학번·이름은 잡힌다."""
    text = "10101\t김가상\t15\r\n10102\t이허구\t13\r\n"
    _fake_clip(monkeypatch, "OK", text)
    out = tmp_path / "명렬.json"
    rc = pseudonymize.main(["roster", "--clipboard", "--out", str(out)])
    captured = capsys.readouterr()
    assert rc == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["students"]) == 2
    assert_no_pii(captured.out)


def test_roster_clipboard_empty_first_then_security_hint_on_second(tmp_path, monkeypatch, capsys):
    _fake_clip(monkeypatch, "NO_TEXT", None)
    out = tmp_path / "명렬.json"

    rc1 = pseudonymize.main(["roster", "--clipboard", "--out", str(out)])
    first = capsys.readouterr().out
    assert rc1 == 1
    assert "클립보드에 표가 보이지 않습니다" in first
    assert "보안 프로그램" not in first

    rc2 = pseudonymize.main(["roster", "--clipboard", "--out", str(out)])
    second = capsys.readouterr().out
    assert rc2 == 1
    assert "보안 프로그램" in second


def test_roster_clipboard_success_resets_empty_streak(tmp_path, monkeypatch, capsys):
    out = tmp_path / "명렬.json"
    _fake_clip(monkeypatch, "NO_TEXT", None)
    pseudonymize.main(["roster", "--clipboard", "--out", str(out)])
    capsys.readouterr()

    _fake_clip(monkeypatch, "OK", CLIP_ROSTER_TEXT)
    assert pseudonymize.main(["roster", "--clipboard", "--out", str(out)]) == 0
    capsys.readouterr()

    _fake_clip(monkeypatch, "NO_TEXT", None)
    pseudonymize.main(["roster", "--clipboard", "--out", str(out)])
    again = capsys.readouterr().out
    assert "보안 프로그램" not in again  # 성공이 연속 실패 횟수를 지웠다


def test_roster_clipboard_conflicts_with_input_and_profile(tmp_path, monkeypatch, capsys):
    _fake_clip(monkeypatch, "OK", CLIP_ROSTER_TEXT)
    out = tmp_path / "명렬.json"
    rc = pseudonymize.main(["roster", "가짜.xlsx", "--clipboard", "--out", str(out)])
    assert rc == 1
    capsys.readouterr()
    rc = pseudonymize.main(["roster", "--clipboard", "--out", str(out),
                            "--profile", str(tmp_path / "활동프로파일.json")])
    assert rc == 1
    capsys.readouterr()


def test_roster_without_input_and_without_clipboard_fails(tmp_path, capsys):
    rc = pseudonymize.main(["roster", "--out", str(tmp_path / "명렬.json")])
    assert rc == 1
    assert "클립보드" in capsys.readouterr().out  # 파일 경로 또는 --clipboard 안내


def test_score_clipboard_happy_path(tmp_path, monkeypatch, capsys):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101", "10102"])
    _fake_clip(monkeypatch, "OK", "10101\t15\r\n10102\t13\r\n")
    out = tmp_path / "점수.json"
    rc = pseudonymize.main([
        "score", "--clipboard", "--roster", str(roster_path),
        "--mapping", str(mapping_path), "--out", str(out),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    by_token = {item["토큰"]: item["점수"] for item in saved["items"]}
    assert by_token[mapping["map"]["10101"]] == 15
    assert by_token[mapping["map"]["10102"]] == 13
    assert "분포" in captured.out
    assert_no_pii(captured.out)
    assert_no_pii(out.read_text(encoding="utf-8"))


def test_score_clipboard_header_row_is_skipped(tmp_path, monkeypatch, capsys):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])
    _fake_clip(monkeypatch, "OK", "학번\t점수\r\n10101\t15\r\n")
    out = tmp_path / "점수.json"
    rc = pseudonymize.main([
        "score", "--clipboard", "--roster", str(roster_path),
        "--mapping", str(mapping_path), "--out", str(out),
    ])
    capsys.readouterr()
    assert rc == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 1


def test_score_clipboard_ambiguous_numeric_columns_fails(tmp_path, monkeypatch, capsys):
    """숫자 열이 여럿이면(비인접 선택으로 사이 열이 딸려 온 경우) 조용히 하나를
    고르지 않고 exit 1로 멈춘다."""
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])
    _fake_clip(monkeypatch, "OK", "10101\t14\t15\r\n10102\t12\t13\r\n")
    out = tmp_path / "점수.json"
    rc = pseudonymize.main([
        "score", "--clipboard", "--roster", str(roster_path),
        "--mapping", str(mapping_path), "--out", str(out),
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert not out.exists()
    assert "숫자 열" in captured.out
    assert_no_pii(captured.out)


def test_score_clipboard_empty_clipboard_fails(tmp_path, monkeypatch, capsys):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])
    _fake_clip(monkeypatch, "NO_TEXT", None)
    out = tmp_path / "점수.json"
    rc = pseudonymize.main([
        "score", "--clipboard", "--roster", str(roster_path),
        "--mapping", str(mapping_path), "--out", str(out),
    ])
    assert rc == 1
    assert "클립보드에 표가 보이지 않습니다" in capsys.readouterr().out


def test_score_clipboard_conflicts_with_file_options(tmp_path, monkeypatch, capsys):
    roster_path = _write_roster_json(tmp_path)
    mapping_path, mapping = _write_mapping(tmp_path, roster_path, ["10101"])
    _fake_clip(monkeypatch, "OK", "10101\t15\r\n")
    out = tmp_path / "점수.json"
    rc = pseudonymize.main([
        "score", "--clipboard", "--column", "R", "--roster", str(roster_path),
        "--mapping", str(mapping_path), "--out", str(out),
    ])
    assert rc == 1
    capsys.readouterr()


def test_clipboard_busy_status_reports_without_crash(tmp_path, monkeypatch, capsys):
    _fake_clip(monkeypatch, "BUSY", None)
    out = tmp_path / "명렬.json"
    rc = pseudonymize.main(["roster", "--clipboard", "--out", str(out)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "클립보드" in captured.out
