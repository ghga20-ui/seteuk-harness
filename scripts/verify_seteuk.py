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

    # 바이트 한도 및 문두 검사
    limit = int(profile.get("상한바이트", 760))
    target = int(profile.get("목표바이트", 700))
    if nbytes > limit:
        issues.append(("FAIL", "BYTE_OVER", f"{nbytes}바이트로 상한 {limit} 초과"))
    elif not exempt and nbytes < target - 80:
        issues.append(("WARN", "BYTE_UNDER", f"{nbytes}바이트로 목표 {target}에 크게 미달"))

    if not exempt:
        prefix = profile.get("문두", "")
        if prefix and not text.startswith(prefix):
            issues.append(("FAIL", "OPENING", f"문두가 '{prefix}'로 시작하지 않음"))

    return nbytes, issues


def find_name_intrusions(text: str, names: list[str]) -> list[str]:
    """본문에 등장한 학생 이름 목록을 반환한다(본인 포함 — 이름 기재 자체가 금지)."""
    return [name for name in names if name and name in text]


def verify_drafts(drafts: dict, profile: dict) -> dict:
    """전체 초안을 검사해 보고서를 만든다. 이름 혼입은 반 전체 명단으로 검사한다."""
    rows = []
    fail = warn = 0
    for cls in drafts.get("classes", []):
        names = [s.get("이름", "") for s in cls.get("students", [])]
        for student in cls.get("students", []):
            text = student.get("세특", "")
            exempt = bool(student.get("예외", False))
            nbytes, issues = check_text(text, profile, exempt=exempt)
            for name in find_name_intrusions(text, names):
                issues.append(("FAIL", "NAME", f"학생 이름 '{name}' 본문 혼입"))
            fail += sum(1 for lv, _, _ in issues if lv == "FAIL")
            warn += sum(1 for lv, _, _ in issues if lv == "WARN")
            rows.append(
                {"반": cls.get("name", ""), "학번": student.get("학번", ""),
                 "이름": student.get("이름", ""), "바이트": nbytes, "issues": issues}
            )
    return {"rows": rows, "fail": fail, "warn": warn}


def save_xlsx(drafts: dict, report: dict, out_path: str) -> None:
    """검증 보고서와 함께 반별 시트로 저장한다. 호출 전 FAIL 0을 보장할 것."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    nbytes_map = {(r["반"], r["학번"]): r["바이트"] for r in report["rows"]}
    wb = Workbook()
    wb.remove(wb.active)
    for cls in drafts.get("classes", []):
        ws = wb.create_sheet(cls.get("name", "시트"))
        ws.append(["학번", "이름", "핵심소재", "톤등급", "세특", "바이트수", "비고"])
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9E1F2")
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for s in cls.get("students", []):
            ws.append([s.get("학번", ""), s.get("이름", ""), s.get("핵심소재", ""),
                       s.get("톤등급", ""), s.get("세특", ""),
                       nbytes_map.get((cls.get("name", ""), s.get("학번", "")), ""),
                       s.get("비고", "")])
        for col, width in zip("ABCDEFG", [8, 8, 24, 7, 90, 8, 30]):
            ws.column_dimensions[col].width = width
        for row in ws.iter_rows(min_row=2):
            row[4].alignment = Alignment(wrap_text=True, vertical="top")
            row[6].alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(out_path)


def main(argv=None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="세특 결정론 채점기 + 저장 게이트")
    parser.add_argument("drafts", help="초안 JSON 경로")
    parser.add_argument("--profile", required=True, help="활동프로파일 JSON 경로")
    parser.add_argument("--save", help="검증 통과 시 저장할 xlsx 경로")
    args = parser.parse_args(argv)

    with open(args.drafts, encoding="utf-8") as f:
        drafts = json.load(f)
    with open(args.profile, encoding="utf-8") as f:
        profile = json.load(f)

    report = verify_drafts(drafts, profile)
    for row in report["rows"]:
        for level, code, msg in row["issues"]:
            print(f"{level} {row['반']} {row['학번']} [{code}] {msg}")
    print(f"결과: FAIL {report['fail']}건, WARN {report['warn']}건")

    if report["fail"] > 0:
        print("저장 차단: FAIL을 모두 해소한 뒤 다시 실행하세요.")
        return 1
    if args.save:
        save_xlsx(drafts, report, args.save)
        print(f"저장 완료: {args.save}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
