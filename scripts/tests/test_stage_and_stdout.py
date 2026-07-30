# -*- coding: utf-8 -*-
"""단계 자동 판별 + stdout 비식별화 회귀 테스트(등장인물 전부 가상).

계약: 에이전트(LLM)는 이 스크립트의 stdout만 읽는다. §6 토큰 단계 초안은
"토큰" 키만, §7 실명 단계 초안은 "학번" 키만 갖는다 — verify가 단계를 자동
판별해 토큰 단계에서는 토큰(안전한 식별자)을 찍고, 실명 단계에서는 학번이
어떤 형태로도 stdout에 나가지 않아야 한다(행별 상세는 --mapping의 학번→토큰
번역으로만 본다).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_seteuk as V

PROFILE = {"활동명": "가상 활동", "문두": "가상 활동에서", "목표바이트": 700, "상한바이트": 760,
           "평가자료": "가상 채점표(테스트)"}

GOOD_TEXT = (
    "가상 활동에서 '가상의 책(작가)'을 선정하여 인물의 갈등에 주목하며 감상문을 작성함. "
    "서술 시점의 효과를 짚고 인물의 내적 갈등이 심화되는 과정을 정리함. "
    "작품에 반영된 사회 현실을 비판적으로 읽어냄. "
    "자신의 경험과 견주어 삶의 태도를 성찰하는 다짐을 밝힘. "
    "감상의 근거를 본문에서 찾아 제시하는 태도가 돋보임. "
    "작품을 자기 이해의 계기로 삼는 모습을 보임."
)

# 4자리 이상 숫자 = 학번 후보. 이 파일의 시나리오에서 바이트 수(3자리)·건수
# (1~2자리)는 4자리에 닿지 않으므로, stdout에 이 패턴이 잡히면 학번 노출이다.
SID_LIKE = re.compile(r"\d{4,}")


def token_student(token, text=GOOD_TEXT, exempt=False):
    return {"토큰": token, "핵심소재": "가상의 책(작가)", "톤등급": "중",
            "세특": text, "비고": "", "예외": exempt}


def named_student(sid, name, text=GOOD_TEXT, exempt=False):
    return {"학번": sid, "이름": name, "핵심소재": "가상의 책(작가)", "톤등급": "중",
            "세특": text, "비고": "", "예외": exempt}


def wrap(students):
    return {"classes": [{"name": "1반", "students": students}]}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_main(tmp_path, capsys, drafts, roster=None, submitted=None, mapping=None, save=False):
    """main()을 같은 프로세스에서 실행하고 (exit코드, stdout)을 돌려준다."""
    write_json(tmp_path / "d.json", drafts)
    write_json(tmp_path / "p.json", PROFILE)
    argv = [str(tmp_path / "d.json"), "--profile", str(tmp_path / "p.json")]
    if roster is not None:
        write_json(tmp_path / "r.json", roster)
        argv += ["--roster", str(tmp_path / "r.json")]
    if submitted is not None:
        write_json(tmp_path / "s.json", submitted)
        argv += ["--submitted", str(tmp_path / "s.json")]
    if mapping is not None:
        write_json(tmp_path / "m.json", mapping)
        argv += ["--mapping", str(tmp_path / "m.json")]
    if save:
        argv += ["--save", str(tmp_path / "out.xlsx")]
    rc = V.main(argv)
    return rc, capsys.readouterr().out


# ---------------------------------------------------------------------------
# ① 단계 자동 판별
# ---------------------------------------------------------------------------

def test_detect_stage_token_and_named():
    assert V.detect_stage(wrap([token_student("S-AB12")])) == "token"
    assert V.detect_stage(wrap([named_student("10101", "김가상")])) == "named"


def test_token_drafts_run_text_checks_and_print_token(tmp_path, capsys):
    """토큰 초안이 토큰 단계로 판별되고, 기존 텍스트 검사가 그대로 동작한다."""
    drafts = wrap([token_student("S-AB12", text=GOOD_TEXT + " 또한 정리함.")])
    rc, out = run_main(tmp_path, capsys, drafts)
    assert rc == 1
    assert "BANNED_WORD" in out
    assert "S-AB12" in out  # 토큰은 안전한 식별자라 행별 출력에 쓴다
    assert "이름 혼입·명렬 대조·미제출 감지는 실명 단계에서 수행됩니다" in out


def test_token_stage_clean_passes(tmp_path, capsys):
    rc, out = run_main(tmp_path, capsys, wrap([token_student("S-AB12")]))
    assert rc == 0
    assert "결과: FAIL 0건" in out
    assert "이름 혼입·명렬 대조·미제출 감지는 실명 단계에서 수행됩니다" in out


def test_mixed_token_and_named_students_fail_stage_mixed(tmp_path, capsys):
    """토큰 학생과 실명 학생이 공존하면 STAGE_MIXED로 즉시 중단, 다른 검사 없음."""
    drafts = wrap([
        token_student("S-AB12", text=GOOD_TEXT + " 또한 정리함."),  # 검사가 돌았다면 BANNED_WORD가 찍혔을 본문
        named_student("10101", "김가상"),
    ])
    rc, out = run_main(tmp_path, capsys, drafts)
    assert rc == 1
    assert "STAGE_MIXED" in out
    assert "BANNED_WORD" not in out  # 텍스트 검사를 진행하지 않았다
    assert "결과:" not in out


def test_student_with_both_keys_fails_stage_mixed(tmp_path, capsys):
    student = token_student("S-AB12")
    student["학번"] = "10101"
    rc, out = run_main(tmp_path, capsys, wrap([student]))
    assert rc == 1
    assert "STAGE_MIXED" in out


def test_student_with_neither_key_fails_stage_mixed(tmp_path, capsys):
    student = token_student("S-AB12")
    del student["토큰"]
    rc, out = run_main(tmp_path, capsys, wrap([student]))
    assert rc == 1
    assert "STAGE_MIXED" in out


# ---------------------------------------------------------------------------
# ② 토큰 단계에서 실명 단계 전용 옵션 거부
# ---------------------------------------------------------------------------

def test_token_stage_rejects_roster(tmp_path, capsys):
    roster = {"students": [{"학번": "10101", "이름": "김가상"}]}
    rc, out = run_main(tmp_path, capsys, wrap([token_student("S-AB12")]), roster=roster)
    assert rc != 0
    assert "실명 재결합(finalize) 후의 실명 단계 전용" in out


def test_token_stage_rejects_submitted(tmp_path, capsys):
    rc, out = run_main(tmp_path, capsys, wrap([token_student("S-AB12")]),
                       submitted={"학번목록": ["10101"]})
    assert rc != 0
    assert "실명 재결합(finalize) 후의 실명 단계 전용" in out


def test_token_stage_rejects_save(tmp_path, capsys):
    rc, out = run_main(tmp_path, capsys, wrap([token_student("S-AB12")]), save=True)
    assert rc != 0
    assert "실명 재결합(finalize) 후의 실명 단계 전용" in out
    assert not (tmp_path / "out.xlsx").exists()


# ---------------------------------------------------------------------------
# ③ 중복 토큰 → DUP_TOKEN
# ---------------------------------------------------------------------------

def test_duplicate_token_fails_dup_token(tmp_path, capsys):
    drafts = wrap([token_student("S-AB12"), token_student("S-AB12")])
    rc, out = run_main(tmp_path, capsys, drafts)
    assert rc == 1
    assert "DUP_TOKEN" in out


def test_unique_tokens_pass_without_dup_token(tmp_path, capsys):
    drafts = wrap([token_student("S-AB12"), token_student("S-CD34")])
    rc, out = run_main(tmp_path, capsys, drafts)
    assert rc == 0
    assert "DUP_TOKEN" not in out


# ---------------------------------------------------------------------------
# ④ 실명 단계 stdout 비식별화
# ---------------------------------------------------------------------------

def test_named_stage_fail_stdout_has_no_sid(tmp_path, capsys):
    """FAIL 상황을 만들어도 stdout에 4자리 이상 숫자(학번)가 하나도 없어야 한다."""
    drafts = wrap([named_student("10101", "김가상")])
    roster = {"students": [{"학번": "10102", "이름": "이가상"}]}  # 초안 학번이 명렬에 없음
    rc, out = run_main(tmp_path, capsys, drafts, roster=roster)
    assert rc == 1
    assert "ROSTER" in out
    assert not SID_LIKE.search(out), out
    assert "김가상" not in out and "이가상" not in out


def test_named_stage_id_in_body_not_leaked(tmp_path, capsys):
    """본문에 학번이 남은 경우(ID_IN_BODY)에도 그 학번이 stdout에 다시 나가면 안 된다."""
    body = GOOD_TEXT.replace("인물의 갈등", "10101의 갈등")
    drafts = wrap([named_student("10101", "김가상", text=body)])
    roster = {"students": [{"학번": "10101", "이름": "김가상"}]}
    rc, out = run_main(tmp_path, capsys, drafts, roster=roster)
    assert rc == 1
    assert "ID_IN_BODY" in out
    assert not SID_LIKE.search(out), out


def test_named_stage_with_mapping_prints_token_rows(tmp_path, capsys):
    """--mapping이 있으면 행별 출력의 식별자가 학번→토큰으로 번역된다."""
    drafts = wrap([named_student("10101", "김거짓")])  # 명렬 이름과 불일치 → ROSTER FAIL
    roster = {"students": [{"학번": "10101", "이름": "김가상"},
                           {"학번": "10999", "이름": "이가상"}]}  # 10999는 미제출
    mapping = {"활동": "가상 활동", "map": {"10101": "S-AB12", "10999": "S-CD34"}}
    rc, out = run_main(tmp_path, capsys, drafts, roster=roster, mapping=mapping)
    assert rc == 1
    assert "FAIL 1반 S-AB12 [ROSTER]" in out
    assert "미제출 S-CD34" in out  # 미제출자도 토큰이 있으면 토큰으로 알린다
    assert not SID_LIKE.search(out), out
    assert "김가상" not in out and "김거짓" not in out


def test_named_stage_mapping_missing_sid_counts_as_fail(tmp_path, capsys):
    """매핑에 없는 학번은 행을 찍지 않고 건수 집계 + FAIL로 계산되어 저장이 막힌다."""
    drafts = wrap([named_student("10101", "김가상")])  # 검사 자체는 전부 통과하는 초안
    roster = {"students": [{"학번": "10101", "이름": "김가상"}]}
    mapping = {"활동": "가상 활동", "map": {"20202": "S-EE00"}}  # 초안 학번이 매핑에 없음
    rc, out = run_main(tmp_path, capsys, drafts, roster=roster, mapping=mapping)
    assert rc == 1
    assert "매핑에 없는 학번 1건" in out
    assert "결과: FAIL 1건" in out
    assert not SID_LIKE.search(out), out


def test_named_stage_without_mapping_prints_aggregate_only(tmp_path, capsys):
    """매핑이 없으면 거부하지 않되 행별 출력 대신 코드별 집계만 찍고 안내한다."""
    drafts = wrap([named_student("10101", "김가상")])
    roster = {"students": [{"학번": "10102", "이름": "이가상"}]}
    rc, out = run_main(tmp_path, capsys, drafts, roster=roster)
    assert rc == 1
    assert "FAIL ROSTER 1건" in out
    assert "[ROSTER]" not in out  # 행별 출력이 없어야 한다
    assert "--mapping" in out
    assert not SID_LIKE.search(out), out


def test_named_stage_summary_line_kept(tmp_path, capsys):
    """최종 집계 줄("결과: FAIL n건...")은 기존 형식을 유지한다."""
    drafts = wrap([named_student("10101", "김가상")])
    roster = {"students": [{"학번": "10101", "이름": "김가상"}]}
    rc, out = run_main(tmp_path, capsys, drafts, roster=roster)
    assert rc == 0
    assert re.search(r"결과: FAIL 0건, WARN \d+건, 미제출 0명", out), out


# ---------------------------------------------------------------------------
# ⑤ 함수 수준 — issue 메시지 문자열에 학번 보간이 없어야 한다
# ---------------------------------------------------------------------------

def test_dup_id_message_has_no_sid_interpolation():
    drafts = {"classes": [
        {"name": "1반", "students": [named_student("30101", "김가상", exempt=True)]},
        {"name": "2반", "students": [named_student("30101", "이가상", exempt=True)]},
    ]}
    report = V.verify_drafts(drafts, PROFILE)
    msgs = [msg for r in report["rows"] for _, code, msg in r["issues"] if code == "DUP_ID"]
    assert msgs, "DUP_ID가 발생해야 하는 시나리오"
    for msg in msgs:
        assert "같은 학번이 초안에 두 번 이상 등장" in msg
        assert "30101" not in msg


def test_all_issue_messages_have_no_sid():
    """대표 FAIL 경로(ROSTER·ID_IN_BODY·NOT_SUBMITTED 계열)의 메시지에 학번이 없다."""
    body = GOOD_TEXT.replace("인물의 갈등", "10101의 갈등")
    drafts = wrap([named_student("10101", "김허상", text=body),
                   named_student("10103", "박가상", exempt=True)])
    roster = {"students": [{"학번": "10101", "이름": "김가상"},
                           {"학번": "10103", "이름": "박가상"}]}
    report = V.verify_drafts(drafts, PROFILE, roster=roster,
                             submitted={"10103"})  # 10101은 제출 기록 없음
    for r in report["rows"]:
        for _, code, msg in r["issues"]:
            assert not SID_LIKE.search(msg), (code, msg)
