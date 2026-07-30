# -*- coding: utf-8 -*-
"""민감 산출물 파일 권한(0o600) 테스트 — 전부 가상 인물이다.

명렬·매핑표·확인.html·검수.html은 같은 컴퓨터의 다른 계정이 읽으면 안 된다.
기본 open(..., "w")은 POSIX에서 umask 기본값 기준 0644가 되므로,
_open_private가 생성 순간부터 0o600을 주는지, 그리고 _write_json의 원자적
쓰기 구조(임시 파일 → fsync → os.replace)가 권한을 유지한 채 그대로
살아 있는지를 확인한다.

mode 비트 검증은 POSIX에서만 의미가 있어 skipif로 감싼다 — Windows는 mode를
무시하고 사용자 프로필 폴더의 ACL이 계정별 보호를 맡는다. 이 저장소에 곧
ubuntu CI가 붙을 예정이라 POSIX assert는 CI에서 실효된다. Windows에서도
파일 생성·내용 무결성·os.replace 원자성(기존 파일 덮어쓰기)은 그대로
검증한다.
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pseudonymize

SCRIPT = str(Path(__file__).resolve().parents[1] / "pseudonymize.py")
REVIEW_SCRIPT = str(Path(__file__).resolve().parents[1] / "make_review_html.py")

posix_only = pytest.mark.skipif(
    os.name != "posix", reason="파일 mode 비트는 POSIX에서만 의미가 있다")

ROSTER = {"students": [
    {"학번": "10101", "이름": "김가상", "반": "1반"},
    {"학번": "10102", "이름": "이허구", "반": "1반"},
]}


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


# ---------------------------------------------------------------------------
# _open_private — 헬퍼 단독
# ---------------------------------------------------------------------------

def test_open_private_writes_utf8_content(tmp_path):
    p = tmp_path / "매핑.json"
    with pseudonymize._open_private(p) as f:
        f.write('{"이름": "김가상"}')
    assert p.read_text(encoding="utf-8") == '{"이름": "김가상"}'


def test_open_private_truncates_existing(tmp_path):
    """O_TRUNC — 기존 내용이 길어도 잔여 바이트가 남으면 안 된다."""
    p = tmp_path / "명렬.json"
    p.write_text("긴 옛날 내용 " * 100, encoding="utf-8")
    with pseudonymize._open_private(p) as f:
        f.write("짧음")
    assert p.read_text(encoding="utf-8") == "짧음"


@posix_only
def test_open_private_mode_is_0600(tmp_path):
    p = tmp_path / "매핑.json"
    with pseudonymize._open_private(p) as f:
        f.write("{}")
    assert _mode(p) == 0o600


# ---------------------------------------------------------------------------
# _write_json — 원자적 쓰기 구조가 권한 적용 후에도 살아 있어야 한다
# ---------------------------------------------------------------------------

def test_write_json_roundtrip_and_no_tmp_left(tmp_path):
    p = tmp_path / "명렬.json"
    pseudonymize._write_json(ROSTER, p)
    assert json.loads(p.read_text(encoding="utf-8")) == ROSTER
    assert not (tmp_path / "명렬.json.tmp").exists()


def test_write_json_overwrites_existing_atomically(tmp_path):
    """os.replace 원자성 — 기존 파일을 덮어써도 내용은 전부 새것이어야 한다."""
    p = tmp_path / "매핑.json"
    p.write_text('{"map": {"10101": "S-옛날토큰"}}', encoding="utf-8")
    new = {"map": {"10101": "S-1111", "10102": "S-2222"}}
    pseudonymize._write_json(new, p)
    assert json.loads(p.read_text(encoding="utf-8")) == new
    assert "옛날토큰" not in p.read_text(encoding="utf-8")
    assert not (tmp_path / "매핑.json.tmp").exists()


@posix_only
def test_write_json_mode_is_0600(tmp_path):
    p = tmp_path / "명렬.json"
    pseudonymize._write_json(ROSTER, p)
    assert _mode(p) == 0o600


@posix_only
def test_write_json_narrows_pre_existing_0644(tmp_path):
    """예전 버전이 0644로 남긴 파일도 다시 쓰는 순간 0600으로 좁혀져야 한다.

    os.replace는 임시 파일의 권한을 그대로 넘기므로 원본의 낡은 권한은
    살아남지 못한다 — 그 계약을 여기서 못 박는다.
    """
    p = tmp_path / "매핑.json"
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o644)
    pseudonymize._write_json({"map": {}}, p)
    assert _mode(p) == 0o600


# ---------------------------------------------------------------------------
# CLI — 확인.html(실명)·검수.html(실명)도 같은 그물에 걸려야 한다
# ---------------------------------------------------------------------------

def _run_confirm(tmp_path) -> Path:
    roster_path = tmp_path / "명렬.json"
    roster_path.write_text(json.dumps(ROSTER, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "확인.html"
    proc = subprocess.run(
        [sys.executable, SCRIPT, "confirm-html",
         "--roster", str(roster_path), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def _run_review(tmp_path) -> Path:
    bundle = {
        "활동명": "시 비평하기", "목표바이트": 700, "상한바이트": 760,
        "students": [
            {"토큰": "S-1111", "학번": "10101", "이름": "김가상", "반": "1반",
             "세특": "시를 분석함.", "원문": "화자를 살펴보았다.", "우선검토": []},
        ],
    }
    bundle_path = tmp_path / "검수번들.json"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "검수.html"
    proc = subprocess.run(
        [sys.executable, REVIEW_SCRIPT, str(bundle_path), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def test_confirm_html_is_created_with_names(tmp_path):
    out = _run_confirm(tmp_path)
    html = out.read_text(encoding="utf-8")
    assert "김가상" in html and "이허구" in html


@posix_only
def test_confirm_html_mode_is_0600(tmp_path):
    out = _run_confirm(tmp_path)
    assert _mode(out) == 0o600


def test_review_html_is_created_with_names(tmp_path):
    out = _run_review(tmp_path)
    assert "김가상" in out.read_text(encoding="utf-8")


@posix_only
def test_review_html_mode_is_0600(tmp_path):
    out = _run_review(tmp_path)
    assert _mode(out) == 0o600
