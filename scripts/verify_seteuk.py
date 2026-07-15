#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seteuk-harness 결정론 채점기 + 저장 게이트.

wiki/규칙정본.md의 기계 검사 가능 규칙을 코드로 강제한다.
규칙정본이 개정되면 이 파일의 상수도 함께 개정한다.
"""
from __future__ import annotations

import re

# 규칙정본 '금지 어휘' — '이는'은 단어 경계 정규식으로 별도 처리
BANNED_WORDS = ["단순히", "또한", "이를 통해", "바탕으로", "무엇보다", "단순한", "넘어"]
INEUN = re.compile(r"(?:^|[ ,.'])이는(?=[ ,.]|$)")
# 규칙정본 '특수문자' — 작은따옴표(')는 도서명 전용으로 허용
BANNED_CHARS = re.compile("[·\\-<>\"“”‘’*※①-⑳#&@]")


def check_text(text: str, profile: dict, exempt: bool = False):
    """단일 세특 본문을 검사한다. 반환: (utf8 바이트수, [(레벨, 코드, 메시지)])."""
    issues: list[tuple[str, str, str]] = []
    nbytes = len(text.encode("utf-8"))

    for word in BANNED_WORDS:
        if word in text:
            issues.append(("FAIL", "BANNED_WORD", f"금지 어휘 '{word}' 포함"))
    if INEUN.search(text):
        issues.append(("FAIL", "BANNED_WORD", "금지 어휘 '이는' 포함"))

    match = BANNED_CHARS.search(text)
    if match:
        issues.append(("FAIL", "BANNED_CHAR", f"금지 특수문자 '{match.group()}' 포함"))

    return nbytes, issues
