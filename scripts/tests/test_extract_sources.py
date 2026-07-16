# -*- coding: utf-8 -*-
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_sources import extract, sniff_format

HWPX_SECTION = """<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
        xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
<hp:p><hp:run><hp:t>첫 문단입니다.</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:t>둘째 문단이며 </hp:t></hp:run><hp:run><hp:t>런이 나뉘어 있습니다.</hp:t></hp:run></hp:p>
</hs:sec>
"""

DISGUISED_HTML = """
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8"></head><body>
        <table><tr><th>학번</th><th>이름</th><th>본문</th></tr>
        <tr><td>10101</td><td>김가상</td><td>작품을 읽고<br>감상을 정리함.</td></tr></table>
        </body></html>
"""


def make_hwpx(tmp_path):
    p = tmp_path / "가상문서.hwpx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", HWPX_SECTION)
    return p


def make_disguised_xls(tmp_path):
    p = tmp_path / "가상반.xls"
    p.write_text(DISGUISED_HTML, encoding="utf-8")
    return p


def make_xlsx(tmp_path):
    from openpyxl import Workbook

    p = tmp_path / "가상반.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "1반"
    ws.append(["학번", "이름", "본문"])
    ws.append(["10101", "김가상", "감상문 본문입니다."])
    wb.save(p)
    return p


def make_fake_hwp(tmp_path):
    p = tmp_path / "가상.hwp"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    return p


def test_sniff_disguised_html(tmp_path):
    assert sniff_format(make_disguised_xls(tmp_path)) == "html"


def test_sniff_hwpx(tmp_path):
    assert sniff_format(make_hwpx(tmp_path)) == "hwpx"


def test_sniff_xlsx(tmp_path):
    assert sniff_format(make_xlsx(tmp_path)) == "xlsx"


def test_sniff_ole_binary(tmp_path):
    assert sniff_format(make_fake_hwp(tmp_path)) == "hwp-or-ole"


def test_extract_hwpx_paragraphs(tmp_path):
    fmt, text = extract(make_hwpx(tmp_path))
    assert fmt == "hwpx"
    assert "첫 문단입니다." in text
    assert "둘째 문단이며 런이 나뉘어 있습니다." in text
    assert text.index("첫 문단") < text.index("둘째 문단")


def test_extract_html_table(tmp_path):
    fmt, text = extract(make_disguised_xls(tmp_path))
    assert fmt == "html"
    assert "10101" in text
    assert "김가상" in text
    assert "작품을 읽고" in text


def test_extract_xlsx_rows(tmp_path):
    fmt, text = extract(make_xlsx(tmp_path))
    assert fmt == "xlsx"
    assert "1반" in text
    assert "10101" in text
    assert "감상문 본문입니다." in text


def test_cli_unsupported_hwp_exits_2(tmp_path):
    script = str(Path(__file__).resolve().parents[1] / "extract_sources.py")
    proc = subprocess.run(
        [sys.executable, script, str(make_fake_hwp(tmp_path))],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 2
    assert "다시 저장" in proc.stdout + proc.stderr
