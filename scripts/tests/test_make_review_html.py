# -*- coding: utf-8 -*-
"""make_review_html CLI 테스트 — 검수번들.json을 검수템플릿.html에 심어 검수.html을 만든다.

핵심 계약:
- 산출 파일(검수.html)은 실명을 담아도 되지만(로컬 전용), stdout에는 이름이 절대 없다.
- 학생 글에 </script>가 있어도 화면이 깨지지 않도록 < 를 \\u003c 로 이스케이프한다.
- 템플릿을 못 찾거나 번들이 비면 exit 1과 사유를 낸다.

전부 가상 인물이다.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parents[1] / "make_review_html.py")
TEMPLATE = Path(__file__).resolve().parents[2] / "tools" / "검수템플릿.html"

NAMES = ["김가상", "이허구", "박미정"]
IDS = ["10101", "10102", "10103"]


def run(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def assert_no_names(text):
    for name in NAMES:
        assert name not in text


def _bundle():
    return {
        "활동명": "시 비평하기",
        "목표바이트": 700, "상한바이트": 760,
        "금지어": ["넘어"], "금지문자패턴": "[\"']",
        "students": [
            {"토큰": "S-1111", "학번": "10101", "이름": "김가상", "반": "1반",
             "톤등급": "중", "핵심소재": "진달래꽃(김소월)",
             "세특": "시를 분석함.", "비고": "", "예외": False,
             "원문": "시의 화자를 분석해 보았다.", "우선검토": [],
             "짝": [{"n": 1, "세특": "시를 분석함", "원문": "화자를 분석해"}]},
            {"토큰": "S-2222", "학번": "10102", "이름": "이허구", "반": "1반",
             "톤등급": "상", "핵심소재": "",
             "세특": "감상을 정리함.", "비고": "", "예외": False,
             "원문": "감상을 적었다.", "우선검토": ["분량 미달"]},
        ],
    }


def _write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def _payload_of(html: str) -> str:
    """생성 파일에서 심은 JSON 블록만 꺼낸다."""
    marker = 'id="검수데이터">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    return html[start:end]


# ---------------------------------------------------------------------------
# 정상 생성
# ---------------------------------------------------------------------------

def test_generates_html_with_embedded_data(tmp_path):
    bundle_path = _write(tmp_path / "검수번들.json", _bundle())
    out = tmp_path / "검수.html"

    proc = run(str(bundle_path), "--out", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()

    html = out.read_text(encoding="utf-8")
    assert "__검수데이터__" not in html          # 플레이스홀더가 치환됐다
    payload = _payload_of(html)
    data = json.loads(payload)
    assert len(data["students"]) == 2
    assert data["students"][0]["이름"] == "김가상"   # 파일 안에는 실명이 있어야 한다(로컬 전용)
    assert data["활동명"] == "시 비평하기"


def test_script_close_tag_escaped_and_roundtrips(tmp_path):
    bundle = _bundle()
    tricky = "학생이 이렇게 썼다면: </script><h1>깨짐</h1> 그리고 2<3."
    bundle["students"][0]["원문"] = tricky
    bundle_path = _write(tmp_path / "검수번들.json", bundle)
    out = tmp_path / "검수.html"

    proc = run(str(bundle_path), "--out", str(out))
    assert proc.returncode == 0
    html = out.read_text(encoding="utf-8")
    payload = _payload_of(html)
    # 심은 블록 안에는 꺾쇠가 한 개도 없어야 한다 — 있으면 스크립트가 그 자리에서 끊긴다.
    assert "<" not in payload
    assert "\\u003c" in payload
    # 왕복: 파싱하면 원문이 글자 그대로 돌아온다.
    data = json.loads(payload)
    assert data["students"][0]["원문"] == tricky


# ---------------------------------------------------------------------------
# stdout 계약 — 집계만, 이름 없음, 안내 두 문장
# ---------------------------------------------------------------------------

def test_stdout_has_counts_notice_and_no_names(tmp_path):
    bundle_path = _write(tmp_path / "검수번들.json", _bundle())
    out = tmp_path / "검수.html"

    proc = run(str(bundle_path), "--out", str(out))
    assert proc.returncode == 0
    assert_no_names(proc.stdout)
    assert_no_names(proc.stderr)
    assert "2명" in proc.stdout
    assert "이 파일에는 실명이 들어 있습니다 — 활동 폴더에만 두세요" in proc.stdout
    assert "창을 닫으면 고치던 내용이 사라집니다. 저장 단추를 눌러야 파일로 남습니다" in proc.stdout


# ---------------------------------------------------------------------------
# exit 1 — 템플릿 없음 / 번들 없음·빈 파일·깨진 JSON / 학생 0명
# ---------------------------------------------------------------------------

def test_missing_template_fails(tmp_path):
    bundle_path = _write(tmp_path / "검수번들.json", _bundle())
    out = tmp_path / "검수.html"
    proc = run(str(bundle_path), "--out", str(out),
               "--template", str(tmp_path / "없는템플릿.html"))
    assert proc.returncode == 1
    assert not out.exists()
    assert "템플릿" in proc.stdout


def test_missing_bundle_fails(tmp_path):
    out = tmp_path / "검수.html"
    proc = run(str(tmp_path / "없는번들.json"), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert "읽지 못했습니다" in proc.stdout


def test_empty_bundle_file_fails(tmp_path):
    bundle_path = tmp_path / "검수번들.json"
    bundle_path.write_text("", encoding="utf-8")
    out = tmp_path / "검수.html"
    proc = run(str(bundle_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()


def test_broken_json_fails(tmp_path):
    bundle_path = tmp_path / "검수번들.json"
    bundle_path.write_text("{깨진 json", encoding="utf-8")
    out = tmp_path / "검수.html"
    proc = run(str(bundle_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()


def test_zero_students_fails(tmp_path):
    bundle = _bundle()
    bundle["students"] = []
    bundle_path = _write(tmp_path / "검수번들.json", bundle)
    out = tmp_path / "검수.html"
    proc = run(str(bundle_path), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()
    assert "학생이 없습니다" in proc.stdout


# ---------------------------------------------------------------------------
# 템플릿 자체 계약 — 생성기가 기대는 형태가 유지되는가
# ---------------------------------------------------------------------------

def test_template_exists_and_has_placeholder():
    assert TEMPLATE.exists()
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<script type="application/json" id="검수데이터">__검수데이터__</script>' in html
