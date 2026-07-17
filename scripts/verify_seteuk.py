#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seteuk-harness 결정론 채점기 + 저장 게이트.

기계 규칙은 wiki/규칙.json(단일 정본)에서 읽는다. 파일이 없으면 내장 기본값을 쓴다.
규칙정본.md(사람용)를 개정할 때는 규칙.json도 함께 갱신한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# wiki/규칙.json이 없거나 손상됐을 때의 내장 기본값
DEFAULT_RULES = {
    "금지어휘": ["단순히", "또한", "이를 통해", "바탕으로", "무엇보다", "단순한", "넘어"],
    "이는_경계검사": True,
    "금지문자패턴": "[·\\-<>\"“”‘’*※①-⑳#&@]",
    "목표바이트": 700,
    "상한바이트": 760,
}
RULES_PATH = Path(__file__).resolve().parent.parent / "wiki" / "규칙.json"
INEUN = re.compile(r"(?:^|[ ,.'])이는(?=[ ,.]|$)")


def load_rules(path=RULES_PATH) -> dict:
    """규칙 파일을 읽어 기본값 위에 덮는다. 실패하면 기본값을 반환한다."""
    rules = dict(DEFAULT_RULES)
    try:
        with open(path, encoding="utf-8") as f:
            rules.update(json.load(f))
    except (OSError, ValueError):
        pass
    return rules


RULES = load_rules()


def check_text(text: str, profile: dict, exempt: bool = False, rules: dict | None = None):
    """단일 세특 본문을 검사한다. 반환: (utf8 바이트수, [(레벨, 코드, 메시지)])."""
    if rules is None:
        rules = RULES
    issues: list[tuple[str, str, str]] = []
    nbytes = len(text.encode("utf-8"))

    for word in rules.get("금지어휘", []):
        if word in text:
            issues.append(("FAIL", "BANNED_WORD", f"금지 어휘 '{word}' 포함"))
    if rules.get("이는_경계검사", True) and INEUN.search(text):
        issues.append(("FAIL", "BANNED_WORD", "금지 어휘 '이는' 포함"))

    match = re.search(rules.get("금지문자패턴", DEFAULT_RULES["금지문자패턴"]), text)
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


def verify_drafts(drafts: dict, profile: dict, roster: dict | None = None) -> dict:
    """전체 초안을 검사해 보고서를 만든다. 이름 혼입은 반 전체 명단으로 검사한다.

    roster({"students":[{"학번","이름"}]})를 주면 명렬 대조를 수행한다:
    초안에만 있는 학번·이름 불일치는 FAIL(ROSTER), 명렬에만 있는 학생은
    보고서의 "미제출" 목록으로 반환한다(잘못된 학생 귀속과 조용한 누락 방지).
    """
    roster_map = None
    if roster is not None:
        roster_map = {str(s.get("학번", "")): s.get("이름", "") for s in roster.get("students", [])}

    rows = []
    fail = warn = 0
    seen_ids = set()
    for cls in drafts.get("classes", []):
        names = [s.get("이름", "") for s in cls.get("students", [])]
        for student in cls.get("students", []):
            sid = str(student.get("학번", ""))
            sname = student.get("이름", "")
            seen_ids.add(sid)
            text = student.get("세특", "")
            exempt = bool(student.get("예외", False))
            nbytes, issues = check_text(text, profile, exempt=exempt)
            for name in find_name_intrusions(text, names):
                issues.append(("FAIL", "NAME", f"학생 이름 '{name}' 본문 혼입"))
            if roster_map is not None:
                if sid not in roster_map:
                    issues.append(("FAIL", "ROSTER", f"학번 {sid}이 명렬에 없음 — 오전사 또는 오매핑 의심"))
                elif roster_map[sid] != sname:
                    issues.append(("FAIL", "ROSTER",
                                   f"학번 {sid}의 이름이 명렬({roster_map[sid]})과 불일치({sname}) — 학생 귀속 확인 필요"))
            fail += sum(1 for lv, _, _ in issues if lv == "FAIL")
            warn += sum(1 for lv, _, _ in issues if lv == "WARN")
            rows.append(
                {"반": cls.get("name", ""), "학번": sid,
                 "이름": sname, "바이트": nbytes, "issues": issues}
            )

    missing = []
    if roster_map is not None:
        missing = [{"학번": sid, "이름": name} for sid, name in roster_map.items() if sid not in seen_ids]
    return {"rows": rows, "fail": fail, "warn": warn, "미제출": missing}


def save_xlsx(drafts: dict, report: dict, out_path: str) -> None:
    """검증 보고서와 함께 반별 시트로 저장한다. 호출 전 FAIL 0을 보장할 것."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    nbytes_map = {(r["반"], r["학번"]): r["바이트"] for r in report["rows"]}
    wb = Workbook()
    wb.remove(wb.active)
    notice = wb.create_sheet("안내")
    notice["A1"] = "AI 초안 — 교사 검수 전"
    notice["A2"] = "이 파일의 세특은 AI가 생성한 초안입니다. 교사가 실제 수행과의 일치, 허위·과장 여부,"
    notice["A3"] = "기재요령 준수를 검수·승인하기 전에는 NEIS에 입력할 수 없습니다."
    notice["A1"].font = Font(bold=True, size=14, color="C00000")
    notice.column_dimensions["A"].width = 90
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
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="세특 결정론 채점기 + 저장 게이트")
    parser.add_argument("drafts", help="초안 JSON 경로")
    parser.add_argument("--profile", required=True, help="활동프로파일 JSON 경로")
    parser.add_argument("--roster", help="명렬 JSON 경로(선택) — 학번·이름 대조와 미제출자 보고")
    parser.add_argument("--save", help="검증 통과 시 저장할 xlsx 경로")
    args = parser.parse_args(argv)

    with open(args.drafts, encoding="utf-8") as f:
        drafts = json.load(f)
    with open(args.profile, encoding="utf-8") as f:
        profile = json.load(f)
    roster = None
    if args.roster:
        with open(args.roster, encoding="utf-8") as f:
            roster = json.load(f)

    if not str(profile.get("평가자료", "")).strip():
        print("차단: 교사의 평가 자료(채점표, 루브릭 점수, 관찰 기록 등)가 확인되지 않았습니다.")
        print("이 도구는 평가를 대신하지 않습니다. 채점을 먼저 완료하고 활동프로파일의 평가자료 항목에 출처를 기록하세요.")
        return 1

    total_students = sum(len(cls.get("students", [])) for cls in drafts.get("classes", []))
    if total_students == 0:
        print("오류: 초안에 학생이 없습니다. 초안 JSON의 classes/students 구조를 확인하세요.")
        return 1

    report = verify_drafts(drafts, profile, roster=roster)
    for row in report["rows"]:
        for level, code, msg in row["issues"]:
            print(f"{level} {row['반']} {row['학번']} [{code}] {msg}")
    for s in report.get("미제출", []):
        print(f"미제출 {s['학번']} {s['이름']} — 원본 없음, 별도 확인 필요")
    print(f"결과: FAIL {report['fail']}건, WARN {report['warn']}건, 미제출 {len(report.get('미제출', []))}명")

    if report["fail"] > 0:
        print("저장 차단: FAIL을 모두 해소한 뒤 다시 실행하세요.")
        return 1
    if args.save:
        import os

        tmp_path = args.save + ".tmp"
        try:
            save_xlsx(drafts, report, tmp_path)
            os.replace(tmp_path, args.save)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        print(f"저장 완료: {args.save}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
