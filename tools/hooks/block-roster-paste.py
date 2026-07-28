# -*- coding: utf-8 -*-
"""UserPromptSubmit 훅 — 대화창에 붙여넣은 학생 명단을 제출 전에 차단한다.

왜 있는가: 하네스가 명단을 파일로만 받도록 안내해도, 비상구(클립보드) 사용
순간의 근육기억 Ctrl+V 한 번이면 실명 수십 명이 대화로 들어간다. 대화에
들어간 실명은 사후 복구가 불가능하므로(전송이 곧 끝), 제출 직전이 마지막
방어선이다(입력방식-결론 §4).

감지 규칙(오탐 방지 포함):
- 같은 줄에 5자리 학번(앞뒤에 다른 숫자가 붙지 않는)과 그 옆 칸의 순수
  한글 2~4자 토큰이 붙어 있는 줄을 명단 행으로 본다. 순번·점수 열이
  끼어 있어도 잡고, 이름이 학번보다 앞에 와도 잡는다.
- 그런 줄이 3줄 이상이고, 서로 다른 학번이 3개 이상이며, 한글 토큰이
  2종 이상일 때만 차단한다 — "30101 바이트 초과"가 반복되는 용량 목록,
  같은 학번의 반복, 문장 속에 우연히 든 5자리 수는 여기서 걸러진다.
- 학번만 있는 목록(이름 없음)은 차단하지 않는다 — 제출자 학번 목록은
  정상 흐름이다.

차단 방식: stdout에 {"decision": "block", "reason": ...} JSON을 내고 exit 0
(Claude Code UserPromptSubmit 규약). 사유에는 입력된 이름·학번을 절대
되울리지 않는다. stdin이 JSON이 아니거나 읽기에 실패하면 조용히 통과시킨다
(fail-open) — 이 훅은 최후 그물이지 관문이 아니고, 훅 오류로 정상 대화까지
막으면 사용자가 훅 자체를 꺼 버린다.

설치(권장·선택): settings.json의 hooks.UserPromptSubmit에 이 스크립트를
command로 등록한다. 등록은 사용자 승인 하에만 한다 — SKILL.md 실행 전
점검 절 참조.
"""
import json
import re
import sys

# 5자리 학번: 앞뒤로 숫자가 더 붙으면 학번이 아니다(연도 접두 등).
_ID = r"(?<!\d)\d{5}(?!\d)"
# 순수 한글 2~4자 토큰: 앞뒤로 한글이 더 붙으면 이름 토큰이 아니다.
_NAME = r"(?<![가-힣])[가-힣]{2,4}(?![가-힣])"
# 칸 구분: 탭·쉼표·세로줄·공백. 사이에 짧은 토큰(순번·반 표기 등)이
# 최대 2개까지 끼는 것을 허용한다 — 엑셀 표는 열이 붙어 오지 않는 일이 많다.
_SEP = r"[ \t,;|]+"
_FILLER = r"(?:[0-9가-힣.\-]{1,5}" + _SEP + r"){0,2}"

_ID_THEN_NAME = re.compile("(" + _ID + ")" + _SEP + _FILLER + "(" + _NAME + ")")
_NAME_THEN_ID = re.compile("(" + _NAME + ")" + _SEP + _FILLER + "(" + _ID + ")")

REASON = (
    "입력에 학생 명단(학번과 이름)이 보여 전송을 멈췄습니다. "
    "이 창에 붙여넣으면 실명이 AI로 전송되고 되돌릴 수 없습니다. "
    "명단은 파일로 활동 폴더에 넣고, 대화에는 파일 이름만 말씀해 주세요."
)


def _roster_line_hit(line: str):
    """줄에서 (학번, 이름) 한 쌍을 찾는다. 없으면 None."""
    m = _ID_THEN_NAME.search(line)
    if m:
        return (m.group(1), m.group(2))
    m = _NAME_THEN_ID.search(line)
    if m:
        return (m.group(2), m.group(1))
    return None


def looks_like_roster(prompt: str) -> bool:
    ids = set()
    names = set()
    hit_lines = 0
    for line in prompt.splitlines():
        hit = _roster_line_hit(line)
        if hit is None:
            continue
        hit_lines += 1
        ids.add(hit[0])
        names.add(hit[1])
    return hit_lines >= 3 and len(ids) >= 3 and len(names) >= 2


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        prompt = payload.get("prompt", "")
        if not isinstance(prompt, str):
            return 0
    except Exception:
        return 0  # 훅 오류로 정상 대화를 막지 않는다(fail-open)

    if looks_like_roster(prompt):
        out = json.dumps({"decision": "block", "reason": REASON}, ensure_ascii=False)
        sys.stdout.buffer.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
