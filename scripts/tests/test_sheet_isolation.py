# -*- coding: utf-8 -*-
"""엑셀 시트를 이어붙이지 않고 시트별로 처리하는지 검증하는 테스트.

실제 파일 341개 측정에서 19~29개 파일이 "전 시트를 한 리스트로 이어붙이는" 버그에
걸렸다. 반별로 시트가 나뉜 채점표가 한 반으로 합쳐지거나(명렬 인식), 시트1의 헤더
열 인덱스로 시트2의 데이터를 읽어(열 인덱스는 시트마다 다르다) 엉뚱한 값을 점수로
가져오는 사고가 났다. 등장인물은 전부 가상이다.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pseudonymize as P

SCRIPT = str(Path(__file__).resolve().parents[1] / "pseudonymize.py")


def run(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def _make_multi_sheet_xlsx(tmp_path, sheets, filename="다중시트.xlsx"):
    """sheets: [(시트명, [헤더행, 데이터행...]), ...]"""
    from openpyxl import Workbook

    p = tmp_path / filename
    wb = Workbook()
    default_ws = wb.active
    for i, (name, rows) in enumerate(sheets):
        ws = default_ws if i == 0 else wb.create_sheet()
        ws.title = name
        for row in rows:
            ws.append(list(row))
    wb.save(p)
    return p


# ---------------------------------------------------------------------------
# detect_roster — 시트 간 학번 집합 비교로 합칠지·하나만 쓸지 판단
# ---------------------------------------------------------------------------

def test_disjoint_sheets_merge_as_union(tmp_path):
    """선택과목을 반별로 나눠 시트가 학번 교집합 0이면 합집합이 정답이다.

    실측 다중 데이터시트 17개 중 9개가 이 경우였고, 시트 하나만 고르면
    14~137명을 잃었다.
    """
    sheet1 = [("학번", "이름")] + [(f"3010{i}", f"가상{i}") for i in range(1, 6)]
    sheet2 = [("학번", "이름")] + [(f"3020{i}", f"허구{i}") for i in range(1, 6)]
    path = _make_multi_sheet_xlsx(tmp_path, [("1반", sheet1), ("2반", sheet2)])

    roster = P.detect_roster(path)

    assert len(roster["students"]) == 10
    assert set(roster.get("시트합침", [])) == {"1반", "2반"}
    ids = {s["학번"] for s in roster["students"]}
    assert ids == {f"3010{i}" for i in range(1, 6)} | {f"3020{i}" for i in range(1, 6)}


def test_repeated_roster_across_sheets_uses_largest_only(tmp_path):
    """같은 명렬이 여러 시트에 반복 등재되면(교집합이 작은 쪽의 80% 이상) 가장
    큰 시트만 쓰고, 시트 간 제거는 '중복'이 아니라 확인사유로 보고한다."""
    sheet1 = [("학번", "이름")] + [(f"3010{i}", f"가상{i}") for i in range(1, 6)]
    sheet2 = [("학번", "이름")] + [(f"3010{i}", f"가상{i}") for i in range(1, 6)]
    path = _make_multi_sheet_xlsx(tmp_path, [("원본", sheet1), ("사본", sheet2)])

    roster = P.detect_roster(path)

    assert len(roster["students"]) == 5
    assert any("반복" in reason for reason in roster["확인사유"])
    assert roster["중복"] == 0
    assert "시트합침" not in roster


def test_sheet2_header_indices_not_reused_from_sheet1(tmp_path):
    """시트1은 '학번|이름' 순서, 시트2는 '이름|학번'으로 열 순서가 다르면 시트1의
    인덱스로 시트2를 읽어서는 안 된다(합쳐도 이름 칸에 학번이 들어가면 안 됨)."""
    sheet1 = [("학번", "이름")] + [(f"3010{i}", f"가상{i}") for i in range(1, 6)]
    sheet2 = [("이름", "학번")] + [(f"허구{i}", f"3020{i}") for i in range(1, 6)]
    path = _make_multi_sheet_xlsx(tmp_path, [("1반", sheet1), ("2반", sheet2)])

    roster = P.detect_roster(path)

    assert len(roster["students"]) == 10
    for s in roster["students"]:
        # 이름 칸에 5자리 학번 숫자열이 들어가면 인덱스가 뒤바뀐 것이다.
        assert not s["이름"].isdigit()
        assert s["학번"].isdigit()
    names = {s["이름"] for s in roster["students"]}
    assert names == {f"가상{i}" for i in range(1, 6)} | {f"허구{i}" for i in range(1, 6)}


def test_single_sheet_roster_regression(tmp_path):
    """데이터가 잡힌 시트가 1개면 회귀 없이 기존과 동일하게 동작한다."""
    rows = [("학번", "이름")] + [(f"3010{i}", f"가상{i}") for i in range(1, 6)]
    path = _make_multi_sheet_xlsx(tmp_path, [("1반", rows)])

    roster = P.detect_roster(path)

    assert len(roster["students"]) == 5
    assert roster["방식"] == "표헤더"
    assert "시트합침" not in roster
    assert roster["확인사유"] == []


# ---------------------------------------------------------------------------
# score — 점수는 학번 키로 매칭되지만, 명렬처럼 시트를 합치지 않는다(fail-closed).
# ---------------------------------------------------------------------------

def _write_roster_and_mapping(tmp_path, ids):
    roster = {"students": [{"학번": sid, "이름": f"학생{sid}"} for sid in ids]}
    roster_path = tmp_path / "명렬.json"
    roster_path.write_text(json.dumps(roster, ensure_ascii=False), encoding="utf-8")

    mapping_path = tmp_path / "매핑.json"
    run("issue", "--roster", str(roster_path), "--submitted", ",".join(ids), "--out", str(mapping_path))
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    return roster_path, mapping_path, mapping


def test_score_cli_multi_sheet_data_exits_without_selecting(tmp_path):
    """점수 데이터가 있는 시트가 2개면 조용히 합치거나 고르지 않고 exit 1로 멈춘 뒤
    시트 목록을 제시한다. 이름·학번은 출력하지 않는다."""
    ids = [f"3010{i}" for i in range(1, 4)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)

    sheet1 = [("학번", "점수")] + [(sid, "15") for sid in ids]
    sheet2 = [("학번", "점수")] + [(sid, "13") for sid in ids]
    src = _make_multi_sheet_xlsx(tmp_path, [("1반", sheet1), ("2반", sheet2)], filename="채점표.xlsx")

    out = tmp_path / "점수.json"
    proc = run("score", str(src), "--roster", str(roster_path), "--mapping", str(mapping_path), "--out", str(out))

    assert proc.returncode == 1
    assert not out.exists()
    assert "데이터가 있는 시트가 2개입니다" in proc.stdout
    assert "1반" in proc.stdout and "2반" in proc.stdout
    for sid in ids:
        assert sid not in proc.stdout
    assert "학생" not in proc.stdout


def test_score_cli_sheet_option_selects_named_sheet(tmp_path):
    """--sheet로 지정하면 그 시트만 파싱하고, 다른 시트의 열 인덱스를 섞어 쓰지 않는다."""
    ids = [f"3010{i}" for i in range(1, 4)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)

    sheet1 = [("학번", "점수")] + [(sid, "15") for sid in ids]
    sheet2 = [("학번", "점수")] + [(sid, "20") for sid in ids]
    src = _make_multi_sheet_xlsx(tmp_path, [("1반", sheet1), ("2반", sheet2)], filename="채점표.xlsx")

    out = tmp_path / "점수.json"
    proc = run(
        "score", str(src), "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--sheet", "2반",
    )

    assert proc.returncode == 0
    assert out.exists()
    saved = json.loads(out.read_text(encoding="utf-8"))
    scores = {item["토큰"]: item["점수"] for item in saved["items"]}
    for sid in ids:
        assert scores[mapping["map"][sid]] == 20


def test_score_cli_invalid_sheet_name_lists_valid_sheets(tmp_path):
    """--sheet에 잘못된 시트명을 주면 exit 1로 멈추고 유효한 시트명을 안내한다."""
    ids = [f"3010{i}" for i in range(1, 4)]
    roster_path, mapping_path, mapping = _write_roster_and_mapping(tmp_path, ids)

    sheet1 = [("학번", "점수")] + [(sid, "15") for sid in ids]
    src = _make_multi_sheet_xlsx(tmp_path, [("1반", sheet1)], filename="채점표.xlsx")

    out = tmp_path / "점수.json"
    proc = run(
        "score", str(src), "--roster", str(roster_path), "--mapping", str(mapping_path),
        "--out", str(out), "--sheet", "3반",
    )

    assert proc.returncode == 1
    assert not out.exists()
    assert "찾을 수 없습니다" in proc.stdout
    assert "1반" in proc.stdout
