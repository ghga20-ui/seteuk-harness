# -*- coding: utf-8 -*-
"""명렬 인식이 조용히 틀리지 않게 하는 가시성 장치 테스트.

실제 학교 파일 341개로 측정한 결과, 명렬을 인식한 82건 중 52건(63.4%)이
오류 없이 틀린 결과를 냈다. 이 테스트들은 그 침묵을 깨는 네 가지 장치를 고정한다.
등장인물은 전부 가상이다.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pseudonymize as P

SCRIPT = str(Path(__file__).resolve().parents[1] / "pseudonymize.py")


def _xlsx(path, rows, numeric_cols=()):
    """rows를 xlsx로 저장한다. numeric_cols에 든 열은 숫자 서식으로 넣는다."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append([
            float(c) if (j in numeric_cols and str(c).isdigit()) else c
            for j, c in enumerate(r)
        ])
    wb.save(str(path))
    return path


# ── ① 중복 학번으로 버린 행을 센다 ────────────────────────────────
def test_duplicate_rows_are_counted(tmp_path):
    """출석번호를 학번으로 쓰는 표는 반이 바뀌면 번호가 되풀이된다.

    실측에서 738행짜리 파일이 32명으로 보고됐다 — 버린 706행이 어디에도
    집계되지 않았기 때문이다.
    """
    rows = [["번호", "이름"]]
    for cls in range(3):                       # 3개 반
        for no in range(1, 6):                 # 반마다 번호 1~5 반복
            rows.append([str(no), f"가상{cls}{no}"])
    r = P.detect_roster(_xlsx(tmp_path / "r.xlsx", rows))

    assert len(r["students"]) == 5             # 첫 반만 남는다
    assert r["중복"] == 10                      # 나머지 10행은 버려졌다 — 이 사실이 드러나야 한다


def test_duplicate_count_is_zero_when_ids_unique(tmp_path):
    rows = [["학번", "이름"]] + [[f"3010{i}", f"가상{i}"] for i in range(1, 6)]
    r = P.detect_roster(_xlsx(tmp_path / "r.xlsx", rows))
    assert r["중복"] == 0


# ── ② 확인필요 딱지가 실제로 붙는다 ──────────────────────────────
def test_needs_confirm_fires_on_dropped_duplicates(tmp_path):
    """조용한 오답 52건은 전부 헤더 경로에서 나왔는데 확인필요가 False로 박혀 있었다."""
    rows = [["번호", "이름"]] + [["1", "가상갑"], ["1", "가상을"], ["2", "가상병"]]
    r = P.detect_roster(_xlsx(tmp_path / "r.xlsx", rows))
    assert r["확인필요"] is True
    assert any("중복" in s for s in r["확인사유"])


def test_needs_confirm_fires_when_id_column_is_attendance_number(tmp_path):
    """'번호'는 출석번호일 수 있다 — 학번으로 단정하면 안 된다."""
    rows = [["번호", "이름"]] + [[str(i), f"가상{i}"] for i in range(1, 6)]
    r = P.detect_roster(_xlsx(tmp_path / "r.xlsx", rows))
    assert r["확인필요"] is True
    assert any("번호" in s for s in r["확인사유"])


def test_clean_roster_needs_no_confirm(tmp_path):
    """깨끗한 표까지 확인을 요구하면 딱지가 무의미해진다."""
    rows = [["학번", "이름"]] + [[f"3010{i}", f"가상{i}"] for i in range(1, 6)]
    r = P.detect_roster(_xlsx(tmp_path / "r.xlsx", rows))
    assert r["확인필요"] is False
    assert r["확인사유"] == []


# ── ③ 못 읽은 이유를 말한다 ──────────────────────────────────────
def test_corrupt_file_reports_reason_not_just_zero(tmp_path):
    """손상 파일·구형 xls·학생 없음이 전부 '0명'으로 똑같이 보였다."""
    bad = tmp_path / "broken.xlsx"
    bad.write_bytes(b"not a zip at all")
    r = P.detect_roster(bad)
    assert r["students"] == []
    assert r.get("읽기오류")


def test_legacy_xls_reports_actionable_reason(tmp_path):
    """구형 .xls는 코퍼스의 17.3%였고 예외조차 나지 않았다."""
    old = tmp_path / "old.xls"
    old.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    r = P.detect_roster(old)
    assert r["students"] == []
    assert "xlsx" in r.get("읽기오류", "")


def test_readable_file_has_no_read_error(tmp_path):
    rows = [["학번", "이름"], ["30101", "가상갑"]]
    r = P.detect_roster(_xlsx(tmp_path / "r.xlsx", rows))
    assert not r.get("읽기오류")


# ── ④ 엑셀 숫자 서식 학번을 살린다 ───────────────────────────────
def _force_float_cells(path, ids):
    """시트 XML의 정수 셀 값을 '30101.0' 형태로 바꿔 실제 구글폼 내보내기를 재현한다.

    openpyxl은 XML에 '30101'이 있으면 int로, '30101.0'이 있으면 float로 돌려준다.
    현장 파일(설문 응답 시트 등)은 후자라서 str(cell)이 '30101.0'이 됐다.
    """
    import re as _re
    import shutil
    import zipfile

    src = Path(path)
    tmp = src.with_suffix(".orig.xlsx")
    shutil.move(str(src), str(tmp))
    with zipfile.ZipFile(tmp) as zin, zipfile.ZipFile(src, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("xl/worksheets/"):
                text = data.decode("utf-8")
                for sid in ids:
                    text = _re.sub(rf"<v>{sid}</v>", f"<v>{sid}.0</v>", text)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    tmp.unlink()
    return src


def test_numeric_formatted_ids_are_recovered(tmp_path):
    """엑셀이 학번을 숫자로 저장하면 str(cell)이 '30101.0'이 되어 통째로 버려졌다.

    실측에서 건너뜀 947행 중 441행(46.6%)이 이 한 가지 원인이었다.
    """
    ids = [f"3010{i}" for i in range(1, 6)]
    rows = [["학번", "이름"]] + [[sid, f"가상{i}"] for i, sid in enumerate(ids, 1)]
    src = _xlsx(tmp_path / "r.xlsx", rows, numeric_cols=(0,))
    r = P.detect_roster(_force_float_cells(src, ids))
    assert len(r["students"]) == 5
    assert r["students"][0]["학번"] == "30101"
    assert r["건너뜀"] == 0


def test_real_decimals_are_not_mangled_into_ids(tmp_path):
    """점수 3.5는 3으로 바뀌면 안 된다 — 정수인 실수만 복구한다."""
    rows = [["학번", "이름", "점수"], ["30101", "가상갑", 3.5]]
    _xlsx(tmp_path / "r.xlsx", rows)
    got = P._rows_from_xlsx(tmp_path / "r.xlsx")
    assert got[1][2] == "3.5"


# ── CLI: 숫자가 실제로 화면에 뜨는가 (이름·학번은 여전히 미출력) ──
def test_cli_prints_duplicate_and_reason(tmp_path):
    rows = [["번호", "이름"]]
    for cls in range(3):
        for no in range(1, 6):
            rows.append([str(no), f"가상{cls}{no}"])
    src = _xlsx(tmp_path / "r.xlsx", rows)
    proc = subprocess.run(
        [sys.executable, SCRIPT, "roster", str(src), "--out", str(tmp_path / "o.json")],
        capture_output=True, text=True, encoding="utf-8",
    )
    out = proc.stdout
    assert "10" in out and "중복" in out          # 버린 행 수가 보인다
    assert "확인" in out                           # 확인 요구가 보인다
    for r in rows[1:]:                             # 이름은 여전히 안 나온다
        assert r[1] not in out
