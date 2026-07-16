# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_seteuk import check_text, load_rules, verify_drafts

PROFILE = {"활동명": "가상 활동", "문두": "가상 활동에서", "목표바이트": 700, "상한바이트": 760}


def codes(issues):
    return [(lv, code) for lv, code, _ in issues]


def test_default_rules_file_exists_and_loads():
    rules = load_rules()
    assert "또한" in rules["금지어휘"]
    assert "금지문자패턴" in rules
    assert rules["금지문자패턴"].startswith("[")


def test_load_rules_falls_back_when_missing(tmp_path):
    rules = load_rules(tmp_path / "없는파일.json")
    assert "또한" in rules["금지어휘"]


def test_check_text_respects_custom_rules(tmp_path):
    custom = tmp_path / "규칙.json"
    custom.write_text(
        json.dumps({"금지어휘": ["또한", "가상금지어"]}, ensure_ascii=False), encoding="utf-8"
    )
    rules = load_rules(custom)
    text = "가상 활동에서 가상금지어를 포함하여 정리함."
    _, issues = check_text(text, PROFILE, exempt=True, rules=rules)
    assert ("FAIL", "BANNED_WORD") in codes(issues)
    _, issues_default = check_text(text, PROFILE, exempt=True)
    assert ("FAIL", "BANNED_WORD") not in codes(issues_default)


def _drafts_one(sid="10101", name="김가상"):
    return {
        "classes": [
            {
                "name": "1반",
                "students": [
                    {"학번": sid, "이름": name, "핵심소재": "", "톤등급": "하",
                     "세특": "가상 활동에 참여함.", "비고": "", "예외": True}
                ],
            }
        ]
    }


ROSTER = {"students": [{"학번": "10101", "이름": "김가상"}, {"학번": "10102", "이름": "이허구"}]}


def test_roster_reports_missing_students():
    report = verify_drafts(_drafts_one(), PROFILE, roster=ROSTER)
    assert {"학번": "10102", "이름": "이허구"} in report["미제출"]


def test_roster_unknown_student_fails():
    report = verify_drafts(_drafts_one(sid="10999"), PROFILE, roster=ROSTER)
    assert report["fail"] >= 1
    assert any(code == "ROSTER" for r in report["rows"] for _, code, _ in r["issues"])


def test_roster_name_mismatch_fails():
    report = verify_drafts(_drafts_one(name="김허상"), PROFILE, roster=ROSTER)
    assert any(code == "ROSTER" for r in report["rows"] for _, code, _ in r["issues"])


def test_no_roster_keeps_previous_behavior():
    report = verify_drafts(_drafts_one(), PROFILE)
    assert report["fail"] == 0
    assert report.get("미제출") in (None, [])
