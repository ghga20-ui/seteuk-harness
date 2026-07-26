# -*- coding: utf-8 -*-
"""파기(destroy) CLI 테스트.

파기는 스킬의 불변 원칙 중 하나인데 CLI 명령이 없어 파이썬 함수를 직접
호출해야 했다 — "명렬·매핑표는 CLI로만 다룬다"는 원칙과 정면으로 어긋났고,
안내 문서에는 존재하지 않는 `pseudonymize.py destroy`가 적혀 있었다.
되돌릴 수 없는 동작이므로 기본은 목록만 보여주고, 실제 삭제는 --yes를 요구한다.
"""
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parents[1] / "pseudonymize.py")


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, "destroy", *args],
                          capture_output=True, text=True, encoding="utf-8")


def _seed(tmp_path):
    """민감 산출물과 무관한 파일을 함께 놓는다."""
    names = ["매핑.json", "명렬.json", "관찰메모.json", "점수.json",
             "점수원본.json", "제출자.json", "토큰본.json"]
    for n in names:
        (tmp_path / n).write_text('{"x":1}', encoding="utf-8")
    (tmp_path / "세특초안.xlsx").write_bytes(b"keep me")
    (tmp_path / "활동프로파일.json").write_text("{}", encoding="utf-8")
    return names


def test_dry_run_lists_without_deleting(tmp_path):
    names = _seed(tmp_path)
    proc = _run("--dir", str(tmp_path))
    assert proc.returncode == 0
    for n in names:
        assert (tmp_path / n).exists(), f"{n}이 --yes 없이 지워졌다"
        assert n in proc.stdout
    assert "--yes" in proc.stdout


def test_yes_actually_destroys(tmp_path):
    names = _seed(tmp_path)
    proc = _run("--dir", str(tmp_path), "--yes")
    assert proc.returncode == 0
    for n in names:
        assert not (tmp_path / n).exists(), f"{n}이 남아 있다"
    assert "7" in proc.stdout


def test_unrelated_files_are_kept(tmp_path):
    _seed(tmp_path)
    _run("--dir", str(tmp_path), "--yes")
    assert (tmp_path / "세특초안.xlsx").exists()
    assert (tmp_path / "활동프로파일.json").exists()


def test_nothing_to_destroy_is_reported(tmp_path):
    proc = _run("--dir", str(tmp_path), "--yes")
    assert proc.returncode == 0
    assert "없" in proc.stdout


def test_stdout_has_no_file_contents(tmp_path):
    """파일명은 보여도 내용(실명·학번)은 절대 나오면 안 된다."""
    (tmp_path / "명렬.json").write_text(
        '{"students":[{"학번":"39999","이름":"가상비밀"}]}', encoding="utf-8")
    for args in ([], ["--yes"]):
        proc = _run("--dir", str(tmp_path), *args)
        assert "가상비밀" not in proc.stdout
        assert "39999" not in proc.stdout


def test_submitted_and_score_source_are_covered(tmp_path):
    """붙여넣기 페이지가 만드는 제출자·점수원본도 파기 대상이어야 한다."""
    (tmp_path / "제출자.json").write_text("{}", encoding="utf-8")
    (tmp_path / "점수원본.json").write_text("{}", encoding="utf-8")
    _run("--dir", str(tmp_path), "--yes")
    assert not (tmp_path / "제출자.json").exists()
    assert not (tmp_path / "점수원본.json").exists()
