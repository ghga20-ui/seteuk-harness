#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""손글씨 답안지 인적사항 마스킹 — 로컬 전용.

비전(LLM)에 보내기 전에 인적사항 구역을 덮는다. 원본은 수정하지 않고 사본을 만든다.
좌표는 이미지 크기에 무관한 비율(0~1)이라 촬영 해상도가 달라도 재사용할 수 있다.
EXIF 회전을 적용한 뒤의 방향을 기준으로 좌표를 해석한다.
"""
from __future__ import annotations

import os


def _abs_box(size, box):
    w, h = size
    left, top, right, bottom = box
    return (int(left * w), int(top * h), int(right * w), int(bottom * h))


def _open_private_bytes(path):
    """실명이 든 이미지 사본을 소유자 전용 권한(0o600)으로 만들어 여는 바이너리 쓰기 헬퍼.

    pseudonymize._open_private와 같은 구조의 바이너리 판 — 이 모듈은
    pseudonymize를 import하지 않으므로 여기 자족적으로 둔다. O_CREAT의
    mode는 신규 생성에만 적용되므로, 기존 파일(예: 구버전이 0644로 만든
    마스킹 사본)을 다시 쓸 때는 열린 fd에 대한 fchmod로 낡은 권한을
    0o600으로 좁힌다(Windows엔 fchmod가 없어 건너뛰고 프로필 폴더 ACL에
    맡긴다).
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    return os.fdopen(fd, "wb")


def _pil_format(dst) -> str:
    """저장 포맷을 dst 확장자에서 유도한다(.png→PNG, .jpg/.jpeg→JPEG 등).

    파일 객체로 save하면 PIL이 경로의 확장자를 볼 수 없어 format 인자가
    필수다. 등록 확장자 표에 없으면 조용히 다른 포맷으로 저장하는 대신
    바로 실패시킨다.
    """
    from PIL import Image

    ext = os.path.splitext(os.fspath(dst))[1].lower()
    fmt = Image.registered_extensions().get(ext)
    if fmt is None:
        raise ValueError(f"지원하지 않는 이미지 확장자입니다: {dst}")
    return fmt


def mask_region(src, dst, box) -> None:
    """비율 좌표 영역을 검은 사각형으로 덮은 사본을 만든다."""
    from PIL import Image, ImageDraw, ImageOps

    img = Image.open(src).convert("RGB")
    img = ImageOps.exif_transpose(img)
    draw = ImageDraw.Draw(img)
    draw.rectangle(_abs_box(img.size, box), fill=(0, 0, 0))
    # 인적사항이 남을 수 있는 사본이므로 생성 순간부터 0o600으로 쓴다.
    with _open_private_bytes(dst) as f:
        img.save(f, format=_pil_format(dst))


def crop_region(src, dst, box) -> None:
    """인적사항 구역만 잘라 로컬 대조용 썸네일을 만든다(LLM 전송 금지)."""
    from PIL import Image, ImageOps

    img = Image.open(src).convert("RGB")
    img = ImageOps.exif_transpose(img)
    # 실명 그 자체인 크롭이므로 생성 순간부터 0o600으로 쓴다.
    with _open_private_bytes(dst) as f:
        img.crop(_abs_box(img.size, box)).save(f, format=_pil_format(dst))


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
