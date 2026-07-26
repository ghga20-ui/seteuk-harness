# -*- coding: utf-8 -*-
"""교사 선언 인원 대조 + 제출 원본 대조 테스트(가상 인물만).

실측 감사 결과: 기존 ROSTER 대조는 초안의 이름을 명렬에서 그대로 붙인 뒤
같은 명렬과 다시 비교하는 항진명제였다(명렬을 명렬로 검증). 명렬 자체가
잘못되면(예: 이름 열이 한 칸씩 밀린 경우) 전원의 이름이 서로 어긋나도
그 대조는 100% 통과했다. 이 파일은 명렬에서 파생되지 않은 외부 정보
(교사 선언 인원수, 제출 원본)로 그 구멍을 막는 새 게이트를 검증한다.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_seteuk import load_submitted_ids, verify_drafts  # noqa: E402

SCRIPT = str(Path(__file__).resolve().parents[1] / "verify_seteuk.py")

PROFILE = {
    "활동명": "가상 활동", "문두": "가상 활동에서",
    "목표바이트": 700, "상한바이트": 760,
    "평가자료": "가상 채점표(테스트)",
}

GOOD_TEXT = (
    "가상 활동에서 '가상의 책(작가)'을 선정하여 인물의 갈등에 주목하며 감상문을 작성함. "
    "서술 시점의 효과를 짚고 인물의 내적 갈등이 심화되는 과정을 정리함. "
    "작품에 반영된 사회 현실을 비판적으로 읽어냄. "
    "자신의 경험과 견주어 삶의 태도를 성찰하는 다짐을 밝힘. "
    "감상의 근거를 본문에서 찾아 제시하는 태도가 돋보임. "
    "작품을 자기 이해의 계기로 삼는 모습을 보임."
)


def make_student(sid, name):
    # 예외=True로 두어 이 파일의 초점(인원·제출 대조)과 무관한 문두·분량 WARN을
    # 배제한다 — 그런 WARN도 기존 사양상 학번을 함께 출력하므로 놔두면
    # "요약에 학번이 없어야 한다" 단언이 이 테스트의 초점과 무관하게 깨진다.
    return {"학번": sid, "이름": name, "핵심소재": "가상의 책(작가)",
            "톤등급": "중", "세특": GOOD_TEXT, "비고": "", "예외": True}


def make_bulk_drafts(n, prefix="1"):
    """가상 학생 n명을 만든다. 학번·이름은 겹치지 않는 가상 값이다."""
    students = [make_student(f"{prefix}{i:04d}", f"가상학생{i:04d}") for i in range(n)]
    return {"classes": [{"name": "1반", "students": students}]}


def make_roster_for(drafts):
    roster_students = []
    for cls in drafts["classes"]:
        for s in cls["students"]:
            roster_students.append({"학번": s["학번"], "이름": s["이름"]})
    return {"students": roster_students}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_cli(tmp_path, drafts, profile=None, roster=None, submitted=None,
            save=True, expected_count=None):
    profile = dict(profile if profile is not None else PROFILE)
    drafts_path = tmp_path / "d.json"
    profile_path = tmp_path / "p.json"
    out = tmp_path / "out.xlsx"
    write_json(drafts_path, drafts)
    write_json(profile_path, profile)
    cmd = [sys.executable, SCRIPT, str(drafts_path), "--profile", str(profile_path)]
    if roster is not None:
        roster_path = tmp_path / "r.json"
        write_json(roster_path, roster)
        cmd += ["--roster", str(roster_path)]
    if submitted is not None:
        submitted_path = tmp_path / "s.json"
        write_json(submitted_path, submitted)
        cmd += ["--submitted", str(submitted_path)]
    if expected_count is not None:
        cmd += ["--expected-count", str(expected_count)]
    if save:
        cmd += ["--save", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return proc, out


# ---------------------------------------------------------------------------
# ① 교사 선언 인원 대조
# ---------------------------------------------------------------------------

def test_save_without_expected_count_or_profile_count_rejected(tmp_path):
    """--expected-count도 프로파일 '인원'도 없으면 저장 거부, 파일 미생성."""
    drafts = make_bulk_drafts(3)
    roster = make_roster_for(drafts)
    proc, out = run_cli(tmp_path, drafts, roster=roster)
    assert proc.returncode == 1
    assert not out.exists()
    assert "--expected-count" in proc.stdout


def test_declared_count_mismatch_blocks_save_and_shows_diff_without_names(tmp_path):
    """선언 48 vs 저장 46 -> exit 1, 차이(2) 출력, 이름·학번은 출력되지 않음."""
    drafts = make_bulk_drafts(46)
    roster = make_roster_for(drafts)
    proc, out = run_cli(tmp_path, drafts, roster=roster, expected_count=48)
    assert proc.returncode == 1
    assert not out.exists()
    assert "인원 불일치" in proc.stdout
    assert "48" in proc.stdout and "46" in proc.stdout
    assert "2명" in proc.stdout
    # 이름·학번이 요약 문구에 노출되면 안 된다.
    for s in drafts["classes"][0]["students"]:
        assert s["이름"] not in proc.stdout
        assert s["학번"] not in proc.stdout


def test_declared_count_matches_actual_saves_normally(tmp_path):
    """선언과 실제가 같으면 정상 저장된다."""
    drafts = make_bulk_drafts(5)
    roster = make_roster_for(drafts)
    proc, out = run_cli(tmp_path, drafts, roster=roster, expected_count=5)
    assert proc.returncode == 0
    assert out.exists()
    assert "저장 완료" in proc.stdout


def test_profile_count_reused_and_shown_on_stdout(tmp_path):
    """프로파일의 '인원'으로 통과하되, 재사용하는 값이 stdout에 보여야 한다."""
    drafts = make_bulk_drafts(4)
    roster = make_roster_for(drafts)
    profile = dict(PROFILE)
    profile["인원"] = 4
    proc, out = run_cli(tmp_path, drafts, profile=profile, roster=roster)
    assert proc.returncode == 0
    assert out.exists()
    assert "4명" in proc.stdout
    assert "재사용" in proc.stdout


# ---------------------------------------------------------------------------
# ② 제출 원본 대조(명렬과 독립된 경로)
# ---------------------------------------------------------------------------

def test_submitted_missing_student_blocks_save(tmp_path):
    """초안에 있는 학번이 제출자 목록에 없으면 FAIL로 저장이 차단된다."""
    drafts = make_bulk_drafts(3)
    roster = make_roster_for(drafts)
    all_ids = [s["학번"] for s in drafts["classes"][0]["students"]]
    # 마지막 학생은 제출자 목록에서 빠뜨린다(제출 안 했는데 세특이 생성된 상황 재현).
    # 예외 표시가 없어야 한다 — 미제출자에게 쓰는 예외 세특은 정상이므로 막지 않는다.
    drafts["classes"][0]["students"][-1]["예외"] = False
    submitted = {"학번목록": all_ids[:-1]}
    proc, out = run_cli(tmp_path, drafts, roster=roster, submitted=submitted, expected_count=3)
    assert proc.returncode == 1
    assert not out.exists()
    assert "NOT_SUBMITTED" in proc.stdout
    assert "FAIL" in proc.stdout


def test_submitted_all_present_passes(tmp_path):
    """전원이 제출자 목록에 있으면 제출 대조는 저장을 막지 않는다."""
    drafts = make_bulk_drafts(3)
    roster = make_roster_for(drafts)
    all_ids = [s["학번"] for s in drafts["classes"][0]["students"]]
    submitted = {"학번목록": all_ids}
    proc, out = run_cli(tmp_path, drafts, roster=roster, submitted=submitted, expected_count=3)
    assert proc.returncode == 0
    assert out.exists()


def test_submitted_not_given_shows_explicit_skip_notice(tmp_path):
    """--submitted 미지정 시 검사를 건너뛰었다는 문구가 stdout에 있어야 한다."""
    drafts = make_bulk_drafts(2)
    roster = make_roster_for(drafts)
    proc, out = run_cli(tmp_path, drafts, roster=roster, expected_count=2)
    assert proc.returncode == 0
    assert "건너뛰었습니다" in proc.stdout
    assert "NO_SUBMITTED_CHECK" in proc.stdout


def test_load_submitted_ids_supports_multiple_shapes(tmp_path):
    """제출 원본 로더가 리스트/학번목록/맵(매핑.json)/students/classes 형태를 모두 지원한다."""
    p1 = tmp_path / "a.json"
    write_json(p1, ["10101", "10102"])
    assert load_submitted_ids(p1) == {"10101", "10102"}

    p2 = tmp_path / "b.json"
    write_json(p2, {"학번목록": ["10101", "10102"]})
    assert load_submitted_ids(p2) == {"10101", "10102"}

    p3 = tmp_path / "c.json"  # 매핑.json과 동일한 모양 — 키가 학번
    write_json(p3, {"활동": "가상", "map": {"10101": "S-AB12", "10102": "S-CD34"}})
    assert load_submitted_ids(p3) == {"10101", "10102"}

    p4 = tmp_path / "d.json"
    write_json(p4, {"students": [{"학번": "10101"}, {"학번": "10102"}]})
    assert load_submitted_ids(p4) == {"10101", "10102"}

    p5 = tmp_path / "e.json"
    write_json(p5, {"classes": [{"students": [{"학번": "10101"}, {"학번": "10102"}]}]})
    assert load_submitted_ids(p5) == {"10101", "10102"}


# ---------------------------------------------------------------------------
# ③ 기존 ROSTER 대조는 형식 일치만 확인한다는 사실을 정직하게 표시
# ---------------------------------------------------------------------------

def test_roster_check_disclaimer_shown_when_roster_used(tmp_path):
    drafts = make_bulk_drafts(2)
    roster = make_roster_for(drafts)
    proc, out = run_cli(tmp_path, drafts, roster=roster, expected_count=2)
    assert "형식 일치만 확인" in proc.stdout
    assert "오귀속은 증명되지" in proc.stdout


# ---------------------------------------------------------------------------
# 항진명제 회귀 테스트 — 이번 수정의 핵심 증명
# ---------------------------------------------------------------------------

def test_tautology_regression_row_shift_caught_by_count_and_submitted_gate(tmp_path):
    """명렬 실측 감사 FINDING 재현.

    명렬의 이름 열이 한 칸 밀려 만들어진 명렬.json을 그대로 재현한다:
    실제 명렬은 (10101,김민준) (10102,이서연) (10103,박도윤) (10104,최수아)
    인데, 이름 열이 한 칸 아래로 밀려 (10101,"") (10102,김민준) (10103,이서연)
    (10104,박도윤)이 되고 최수아라는 이름은 아예 유실된다(흔한 스프레드시트
    붙여넣기 사고). finalize는 이 밀린 명렬에서 이름을 그대로 가져다 붙이므로
    10102는 실제로는 이서연인데 김민준이라는 이름을 달고 저장되려 한다 —
    그러나 이름 열이 비었던 10101은 finalize가 이름을 붙이지 못해 초안에서
    빠진다(실제 파이프라인에서 흔한 실패 모드).

    이 초안을 밀린 명렬 그대로와 대조하면:
    - 기존 ROSTER 대조(학번↔이름 형식 일치)는 전원 통과한다(항진명제 — 이름이
      바로 그 명렬에서 왔으므로 그 명렬과 항상 일치한다).
    - 그러나 교사가 아는 실제 인원(4명)과 저장 대상(3명)이 어긋나 인원 대조가
      저장을 차단한다.
    - 그리고 명렬과 무관한 제출자 목록(4명 전원 제출)과 대조하면 10101이
      초안에 없다는 사실이 WARN(SUBMITTED_NOT_DRAFTED)으로도 드러난다.
    """
    shifted_roster = {"students": [
        {"학번": "10101", "이름": ""},
        {"학번": "10102", "이름": "김민준"},
        {"학번": "10103", "이름": "이서연"},
        {"학번": "10104", "이름": "박도윤"},
    ]}
    # finalize가 밀린 명렬에서 그대로 이름을 붙인 결과: 10101은 빈 이름이라 빠지고
    # 나머지 3명은 밀린 이름을 단 채로 초안에 들어간다.
    drafts = {"classes": [{"name": "1반", "students": [
        make_student("10102", "김민준"),
        make_student("10103", "이서연"),
        make_student("10104", "박도윤"),
    ]}]}

    # 1) 검증 함수 수준에서: 기존 ROSTER 대조는 통과(항진명제 확인).
    report = verify_drafts(drafts, PROFILE, roster=shifted_roster)
    roster_fails = [
        (r["학번"], code, msg)
        for r in report["rows"]
        for lv, code, msg in r["issues"]
        if lv == "FAIL" and code == "ROSTER"
    ]
    assert roster_fails == [], (
        "기존 ROSTER 대조가 밀린 명렬에서도 전원 통과함을 확인하는 것이 이 회귀 "
        f"테스트의 전제인데 FAIL이 나왔다: {roster_fails}"
    )

    # 2) 교사가 실제로 아는 인원은 4명 — 인원 대조가 저장을 막아야 한다.
    proc, out = run_cli(tmp_path, drafts, roster=shifted_roster, expected_count=4)
    assert proc.returncode == 1
    assert not out.exists()
    assert "인원 불일치" in proc.stdout
    assert "4" in proc.stdout and "3" in proc.stdout

    # 3) 명렬과 무관한 제출자 목록(4명 전원 제출)과 대조해도 10101 누락이 드러난다.
    submitted = {"학번목록": ["10101", "10102", "10103", "10104"]}
    report2 = verify_drafts(drafts, PROFILE, roster=shifted_roster, submitted=submitted)
    warn_codes = [(code, msg) for lv, code, msg in report2["경고"] if code == "SUBMITTED_NOT_DRAFTED"]
    assert len(warn_codes) == 1
    assert "1명" in warn_codes[0][1]


def test_unsubmitted_student_with_exempt_draft_is_allowed(tmp_path):
    """미제출자에게도 활동 참여 사실만 담은 예외 세특을 쓰는 것이 규칙이다.

    제출 대조가 예외 여부를 보지 않고 FAIL을 내면, 규칙대로 쓴 초안이
    저장되지 않는다. 미제출은 WARN으로 알리되 저장은 막지 않아야 한다.
    """
    drafts = make_bulk_drafts(3)
    roster = make_roster_for(drafts)
    all_ids = [s["학번"] for s in drafts["classes"][0]["students"]]
    last = drafts["classes"][0]["students"][-1]
    last["예외"] = True
    last["세특"] = "가상 활동에 참여함."
    last["비고"] = "미제출"
    submitted = {"학번목록": all_ids[:-1]}
    proc, out = run_cli(tmp_path, drafts, roster=roster, submitted=submitted, expected_count=3)
    assert proc.returncode == 0
    assert out.exists()
    assert "NOT_SUBMITTED_EXEMPT" in proc.stdout


def test_unsubmitted_student_with_full_draft_still_blocked(tmp_path):
    """예외 표시 없이 정상 세특이 있는데 제출 기록이 없으면 여전히 막는다."""
    drafts = make_bulk_drafts(3)
    roster = make_roster_for(drafts)
    all_ids = [s["학번"] for s in drafts["classes"][0]["students"]]
    drafts["classes"][0]["students"][-1]["예외"] = False
    submitted = {"학번목록": all_ids[:-1]}
    proc, out = run_cli(tmp_path, drafts, roster=roster, submitted=submitted, expected_count=3)
    assert proc.returncode == 1
    assert not out.exists()
    assert "NOT_SUBMITTED" in proc.stdout
