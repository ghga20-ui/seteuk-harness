#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""손글씨 답안지 인적사항 마스킹 — 로컬 전용.

비전(LLM)에 보내기 전에 인적사항 구역을 덮는다. 원본은 수정하지 않고 사본을 만든다.
좌표는 이미지 크기에 무관한 비율(0~1)이라 촬영 해상도가 달라도 재사용할 수 있다.
"""
from __future__ import annotations

from pathlib import Path


def _abs_box(size, box):
    w, h = size
    left, top, right, bottom = box
    return (int(left * w), int(top * h), int(right * w), int(bottom * h))


def mask_region(src, dst, box) -> None:
    """비율 좌표 영역을 검은 사각형으로 덮은 사본을 만든다."""
    from PIL import Image, ImageDraw

    img = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle(_abs_box(img.size, box), fill=(0, 0, 0))
    img.save(dst)


def crop_region(src, dst, box) -> None:
    """인적사항 구역만 잘라 로컬 대조용 썸네일을 만든다(LLM 전송 금지)."""
    from PIL import Image

    img = Image.open(src).convert("RGB")
    img.crop(_abs_box(img.size, box)).save(dst)


def check_count(image_count: int, pages_per_student: int, expected_students: int):
    """개수 대사 게이트. 불일치하면 진행을 차단하고 수치를 보고한다."""
    if pages_per_student <= 0:
        return False, "학생당 장수는 1 이상이어야 합니다."
    expected_images = pages_per_student * expected_students
    if image_count == expected_images:
        return True, f"이미지 {image_count}장 = 학생 {expected_students}명 x {pages_per_student}장"
    return (
        False,
        f"불일치: 이미지 {image_count}장, 예상 {expected_images}장"
        f"(학생 {expected_students}명 x {pages_per_student}장). "
        "미제출 신고 누락, 촬영 누락·중복, 장수 설정 오류를 확인하세요.",
    )
