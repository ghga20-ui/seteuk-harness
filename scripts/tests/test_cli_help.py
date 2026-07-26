# -*- coding: utf-8 -*-
"""모든 서브커맨드의 --help가 크래시 없이 뜨는지 확인한다.

argparse는 help 문자열의 `%`를 포맷 지시자로 해석한다. 실측 수치를 설명에
적으면서 '54.1%'를 그대로 넣었더니 `score --help`가 통째로 죽었다 —
테스트가 없으면 사용자가 도움말을 열어 보기 전까지 아무도 모른다.
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]

CLIS = {
    "pseudonymize.py": [
        "roster", "issue", "mask", "memo", "score", "finalize", "review-bundle", "destroy",
    ],
    "verify_seteuk.py": [],
    "extract_sources.py": [],
}

# CLI가 없는 라이브러리 모듈. 손글씨 이미지 마스킹은 아직 함수 직접 호출이라
# "민감 처리는 CLI로만 한다"는 불변 원칙 밖에 있다 — 첫 이미지 활동 전에
# CLI로 올리거나 원칙에서 예외임을 명시해야 한다.
LIBRARY_ONLY = ["mask_images.py"]


def _run(*args):
    return subprocess.run([sys.executable, *args],
                          capture_output=True, text=True, encoding="utf-8")


def test_top_level_help_works():
    for script in CLIS:
        proc = _run(str(SCRIPTS / script), "--help")
        assert proc.returncode == 0, f"{script} --help 실패: {proc.stderr[:300]}"
        assert proc.stdout.strip(), f"{script} --help 출력 없음"


def test_library_only_modules_have_no_cli():
    """CLI가 생기면 위 목록으로 옮기고 도움말 검사를 받게 해야 한다."""
    for script in LIBRARY_ONLY:
        src = (SCRIPTS / script).read_text(encoding="utf-8")
        assert "argparse" not in src, f"{script}에 CLI가 생겼다 — CLIS로 옮겨라"


def test_every_subcommand_help_works():
    script = str(SCRIPTS / "pseudonymize.py")
    known = set(CLIS["pseudonymize.py"])
    top = _run(script, "--help").stdout
    for sub in sorted(known):
        # 등록되지 않은 이름을 테스트가 조용히 통과시키지 않도록 먼저 확인한다.
        assert sub in top, f"'{sub}' 서브커맨드가 --help 목록에 없다(이름 변경?)"
        proc = _run(script, sub, "--help")
        assert proc.returncode == 0, f"{sub} --help 실패: {proc.stderr[:300]}"
        assert proc.stdout.strip(), f"{sub} --help 출력 없음"
