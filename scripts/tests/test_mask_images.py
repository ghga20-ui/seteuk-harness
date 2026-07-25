# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mask_images import check_count, crop_region, mask_region


def _make_image(tmp_path, name="원본.png", color=(255, 255, 255)):
    from PIL import Image

    p = tmp_path / name
    Image.new("RGB", (100, 100), color).save(p)
    return p


def test_mask_region_blacks_out_area(tmp_path):
    from PIL import Image

    src = _make_image(tmp_path)
    dst = tmp_path / "마스킹.png"
    mask_region(src, dst, (0.0, 0.0, 0.5, 0.2))
    img = Image.open(dst)
    assert img.getpixel((10, 10)) == (0, 0, 0)      # 마스킹 영역
    assert img.getpixel((90, 90)) == (255, 255, 255)  # 본문 영역은 보존


def test_mask_region_does_not_modify_source(tmp_path):
    from PIL import Image

    src = _make_image(tmp_path)
    mask_region(src, tmp_path / "마스킹.png", (0.0, 0.0, 0.5, 0.2))
    assert Image.open(src).getpixel((10, 10)) == (255, 255, 255)


def test_crop_region_creates_thumbnail(tmp_path):
    from PIL import Image

    src = _make_image(tmp_path)
    dst = tmp_path / "인적.png"
    crop_region(src, dst, (0.0, 0.0, 0.5, 0.2))
    assert dst.exists()
    assert Image.open(dst).size == (50, 20)


def test_check_count_matches():
    ok, msg = check_count(image_count=27, pages_per_student=1, expected_students=27)
    assert ok is True


def test_check_count_mismatch_reports_numbers():
    ok, msg = check_count(image_count=26, pages_per_student=1, expected_students=27)
    assert ok is False
    assert "26" in msg and "27" in msg


def test_check_count_handles_multi_page():
    assert check_count(image_count=54, pages_per_student=2, expected_students=27)[0] is True
    assert check_count(image_count=53, pages_per_student=2, expected_students=27)[0] is False
