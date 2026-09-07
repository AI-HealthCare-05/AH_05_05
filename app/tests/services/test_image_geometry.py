"""이미지 기하 변환 5개 테스트 — 박준영님 코드 대상. 동작 변경은 없다.

    app/services/medication_ocr_v3/pipeline/preprocess.py
      apply_matrix · exif_orientation_matrix · rotation_matrix_clockwise
      resize_matrix · perspective_matrix

사진으로 찍은 처방전을 반듯한 직사각형으로 펴는 부분이다. 원본 사진 좌표를 펴진
이미지 좌표로 옮기는 환산표를 만들고, 되돌리는 표도 같이 들고 다닌다. 되돌리기가
필요한 이유는 OCR 이 펴진 이미지에서 「약 이름이 여기 있다」고 알려주면 그것을 원본
사진 위에 표시해야 하기 때문이다. 틀리면 글자는 읽되 엉뚱한 자리를 가리킨다.

⭐ **기대 좌표를 손으로 계산해 박아넣지 않는다.**

네 함수가 돌려주는 MatrixTransform 에는 `matrix` 와 `inverse` 가 함께 들어 있다.
그래서 「이 점이 (137.5, 42.0)으로 가야 한다」를 계산할 필요 없이 **성질**로 검증한다.

    - matrix 로 보냈다가 inverse 로 되돌리면 제자리인가
    - 90도를 네 번 돌리면 원래 크기·위치인가
    - 방향 1은 아무것도 바꾸지 않는가
    - 축소 행렬과 확대 행렬을 겹치면 제자리인가
    - 입력 사각형의 꼭짓점 4개가 목표 직사각형의 꼭짓점 4개로 가는가

좌표계 규약을 잘못 이해한 채 기대값을 박아넣으면 **틀린 값이 그대로 고정된다.**
이 파일을 이어받는 사람도 같은 방침을 지켜주기를 바란다.

예외는 apply_matrix 하나다. 항등행렬·단순 이동처럼 규약과 무관하게 자명한 경우만
값을 직접 단언한다.

허용 오차는 1e-9 수준으로 둔다. 픽셀 단위로 헐겁게 잡으면 틀린 행렬도 통과한다.

이미지 파일을 만들지 않는다. 다섯 함수 모두 숫자만 다룬다. DB·픽스처도 쓰지 않는다.
"""

import math

import pytest

from app.services.medication_ocr_v3.domain.image import (
    ImageErrorCode,
    ImageValidationError,
    Point,
    Quad,
)
from app.services.medication_ocr_v3.pipeline.preprocess import (
    apply_matrix,
    exif_orientation_matrix,
    perspective_matrix,
    resize_matrix,
    rotation_matrix_clockwise,
)

TOLERANCE = 1e-9

WIDTH, HEIGHT = 400, 300
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

# 코드의 destination 순서와 같은 시계방향 TL, TR, BR, BL.
# 호출부(_rectified_candidate)가 _order_quad 로 이 순서를 보장한다.
CLOCKWISE_QUAD: Quad = (Point(10.0, 20.0), Point(210.0, 15.0), Point(220.0, 170.0), Point(5.0, 160.0))


def assert_same_point(actual: Point, expected: Point, *, tolerance: float = TOLERANCE) -> None:
    assert actual.x == pytest.approx(expected.x, abs=tolerance)
    assert actual.y == pytest.approx(expected.y, abs=tolerance)


def round_trip(transform, point: Point) -> Point:
    """matrix 로 보냈다가 inverse 로 되돌린다."""
    return apply_matrix(transform.inverse, apply_matrix(transform.matrix, point))


def source_corners(width: int = WIDTH, height: int = HEIGHT) -> list[Point]:
    return [Point(0.0, 0.0), Point(float(width), 0.0), Point(float(width), float(height)), Point(0.0, float(height))]


def corner_set(transform) -> set[tuple[float, float]]:
    """목표 크기의 네 모서리를 반올림한 집합. 순서는 방향마다 달라도 집합은 같아야 한다."""
    return {
        (0.0, 0.0),
        (float(transform.target_width), 0.0),
        (float(transform.target_width), float(transform.target_height)),
        (0.0, float(transform.target_height)),
    }


def mapped_corner_set(transform, corners: list[Point]) -> set[tuple[float, float]]:
    mapped = [apply_matrix(transform.matrix, corner) for corner in corners]
    return {(round(point.x, 6), round(point.y, 6)) for point in mapped}


# ──────────────────────────────── apply_matrix ────────────────────────────────
#
# 나머지 넷을 검증할 때 도구로 쓰므로 먼저 고정한다.
# 이 함수만 MatrixTransform 이 아니라 평평한 9개짜리 튜플을 받는다.


@pytest.mark.parametrize("length", [0, 1, 8, 10, 16])
def test_apply_matrix_requires_nine_values(length: int) -> None:
    with pytest.raises(ValueError, match="nine values"):
        apply_matrix(tuple(0.0 for _ in range(length)), Point(1.0, 2.0))


def test_apply_matrix_leaves_a_point_alone_under_the_identity() -> None:
    """항등행렬은 규약과 무관하게 자명하므로 값을 직접 단언한다."""
    assert_same_point(apply_matrix(IDENTITY, Point(137.5, 42.0)), Point(137.5, 42.0))


def test_apply_matrix_translates() -> None:
    """단순 평행이동도 자명하다. 마지막 열이 이동량이라는 규약을 고정한다."""
    translate = (1.0, 0.0, 30.0, 0.0, 1.0, -12.0, 0.0, 0.0, 1.0)

    assert_same_point(apply_matrix(translate, Point(10.0, 50.0)), Point(40.0, 38.0))


def test_apply_matrix_divides_by_the_homogeneous_component() -> None:
    """마지막 행이 (0,0,1) 이 아니면 w 로 나눈다.

    w = 2 가 되도록 만들어, 나눗셈을 건너뛰면 값이 두 배로 나오게 했다.
    """
    matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 2.0)

    assert_same_point(apply_matrix(matrix, Point(10.0, 20.0)), Point(5.0, 10.0))


def test_apply_matrix_rejects_a_point_that_maps_to_infinity() -> None:
    """w 가 0 이면 나눌 수 없다. 문턱은 1e-12 다."""
    matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0)

    with pytest.raises(ValueError, match="infinity"):
        apply_matrix(matrix, Point(1.0, 1.0))


def test_apply_matrix_accepts_a_w_just_above_the_threshold() -> None:
    """1e-12 는 「미만」이 걸리므로 그 값 자체는 통과한다."""
    matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1e-12)

    result = apply_matrix(matrix, Point(1.0, 1.0))

    assert math.isfinite(result.x)
    assert math.isfinite(result.y)


def test_apply_matrix_rejects_a_w_just_below_the_threshold() -> None:
    matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1e-13)

    with pytest.raises(ValueError, match="infinity"):
        apply_matrix(matrix, Point(1.0, 1.0))


# ───────────────────────── exif_orientation_matrix ─────────────────────────

ALL_ORIENTATIONS = [1, 2, 3, 4, 5, 6, 7, 8]
SWAPPED_ORIENTATIONS = [5, 6, 7, 8]


def test_exif_orientation_one_is_the_identity() -> None:
    transform = exif_orientation_matrix(WIDTH, HEIGHT, 1)

    assert transform.matrix == IDENTITY
    assert (transform.target_width, transform.target_height) == (WIDTH, HEIGHT)
    assert_same_point(apply_matrix(transform.matrix, Point(137.5, 42.0)), Point(137.5, 42.0))


@pytest.mark.parametrize("orientation", ALL_ORIENTATIONS)
def test_exif_orientation_round_trips_every_corner(orientation: int) -> None:
    """matrix → inverse 왕복이 제자리로 오는가. 규약을 몰라도 참이어야 하는 성질이다."""
    transform = exif_orientation_matrix(WIDTH, HEIGHT, orientation)

    for corner in source_corners():
        assert_same_point(round_trip(transform, corner), corner)


@pytest.mark.parametrize("orientation", ALL_ORIENTATIONS)
def test_exif_orientation_round_trips_an_interior_point(orientation: int) -> None:
    transform = exif_orientation_matrix(WIDTH, HEIGHT, orientation)
    point = Point(137.5, 42.0)

    assert_same_point(round_trip(transform, point), point)


@pytest.mark.parametrize("orientation", ALL_ORIENTATIONS)
def test_exif_orientation_maps_source_corners_onto_target_corners(orientation: int) -> None:
    """원본 네 모서리가 목표 크기의 네 모서리에 대응한다.

    어느 모서리가 어디로 가는지는 방향마다 다르므로 **집합으로** 비교한다.
    """
    transform = exif_orientation_matrix(WIDTH, HEIGHT, orientation)

    assert mapped_corner_set(transform, source_corners()) == corner_set(transform)


@pytest.mark.parametrize("orientation", ALL_ORIENTATIONS)
def test_exif_orientation_swaps_width_and_height_only_for_the_transposing_half(orientation: int) -> None:
    """1~4 는 폭·높이를 유지하고 5~8 은 뒤바꾼다.

    5~8 의 행렬은 대각 성분이 0 이고 비대각이 ±1 이라 x·y 축이 교환된다.
    """
    transform = exif_orientation_matrix(WIDTH, HEIGHT, orientation)
    expected = (HEIGHT, WIDTH) if orientation in SWAPPED_ORIENTATIONS else (WIDTH, HEIGHT)

    assert (transform.target_width, transform.target_height) == expected


@pytest.mark.parametrize("orientation", ALL_ORIENTATIONS)
def test_exif_orientation_keeps_the_source_size(orientation: int) -> None:
    transform = exif_orientation_matrix(WIDTH, HEIGHT, orientation)

    assert (transform.source_width, transform.source_height) == (WIDTH, HEIGHT)


@pytest.mark.parametrize("orientation", ALL_ORIENTATIONS)
def test_exif_orientation_preserves_area(orientation: int) -> None:
    """회전·거울 뒤집기뿐이므로 면적이 보존된다. 축척이 섞여 들어가면 깨진다."""
    transform = exif_orientation_matrix(WIDTH, HEIGHT, orientation)

    assert transform.target_width * transform.target_height == WIDTH * HEIGHT


@pytest.mark.parametrize("orientation", [0, 9, -1, 99, 1000])
def test_exif_orientation_falls_back_to_one_for_unknown_values(orientation: int) -> None:
    """현재 동작 — 표에 없는 방향값을 예외 없이 방향 1(변환 없음)로 떨어뜨린다.

    `matrices.get(orientation, matrices[1])` 이다. EXIF 는 파일 메타데이터라 깨져
    있거나 없을 수 있어, 사진을 있는 그대로 보여주는 쪽으로 흘리는 안전한 기본값으로
    읽힌다. 다만 잘못된 방향값이 들어와도 아무 신호가 없다.

    같은 표를 쓰는 rotation_matrix_clockwise 는 반대로 거부한다 — 아래 대조 참고.
    """
    transform = exif_orientation_matrix(WIDTH, HEIGHT, orientation)

    assert transform.matrix == IDENTITY
    assert (transform.target_width, transform.target_height) == (WIDTH, HEIGHT)


def test_exif_orientation_handles_a_square_image() -> None:
    """정사각형이면 뒤바꿔도 크기가 같아, 축 교환 여부를 크기로는 구분할 수 없다."""
    transform = exif_orientation_matrix(200, 200, 6)

    assert (transform.target_width, transform.target_height) == (200, 200)
    assert mapped_corner_set(transform, source_corners(200, 200)) == corner_set(transform)


# ───────────────────────── rotation_matrix_clockwise ─────────────────────────


@pytest.mark.parametrize("degrees", [0, 90, 180, 270])
def test_rotation_accepts_the_four_right_angles(degrees: int) -> None:
    transform = rotation_matrix_clockwise(WIDTH, HEIGHT, degrees)

    assert (transform.source_width, transform.source_height) == (WIDTH, HEIGHT)


@pytest.mark.parametrize("degrees", [1, 45, 89, 91, 360, -90, 271])
def test_rotation_rejects_any_other_angle(degrees: int) -> None:
    """exif_orientation_matrix 와 달리 모르는 값을 삼키지 않고 거부한다."""
    with pytest.raises(ImageValidationError) as exc_info:
        rotation_matrix_clockwise(WIDTH, HEIGHT, degrees)

    assert exc_info.value.code is ImageErrorCode.INVALID_ROTATION


def test_rotation_and_exif_disagree_on_invalid_input() -> None:
    """현재 동작 — 같은 표를 쓰는 두 함수가 잘못된 입력에 다르게 반응한다.

    회전 각도는 우리 API 요청에서 오고 EXIF 방향은 사용자가 올린 파일 메타데이터에서
    온다. 신뢰 수준이 다르니 엄격/관대가 갈리는 것은 설명이 되지만, 두 함수가 같은
    매핑표를 공유한다는 점에서 헷갈릴 여지가 있어 비대칭 자체를 고정해 둔다.
    """
    assert exif_orientation_matrix(WIDTH, HEIGHT, 999).matrix == IDENTITY

    with pytest.raises(ImageValidationError):
        rotation_matrix_clockwise(WIDTH, HEIGHT, 999)


@pytest.mark.parametrize(("degrees", "orientation"), [(0, 1), (90, 6), (180, 3), (270, 8)])
def test_rotation_delegates_to_the_matching_exif_orientation(degrees: int, orientation: int) -> None:
    rotated = rotation_matrix_clockwise(WIDTH, HEIGHT, degrees)
    oriented = exif_orientation_matrix(WIDTH, HEIGHT, orientation)

    assert rotated.matrix == oriented.matrix
    assert (rotated.target_width, rotated.target_height) == (oriented.target_width, oriented.target_height)


def test_rotation_by_zero_changes_nothing() -> None:
    transform = rotation_matrix_clockwise(WIDTH, HEIGHT, 0)

    assert transform.matrix == IDENTITY
    assert (transform.target_width, transform.target_height) == (WIDTH, HEIGHT)


def test_rotating_ninety_degrees_four_times_returns_to_the_start() -> None:
    """⭐ 좌표계 규약을 몰라도 참이어야 하는 성질이다.

    각 단계의 목표 크기를 다음 단계의 원본 크기로 넘겨 네 번 겹친다.
    """
    point = Point(137.5, 42.0)
    current, width, height = point, WIDTH, HEIGHT

    for _ in range(4):
        transform = rotation_matrix_clockwise(width, height, 90)
        current = apply_matrix(transform.matrix, current)
        width, height = transform.target_width, transform.target_height

    assert_same_point(current, point)
    assert (width, height) == (WIDTH, HEIGHT)


def test_rotating_one_hundred_eighty_degrees_twice_returns_to_the_start() -> None:
    point = Point(137.5, 42.0)
    first = rotation_matrix_clockwise(WIDTH, HEIGHT, 180)
    second = rotation_matrix_clockwise(first.target_width, first.target_height, 180)

    assert_same_point(apply_matrix(second.matrix, apply_matrix(first.matrix, point)), point)
    assert (second.target_width, second.target_height) == (WIDTH, HEIGHT)


def test_rotating_ninety_then_two_hundred_seventy_returns_to_the_start() -> None:
    point = Point(137.5, 42.0)
    first = rotation_matrix_clockwise(WIDTH, HEIGHT, 90)
    second = rotation_matrix_clockwise(first.target_width, first.target_height, 270)

    assert_same_point(apply_matrix(second.matrix, apply_matrix(first.matrix, point)), point)
    assert (second.target_width, second.target_height) == (WIDTH, HEIGHT)


# ──────────────────────────────── resize_matrix ────────────────────────────────


@pytest.mark.parametrize(
    "sizes",
    [(0, 300, 200, 150), (400, 0, 200, 150), (400, 300, 0, 150), (400, 300, 200, 0), (-1, 300, 200, 150)],
)
def test_resize_rejects_non_positive_dimensions(sizes: tuple[int, int, int, int]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        resize_matrix(*sizes)


def test_resize_to_the_same_size_is_the_identity() -> None:
    transform = resize_matrix(WIDTH, HEIGHT, WIDTH, HEIGHT)

    assert transform.matrix == IDENTITY


def test_resize_round_trips_through_a_shrink_and_a_matching_grow() -> None:
    """축소 행렬과 확대 행렬을 겹치면 제자리다."""
    point = Point(137.5, 42.0)
    down = resize_matrix(WIDTH, HEIGHT, 200, 150)
    up = resize_matrix(200, 150, WIDTH, HEIGHT)

    assert_same_point(apply_matrix(up.matrix, apply_matrix(down.matrix, point)), point)


@pytest.mark.parametrize("point", [Point(0.0, 0.0), Point(137.5, 42.0), Point(400.0, 300.0)])
def test_resize_inverse_undoes_the_matrix(point: Point) -> None:
    transform = resize_matrix(WIDTH, HEIGHT, 200, 150)

    assert_same_point(round_trip(transform, point), point)


def test_resize_scales_each_axis_independently() -> None:
    """가로세로 비율이 다르면 각 축이 따로 스케일된다.

    구체적 좌표를 박지 않고, 원점과 오른쪽 아래 모서리가 목표 모서리로 간다는
    성질로 확인한다.
    """
    transform = resize_matrix(WIDTH, HEIGHT, 100, 900)

    assert_same_point(apply_matrix(transform.matrix, Point(0.0, 0.0)), Point(0.0, 0.0))
    assert_same_point(apply_matrix(transform.matrix, Point(float(WIDTH), float(HEIGHT))), Point(100.0, 900.0))


def test_resize_keeps_the_origin_fixed() -> None:
    """축척만 있고 이동이 없으므로 원점은 움직이지 않는다."""
    transform = resize_matrix(WIDTH, HEIGHT, 37, 911)

    assert_same_point(apply_matrix(transform.matrix, Point(0.0, 0.0)), Point(0.0, 0.0))


def test_resize_records_both_sizes() -> None:
    transform = resize_matrix(WIDTH, HEIGHT, 200, 150)

    assert (transform.source_width, transform.source_height) == (WIDTH, HEIGHT)
    assert (transform.target_width, transform.target_height) == (200, 150)


def test_resize_maps_source_corners_onto_target_corners() -> None:
    transform = resize_matrix(WIDTH, HEIGHT, 200, 150)

    assert mapped_corner_set(transform, source_corners()) == corner_set(transform)


# ─────────────────────────────── perspective_matrix ───────────────────────────────


def test_perspective_maps_the_four_vertices_onto_the_target_rectangle() -> None:
    """⭐ 손 계산 없이 확인할 수 있는 핵심 성질.

    꼭짓점 순서는 코드의 destination 순서와 같은 TL, TR, BR, BL 이다.
    """
    transform = perspective_matrix(CLOCKWISE_QUAD, target_width=200, target_height=150)
    expected = [Point(0.0, 0.0), Point(200.0, 0.0), Point(200.0, 150.0), Point(0.0, 150.0)]

    for vertex, target in zip(CLOCKWISE_QUAD, expected, strict=True):
        assert_same_point(apply_matrix(transform.matrix, vertex), target, tolerance=1e-6)


@pytest.mark.parametrize("point", [Point(100.0, 90.0), Point(15.0, 25.0), Point(200.0, 160.0)])
def test_perspective_inverse_undoes_the_matrix(point: Point) -> None:
    transform = perspective_matrix(CLOCKWISE_QUAD, target_width=200, target_height=150)

    assert_same_point(round_trip(transform, point), point, tolerance=1e-6)


def test_perspective_without_a_border_targets_exactly_the_requested_size() -> None:
    transform = perspective_matrix(CLOCKWISE_QUAD, target_width=200, target_height=150)

    assert (transform.target_width, transform.target_height) == (200, 150)


def test_perspective_border_pads_both_sides_of_each_axis() -> None:
    """border 는 네 변에 같은 여백을 두므로 목표 크기가 각 축으로 2배씩 늘어난다."""
    border = 12
    transform = perspective_matrix(CLOCKWISE_QUAD, target_width=200, target_height=150, border=border)

    assert (transform.target_width, transform.target_height) == (200 + 2 * border, 150 + 2 * border)


def test_perspective_border_shifts_the_rectangle_inward() -> None:
    """여백이 있으면 첫 꼭짓점이 (0,0) 이 아니라 (border, border) 로 간다."""
    border = 12
    transform = perspective_matrix(CLOCKWISE_QUAD, target_width=200, target_height=150, border=border)

    assert_same_point(
        apply_matrix(transform.matrix, CLOCKWISE_QUAD[0]),
        Point(float(border), float(border)),
        tolerance=1e-6,
    )
    assert_same_point(
        apply_matrix(transform.matrix, CLOCKWISE_QUAD[2]),
        Point(float(border + 200), float(border + 150)),
        tolerance=1e-6,
    )


def test_perspective_on_an_axis_aligned_rectangle_is_a_plain_scale() -> None:
    """이미 반듯한 사각형을 넣으면 원근 성분이 없는 단순 축척이 된다.

    구체적 좌표 대신, 마지막 행이 (0, 0, 1) 에 가깝다는 성질로 확인한다.
    """
    rectangle: Quad = (Point(0.0, 0.0), Point(100.0, 0.0), Point(100.0, 50.0), Point(0.0, 50.0))
    transform = perspective_matrix(rectangle, target_width=200, target_height=100)

    assert transform.matrix[6] == pytest.approx(0.0, abs=1e-9)
    assert transform.matrix[7] == pytest.approx(0.0, abs=1e-9)
    assert transform.matrix[8] == pytest.approx(1.0, abs=1e-9)


def test_perspective_rejects_a_concave_quadrilateral() -> None:
    concave: Quad = (Point(0.0, 0.0), Point(100.0, 0.0), Point(10.0, 10.0), Point(0.0, 100.0))

    with pytest.raises(ValueError, match="convex quadrilateral"):
        perspective_matrix(concave, target_width=200, target_height=150)


def test_perspective_rejects_a_quadrilateral_below_the_minimum_area() -> None:
    """minimum_area 는 16.0 이다. 넓이 9 인 사각형은 거부된다."""
    tiny: Quad = (Point(0.0, 0.0), Point(3.0, 0.0), Point(3.0, 3.0), Point(0.0, 3.0))

    with pytest.raises(ValueError, match="convex quadrilateral"):
        perspective_matrix(tiny, target_width=200, target_height=150)


def test_perspective_accepts_a_quadrilateral_at_the_minimum_area() -> None:
    """넓이 16 은 `>=` 라 통과한다."""
    boundary: Quad = (Point(0.0, 0.0), Point(4.0, 0.0), Point(4.0, 4.0), Point(0.0, 4.0))

    transform = perspective_matrix(boundary, target_width=200, target_height=150)

    assert (transform.target_width, transform.target_height) == (200, 150)


@pytest.mark.parametrize(("target_width", "target_height"), [(1, 150), (200, 1), (0, 150), (1, 1)])
def test_perspective_rejects_a_target_smaller_than_two_pixels(target_width: int, target_height: int) -> None:
    with pytest.raises(ValueError, match="convex quadrilateral"):
        perspective_matrix(CLOCKWISE_QUAD, target_width=target_width, target_height=target_height)


@pytest.mark.parametrize("border", [-1, -10])
def test_perspective_rejects_a_negative_border(border: int) -> None:
    with pytest.raises(ValueError, match="convex quadrilateral"):
        perspective_matrix(CLOCKWISE_QUAD, target_width=200, target_height=150, border=border)


def test_perspective_source_size_comes_from_the_vertices_not_the_image() -> None:
    """현재 동작 — source 크기를 꼭짓점 x·y 의 최댓값을 올림해서 정한다.

    사각형이 이미지 왼쪽 위 구석에 있으면 원본 이미지보다 작은 값이 나온다.

    유일한 호출부(_rectified_candidate, preprocess.py:1314)가 반환된 transform 을
    실제 이미지 크기로 다시 만들어 이 값을 **버린다.** 그래서 실사용에는 영향이 없다.
    다만 이 함수를 직접 쓰면 오해할 수 있는 값이라 사실을 남긴다.
    """
    corner_quad: Quad = (Point(0.0, 0.0), Point(30.0, 0.0), Point(30.0, 20.0), Point(0.0, 20.0))

    transform = perspective_matrix(corner_quad, target_width=200, target_height=150)

    assert (transform.source_width, transform.source_height) == (30, 20)


def test_perspective_source_size_rounds_fractional_vertices_up() -> None:
    fractional: Quad = (Point(0.0, 0.0), Point(30.2, 0.0), Point(30.2, 20.7), Point(0.0, 20.7))

    transform = perspective_matrix(fractional, target_width=200, target_height=150)

    assert (transform.source_width, transform.source_height) == (31, 21)


def test_perspective_does_not_validate_the_vertex_winding_order() -> None:
    """현재 동작 — 꼭짓점 감김 방향을 검사하지 않는다.

    `_is_valid_quad` 가 넓이의 **절댓값**을 보므로 반시계 순서도 통과한다. 통과한 뒤에는
    꼭짓점이 다른 목표 모서리로 가서 결과가 거울처럼 뒤집힌다.

    유일한 호출부는 `_order_quad` 를 거쳐 넘긴다. 그 함수가 `_signed_area` 부호로
    감김 방향을 정규화해 시계방향(양의 면적)으로 맞추므로 규약이 보장된다.
    검사가 없는 것은 호출부가 이미 보장하기 때문으로 읽힌다.
    """
    reversed_quad: Quad = (
        CLOCKWISE_QUAD[0],
        CLOCKWISE_QUAD[3],
        CLOCKWISE_QUAD[2],
        CLOCKWISE_QUAD[1],
    )

    transform = perspective_matrix(reversed_quad, target_width=200, target_height=150)

    # 거부되지 않고, 두 번째 꼭짓점이 오른쪽 위로 간다 — 시계방향 입력이었다면 왼쪽 아래다.
    assert_same_point(
        apply_matrix(transform.matrix, reversed_quad[1]),
        Point(200.0, 0.0),
        tolerance=1e-6,
    )


def test_perspective_still_round_trips_with_a_border() -> None:
    """여백이 붙어도 왕복은 유지된다."""
    transform = perspective_matrix(CLOCKWISE_QUAD, target_width=200, target_height=150, border=12)
    point = Point(100.0, 90.0)

    assert_same_point(round_trip(transform, point), point, tolerance=1e-6)
