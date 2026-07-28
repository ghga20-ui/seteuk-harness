# -*- coding: utf-8 -*-
"""UserPromptSubmit 훅(block-roster-paste.py) 테스트 — 전부 가상 인물.

훅은 subprocess로 호출한다(실사용과 같은 경계). 계약:
- stdin으로 {"prompt": "..."} JSON을 받는다.
- 명단 패턴(같은 줄에 5자리 학번 + 한글 2~4자 이름, 3줄 이상·서로 다른
  학번 3개 이상)을 감지하면 stdout에 {"decision":"block","reason":...}를
  내고 exit 0.
- 그 외에는 아무것도 출력하지 않고 exit 0(통과).
- 차단 사유(reason)에 입력된 이름·학번을 되울리지 않는다.
- stdin이 JSON이 아니거나 prompt가 없어도 죽지 않고 통과시킨다(fail-open —
  훅은 최후 그물이지 관문이 아니다).
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "tools" / "hooks" / "block-roster-paste.py"


def run_hook(stdin_bytes: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_bytes,
        capture_output=True,
        timeout=30,
    )


def run_prompt(prompt: str) -> subprocess.CompletedProcess:
    return run_hook(json.dumps({"prompt": prompt}).encode("utf-8"))


def decision_of(proc: subprocess.CompletedProcess):
    out = proc.stdout.decode("utf-8").strip()
    if not out:
        return None
    return json.loads(out)


# ── 차단해야 하는 입력 ─────────────────────────────────────────────


def test_탭_구분_명단_차단():
    proc = run_prompt("30101\t김가상\n30102\t이허구\n30103\t박모의\n30104\t최견본")
    assert proc.returncode == 0
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"
    assert data["reason"].strip()


def test_공백_구분_명단_차단():
    proc = run_prompt("30101 김가상\n30102 이허구\n30103 박모의")
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"


def test_쉼표_구분_명단_차단():
    proc = run_prompt("30101, 김가상\n30102, 이허구\n30103, 박모의")
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"


def test_이름이_앞에_와도_차단():
    proc = run_prompt("김가상 30101\n이허구 30102\n박모의 30103")
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"


def test_순번_열이_있어도_차단():
    proc = run_prompt("1\t30101\t김가상\n2\t30102\t이허구\n3\t30103\t박모의")
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"


def test_점수_열이_있어도_차단():
    proc = run_prompt("30101\t김가상\t15\n30102\t이허구\t13\n30103\t박모의\t14")
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"


def test_명단_앞뒤에_말이_붙어도_차단():
    proc = run_prompt(
        "이 학생들 세특 좀 써 줘\n30101\t김가상\n30102\t이허구\n30103\t박모의\n고마워"
    )
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"


def test_차단_사유에_이름과_학번을_되울리지_않는다():
    proc = run_prompt("30101\t김가상\n30102\t이허구\n30103\t박모의")
    data = decision_of(proc)
    assert data is not None and data["decision"] == "block"
    for secret in ("김가상", "이허구", "박모의", "30101", "30102", "30103"):
        assert secret not in data["reason"]
    # stderr에도 없어야 한다
    err = proc.stderr.decode("utf-8", errors="replace")
    for secret in ("김가상", "이허구", "박모의"):
        assert secret not in err


# ── 통과해야 하는 입력 (오탐 방지) ────────────────────────────────


def assert_allowed(proc: subprocess.CompletedProcess):
    assert proc.returncode == 0
    assert proc.stdout.decode("utf-8").strip() == ""


def test_두_줄이면_통과():
    # 3줄 미만은 명단으로 단정하지 않는다
    assert_allowed(run_prompt("30101\t김가상\n30102\t이허구"))


def test_같은_학번_반복은_통과():
    # 서로 다른 학번이 3개 미만이면 명단이 아니다
    assert_allowed(run_prompt("30101 김가상\n30101 김가상\n30101 김가상"))


def test_같은_단어_반복은_통과():
    # 학번처럼 보이는 숫자 + 같은 일반명사 반복(용량 목록 등)은 명단이 아니다
    assert_allowed(run_prompt("30101 바이트 초과\n30245 바이트 초과\n31007 바이트 초과"))


def test_일반_문장은_통과():
    assert_allowed(run_prompt("결과 파일이 30101 바이트를 넘었는데 어떻게 줄일까?"))


def test_학번만_있는_목록은_통과():
    # 학번만으로는 실명 유출이 아니다(제출자 목록 등 정상 흐름)
    assert_allowed(run_prompt("30101\n30102\n30103\n30104"))


def test_긴_숫자는_학번이_아니다():
    assert_allowed(run_prompt("202630101 김가상\n202630102 이허구\n202630103 박모의"))


def test_빈_프롬프트_통과():
    assert_allowed(run_prompt(""))


def test_프롬프트_키_없음_통과():
    assert_allowed(run_hook(b"{}"))


def test_JSON_아님_통과():
    assert_allowed(run_hook(b"this is not json"))


def test_빈_stdin_통과():
    assert_allowed(run_hook(b""))
