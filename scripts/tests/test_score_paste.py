# -*- coding: utf-8 -*-
"""score 명령의 붙여넣기 입력 경로(--paste) 검증.

실측 채점표 37개 중 20개(54.1%)가 점수 열 후보를 정확히 하나만 내놓았는데
그 하나가 틀린 활동의 열이었다. 후보가 1개면 _resolve_score_column이
모호성을 감지하지 못해(ambiguous 분기에 들어가지 않아) 질문 트리거가
원리적으로 생기지 않는다 — 파일을 아무리 잘 파싱해도 잡을 수 없는 오염이다.
유일한 해법은 교사가 화면에서 학번·점수 두 열을 직접 골라 붙여넣게 하고,
그 값을 그대로 신뢰하는 것이다(명렬입력.html 3단계가 만드는 점수원본.json).

등장인물은 전부 가상 학번(30101 등)이며 이름은 등장시키지 않는다.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCRIPT = str(Path(__file__).resolve().parents[1] / "pseudonymize.py")


def run(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def _write_roster_and_mapping(tmp_path, ids):
    """이름은 '학생<학번>' 같은 자리표시자일 뿐 실제 이름이 아니다 — CLI가
    이 값을 stdout에 출력하지 않는지가 이 테스트 파일의 핵심 단언이다."""
    roster = {"students": [{"학번": sid, "이름": f"학생{sid}"} for sid in ids]}
    roster_path = tmp_path / "명렬.json"
    roster_path.write_text(json.dumps(roster, ensure_ascii=False), encoding="utf-8")

    mapping_path = tmp_path / "매핑.json"
    run("issue", "--roster", str(roster_path), "--submitted", ",".join(ids), "--out", str(mapping_path))
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    return roster_path, mapping_path, mapping


def _write_paste(tmp_path, items, filename="점수원본.json"):
    p = tmp_path / filename
    p.write_text(json.dumps({"항목": items}, ensure_ascii=False), encoding="utf-8")
    return p


def test_paste_score_produces_token_score_items_and_distribution(tmp_path):
    ids = [f"3010{i}" for i in range(1, 4)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)
    items = [{"학번": sid, "점수": 15} for sid in ids]
    paste = _write_paste(tmp_path, items)
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste),
    )

    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 3
    tokens = set(mapping["map"].values())
    for item in saved["items"]:
        assert item["점수"] == 15
        assert item["토큰"] in tokens
        assert "학번" not in item
    assert "붙여넣기" in proc.stdout
    assert "15점 3명" in proc.stdout
    for sid in ids:
        assert sid not in proc.stdout
    assert "학생" not in proc.stdout


def test_paste_grade_produces_token_grade_items_and_distribution(tmp_path):
    ids = [f"3020{i}" for i in range(1, 4)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)
    grades = ["상", "중", "중"]
    items = [{"학번": sid, "등급": g} for sid, g in zip(ids, grades)]
    paste = _write_paste(tmp_path, items)
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste),
    )

    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 3
    for item in saved["items"]:
        assert "등급" in item
        assert "점수" not in item
    assert "붙여넣기" in proc.stdout
    assert "중 2명" in proc.stdout
    assert "상 1명" in proc.stdout
    for sid in ids:
        assert sid not in proc.stdout


def test_paste_mixed_score_and_grade_rejected(tmp_path):
    ids = [f"3030{i}" for i in range(1, 3)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)
    items = [{"학번": ids[0], "점수": 10}, {"학번": ids[1], "등급": "상"}]
    paste = _write_paste(tmp_path, items)
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste),
    )

    assert proc.returncode == 1
    assert "섞" in proc.stdout
    assert not out.exists()


def test_paste_excludes_unmapped_ids_and_reports_count(tmp_path):
    ids = [f"3040{i}" for i in range(1, 3)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)
    items = [{"학번": ids[0], "점수": 10}, {"학번": "39999", "점수": 20}]
    paste = _write_paste(tmp_path, items)
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste),
    )

    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 1
    assert "매핑 없음 1건" in proc.stdout
    assert "39999" not in proc.stdout


def test_paste_and_column_mutually_exclusive(tmp_path):
    ids = ["30501"]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)
    items = [{"학번": ids[0], "점수": 10}]
    paste = _write_paste(tmp_path, items)
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste), "--column", "R",
    )

    assert proc.returncode == 1
    assert "--paste" in proc.stdout
    assert not out.exists()


def test_paste_and_sheet_mutually_exclusive(tmp_path):
    ids = ["30502"]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)
    items = [{"학번": ids[0], "점수": 10}]
    paste = _write_paste(tmp_path, items)
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste), "--sheet", "1반",
    )

    assert proc.returncode == 1
    assert "--paste" in proc.stdout


def test_paste_empty_items_rejected_with_reason(tmp_path):
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ["30601"])
    paste = _write_paste(tmp_path, [])
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste),
    )

    assert proc.returncode == 1
    assert "항목" in proc.stdout
    assert not out.exists()


def test_paste_missing_file_rejected_with_reason(tmp_path):
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ["30602"])
    missing = tmp_path / "없음.json"
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(missing),
    )

    assert proc.returncode == 1
    assert proc.stdout.strip() != ""
    assert not out.exists()


def test_paste_input_positional_not_required(tmp_path):
    """--paste를 쓰면 채점표 xlsx 위치 인자를 아예 주지 않아도 동작한다."""
    ids = ["30701"]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)
    items = [{"학번": ids[0], "점수": 12}]
    paste = _write_paste(tmp_path, items)
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--paste", str(paste),
    )

    assert proc.returncode == 0
    assert out.exists()


def test_missing_input_without_paste_is_rejected(tmp_path):
    """--paste도 없고 위치 인자도 없으면 이전처럼 명확한 사유로 거부한다."""
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ["30801"])
    out = tmp_path / "점수.json"

    proc = run(
        "score", "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out),
    )

    assert proc.returncode == 1
    assert proc.stdout.strip() != ""


def test_existing_xlsx_path_regression_without_paste(tmp_path):
    """--paste 없이 기존 xlsx 경로가 회귀 없이 그대로 동작하는지 확인한다."""
    from openpyxl import Workbook

    ids = [f"3090{i}" for i in range(1, 3)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)

    wb = Workbook()
    ws = wb.active
    ws.append(("학번", "점수"))
    for sid in ids:
        ws.append((sid, 20))
    src = tmp_path / "채점표.xlsx"
    wb.save(src)

    out = tmp_path / "점수.json"
    proc = run(
        "score", str(src), "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out),
    )

    assert proc.returncode == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert len(saved["items"]) == 2
    for item in saved["items"]:
        assert item["점수"] == 20
