# -*- coding: utf-8 -*-
"""검수.html 생성기 — 검수번들.json을 검수템플릿.html에 심는다.

file:// 로 여는 페이지는 옆 파일(fetch)을 읽을 수 없으므로, 검수 데이터는
HTML 안에 <script type="application/json"> 블록으로 심는 것이 유일한 길이다
(docs/ux 실측). 심을 때 JSON 문자열의 < 를 \\u003c 로 바꾼다 — 학생 글에
닫는 스크립트 태그가 있으면 화면 전체가 조용히 죽는 사고를 막는 필수
이스케이프다.

계약:
- 산출 파일(검수.html)은 실명을 담는다(로컬 전용). stdout에는 이름이 절대
  나오지 않는다 — 집계와 안내 문장만 낸다.
- 템플릿을 못 찾거나 번들이 비면 exit 1과 사유를 낸다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 검수.html은 실명을 담으므로 생성 순간부터 소유자 전용 권한(0o600)으로 쓴다.
# 같은 scripts/ 폴더의 pseudonymize에 있는 헬퍼를 그대로 쓴다 — 스크립트로
# 실행하면 sys.path[0]이 scripts/라 바로 import된다(verify_seteuk과 같은 방식).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pseudonymize import _open_private

MARKER = "__검수데이터__"
DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "tools" / "검수템플릿.html"


def build_html(template: str, bundle: dict) -> str:
    """템플릿의 플레이스홀더에 번들 JSON을 심은 HTML을 돌려준다.

    < 이스케이프는 선택이 아니다: 학생 원문의 </script> 한 건이 화면 전체를
    빈 화면으로 만든다. JSON 규격상 \\u003c 는 파싱하면 < 로 돌아오므로
    데이터는 한 글자도 달라지지 않는다.
    """
    if MARKER not in template:
        raise ValueError("템플릿에 데이터 플레이스홀더가 없습니다")
    payload = json.dumps(bundle, ensure_ascii=False).replace("<", "\\u003c")
    return template.replace(MARKER, payload, 1)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="검수번들.json을 검수템플릿.html에 심어 더블클릭으로 열리는 "
                    "검수.html을 만든다. 산출 파일은 실명을 담으므로 활동 폴더에만 둔다.")
    parser.add_argument("bundle", help="검수번들.json 경로")
    parser.add_argument("--out", help="검수.html 저장 경로 (기본: 번들 옆의 검수.html)")
    parser.add_argument("--template", help="검수템플릿.html 경로 (기본: 스킬의 tools/)")
    args = parser.parse_args(argv)

    template_path = Path(args.template) if args.template else DEFAULT_TEMPLATE
    if not template_path.is_file():
        print(f"생성 실패: 검수템플릿을 찾지 못했습니다. ({template_path})")
        return 1
    template = template_path.read_text(encoding="utf-8-sig")
    if MARKER not in template:
        print("생성 실패: 템플릿에 데이터 플레이스홀더가 없습니다. 템플릿 파일이 손상됐을 수 있습니다.")
        return 1

    bundle_path = Path(args.bundle)
    try:
        raw = bundle_path.read_text(encoding="utf-8-sig")
    except OSError:
        print(f"생성 실패: 검수번들을 읽지 못했습니다. ({bundle_path})")
        return 1
    if not raw.strip():
        print("생성 실패: 검수번들이 빈 파일입니다. review-bundle을 먼저 실행하세요.")
        return 1
    try:
        bundle = json.loads(raw)
    except ValueError:
        print("생성 실패: 검수번들이 올바른 JSON이 아닙니다. review-bundle을 다시 실행하세요.")
        return 1
    students = bundle.get("students") if isinstance(bundle, dict) else None
    if not isinstance(students, list) or not students:
        print("생성 실패: 검수번들에 학생이 없습니다.")
        return 1

    html = build_html(template, bundle)
    out_path = Path(args.out) if args.out else bundle_path.parent / "검수.html"
    with _open_private(out_path) as f:
        f.write(html)

    n = len(students)
    priority = sum(1 for s in students if s.get("우선검토"))
    with_source = sum(1 for s in students if s.get("원문"))
    with_pairs = sum(1 for s in students if s.get("짝") or s.get("짝없음"))
    print(f"검수 화면: {n}명(우선 검토 {priority}명, 원문 포함 {with_source}명, "
          f"짝 표시 {with_pairs}명). 저장: {out_path}")
    print("이 파일에는 실명이 들어 있습니다 — 활동 폴더에만 두세요.")
    print("창을 닫으면 고치던 내용이 사라집니다. 저장 단추를 눌러야 파일로 남습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
