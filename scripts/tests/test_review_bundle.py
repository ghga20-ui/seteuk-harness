# -*- coding: utf-8 -*-
"""review-bundle CLI 테스트 — 검수를 브라우저로 옮기는 첫 조각.

핵심 계약: 산출 파일(검수번들.json)은 실명을 담아도 되지만(로컬 전용),
stdout에는 이름·학번이 절대 등장하면 안 된다. 에이전트는 stdout 집계만 읽는다.

전부 가상 인물이다.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parents[1] / "pseudonymize.py")
RULES_PATH = Path(__file__).resolve().parents[2] / "wiki" / "규칙.json"

NAMES = ["김가상", "이허구", "박미정", "최시늉", "한연습"]
IDS = ["10101", "10102", "10103", "10104", "10105"]


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


def _write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


MAPPING = {"활동": "시 비평하기", "map": {"10101": "S-1111", "10102": "S-2222"}}


def _basic_drafts():
    return {"classes": [{"name": "1반", "students": [
        {"학번": "10101", "이름": "김가상", "핵심소재": "진달래꽃(김소월)", "톤등급": "중",
         "세특": "시를 분석함.", "비고": "", "예외": False},
        {"학번": "10102", "이름": "이허구", "핵심소재": "", "톤등급": "상",
         "세특": "감상을 정리함.", "비고": "", "예외": False},
    ]}]}


# ---------------------------------------------------------------------------
# 정상 생성
# ---------------------------------------------------------------------------

def test_basic_bundle_counts_tokens_and_profile(tmp_path):
    drafts_path = _write(tmp_path / "초안.json", _basic_drafts())
    mapping_path = _write(tmp_path / "매핑.json", MAPPING)
    profile_path = _write(tmp_path / "활동프로파일.json",
                           {"활동명": "시 비평하기", "목표바이트": 700, "상한바이트": 760})
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--profile", str(profile_path), "--out", str(out))
    assert proc.returncode == 0
    assert out.exists()

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["활동명"] == "시 비평하기"
    assert saved["목표바이트"] == 700
    assert saved["상한바이트"] == 760
    assert len(saved["students"]) == 2

    by_id = {s["학번"]: s for s in saved["students"]}
    assert by_id["10101"]["토큰"] == "S-1111"
    assert by_id["10102"]["토큰"] == "S-2222"
    assert by_id["10101"]["핵심소재"] == "진달래꽃(김소월)"

    assert "검수번들: 2명" in proc.stdout
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)


def test_default_profile_used_when_missing(tmp_path):
    drafts_path = _write(tmp_path / "초안.json", _basic_drafts())
    mapping_path = _write(tmp_path / "매핑.json", MAPPING)
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["목표바이트"] == 700
    assert saved["상한바이트"] == 760


def test_last_stdout_line_warns_sensitive_output(tmp_path):
    drafts_path = _write(tmp_path / "초안.json", _basic_drafts())
    mapping_path = _write(tmp_path / "매핑.json", MAPPING)
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 0
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert "로컬" in lines[-1] or "민감" in lines[-1]


# ---------------------------------------------------------------------------
# --sources
# ---------------------------------------------------------------------------

def test_sources_included_and_tokens_reidentified_to_ids(tmp_path):
    drafts_path = _write(tmp_path / "초안.json", _basic_drafts())
    mapping_path = _write(tmp_path / "매핑.json", MAPPING)
    sources_path = _write(tmp_path / "토큰본.json", {"items": [
        {"토큰": "S-1111", "본문": "S-1111은 S-2222와 함께 활동함."},
        {"토큰": "S-2222", "본문": "S-2222 학생 단독으로 활동함."},
    ]})
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--sources", str(sources_path), "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    by_id = {s["학번"]: s for s in saved["students"]}
    assert by_id["10101"]["원문"] == "10101은 10102와 함께 활동함."
    assert by_id["10102"]["원문"] == "10102 학생 단독으로 활동함."
    assert "원문 포함 2명" in proc.stdout
    assert_no_pii(proc.stdout)


def test_without_sources_no_content_and_stdout_reflects_zero(tmp_path):
    drafts_path = _write(tmp_path / "초안.json", _basic_drafts())
    mapping_path = _write(tmp_path / "매핑.json", MAPPING)
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    for s in saved["students"]:
        assert not s.get("원문")
    assert "원문 포함 0명" in proc.stdout


# ---------------------------------------------------------------------------
# 우선검토 사유
# ---------------------------------------------------------------------------

def test_priority_review_reasons_cover_each_category(tmp_path):
    drafts = {"classes": [{"name": "1반", "students": [
        {"학번": "10101", "이름": "김가상", "핵심소재": "가상 작품A", "톤등급": "중",
         "세특": "정상 분량의 세특 본문임.", "비고": "", "예외": False},
        {"학번": "10102", "이름": "이허구", "핵심소재": "가상 작품B", "톤등급": "중",
         "세특": "예외 처리된 학생임.", "비고": "", "예외": True},
        {"학번": "10103", "이름": "박미정", "핵심소재": "가상 작품C", "톤등급": "중",
         "세특": "톤 조정이 필요해 보임.", "비고": "검토 필요", "예외": False},
        # 상한 100바이트의 95%(95바이트) 이상 — '가'(3바이트) x 32 = 96바이트
        {"학번": "10104", "이름": "최시늉", "핵심소재": "가상 작품D", "톤등급": "중",
         "세특": "가" * 32, "비고": "", "예외": False},
        # 목표 50바이트의 60%(30바이트) 이하
        {"학번": "10105", "이름": "한연습", "핵심소재": "가상 작품E", "톤등급": "중",
         "세특": "짧음", "비고": "", "예외": False},
    ]}]}
    drafts_path = _write(tmp_path / "초안.json", drafts)
    # 10105는 일부러 매핑에서 제외해 "매핑에 토큰 없음" 사유도 함께 검증한다.
    mapping = {"활동": "시 비평하기", "map": {
        "10101": "S-1111", "10102": "S-2222", "10103": "S-3333", "10104": "S-4444",
    }}
    mapping_path = _write(tmp_path / "매핑.json", mapping)
    profile_path = _write(tmp_path / "활동프로파일.json",
                           {"활동명": "시 비평하기", "목표바이트": 50, "상한바이트": 100})
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--profile", str(profile_path), "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    by_id = {s["학번"]: s for s in saved["students"]}

    assert by_id["10101"]["우선검토"] == []
    assert "예외 학생" in by_id["10102"]["우선검토"]
    assert any("검토 필요" in r for r in by_id["10103"]["우선검토"])
    assert any("상한" in r for r in by_id["10104"]["우선검토"])
    assert any("부족" in r or "미달" in r for r in by_id["10105"]["우선검토"])
    assert any("토큰" in r for r in by_id["10105"]["우선검토"])
    assert by_id["10105"]["토큰"] is None

    assert "우선 검토 4명" in proc.stdout
    assert_no_pii(proc.stdout)


def test_bigo_keywords_추정_교정_확인_also_trigger_review(tmp_path):
    drafts = {"classes": [{"name": "1반", "students": [
        {"학번": "10101", "이름": "김가상", "핵심소재": "가상 작품A", "톤등급": "중",
         "세특": "본문.", "비고": "전사 추정", "예외": False},
        {"학번": "10102", "이름": "이허구", "핵심소재": "가상 작품B", "톤등급": "중",
         "세특": "본문.", "비고": "소재 교정함", "예외": False},
        {"학번": "10103", "이름": "박미정", "핵심소재": "가상 작품C", "톤등급": "중",
         "세특": "본문.", "비고": "톤 확인 요망", "예외": False},
    ]}]}
    drafts_path = _write(tmp_path / "초안.json", drafts)
    mapping = {"map": {"10101": "S-1111", "10102": "S-2222", "10103": "S-3333"}}
    mapping_path = _write(tmp_path / "매핑.json", mapping)
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    by_id = {s["학번"]: s for s in saved["students"]}
    assert by_id["10101"]["우선검토"]
    assert by_id["10102"]["우선검토"]
    assert by_id["10103"]["우선검토"]


# ---------------------------------------------------------------------------
# 매핑에 없는 학번(미제출자 등)도 제외하지 않는다
# ---------------------------------------------------------------------------

def test_unmapped_student_kept_with_null_token(tmp_path):
    drafts = {"classes": [{"name": "1반", "students": [
        {"학번": "10101", "이름": "김가상", "핵심소재": "가상 작품", "톤등급": "중",
         "세특": "미제출로 예외 처리됨.", "비고": "미제출", "예외": True},
    ]}]}
    drafts_path = _write(tmp_path / "초안.json", drafts)
    mapping_path = _write(tmp_path / "매핑.json", {"map": {}})
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["students"]) == 1
    assert saved["students"][0]["토큰"] is None
    assert saved["students"][0]["우선검토"]


# ---------------------------------------------------------------------------
# 금지어·금지문자는 wiki/규칙.json에서 읽어 싣는다
# ---------------------------------------------------------------------------

def test_banned_words_and_chars_loaded_from_rules_file(tmp_path):
    drafts_path = _write(tmp_path / "초안.json", _basic_drafts())
    mapping_path = _write(tmp_path / "매핑.json", MAPPING)
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))

    rules = json.loads(RULES_PATH.read_text(encoding="utf-8-sig"))
    for word in rules["금지어휘"]:
        assert word in saved["금지어"]
    if rules.get("이는_경계검사"):
        assert "이는" in saved["금지어"]
    assert saved["금지문자패턴"] == rules["금지문자패턴"]
    # 패턴은 정규식이어야 한다 — 문자 목록으로 실으면 소비자 검사가 무력해진다
    import re as _re
    assert _re.search(saved["금지문자패턴"], '그는 "말했다" · 그리고 ①')


# ---------------------------------------------------------------------------
# stdout 계약 — 이름·학번 절대 없음
# ---------------------------------------------------------------------------

def test_stdout_never_contains_names_or_ids(tmp_path):
    drafts = {"classes": [{"name": "1반", "students": [
        {"학번": sid, "이름": name, "핵심소재": "가상 작품", "톤등급": "중",
         "세특": "본문.", "비고": "", "예외": False}
        for sid, name in zip(IDS, NAMES)
    ]}]}
    drafts_path = _write(tmp_path / "초안.json", drafts)
    mapping_path = _write(tmp_path / "매핑.json",
                           {"map": {sid: f"S-{i:04X}" for i, sid in enumerate(IDS)}})
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 0
    assert_no_pii(proc.stdout)
    assert_no_pii(proc.stderr)


# ---------------------------------------------------------------------------
# 빈 초안 / 학생 0명 -> exit 1
# ---------------------------------------------------------------------------

def test_empty_drafts_file_fails(tmp_path):
    drafts_path = tmp_path / "초안.json"
    drafts_path.write_text("", encoding="utf-8")
    mapping_path = _write(tmp_path / "매핑.json", {"map": {}})
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert_no_pii(proc.stdout)


def test_zero_students_fails(tmp_path):
    drafts_path = _write(tmp_path / "초안.json", {"classes": [{"name": "1반", "students": []}]})
    mapping_path = _write(tmp_path / "매핑.json", {"map": {}})
    out = tmp_path / "검수번들.json"

    proc = run("review-bundle", "--drafts", str(drafts_path), "--mapping", str(mapping_path),
               "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert "학생이 없습니다" in proc.stdout
