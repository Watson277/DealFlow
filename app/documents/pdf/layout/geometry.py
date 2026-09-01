"""Geometry helpers using top-left-origin PDF coordinates."""

from app.documents.pdf.models import BoundingBox


def width(bbox: BoundingBox) -> float:
    return bbox.x1 - bbox.x0


def height(bbox: BoundingBox) -> float:
    return bbox.y1 - bbox.y0


def area(bbox: BoundingBox) -> float:
    return max(0.0, width(bbox)) * max(0.0, height(bbox))


def intersection_area(first: BoundingBox, second: BoundingBox) -> float:
    overlap_width = max(0.0, min(first.x1, second.x1) - max(first.x0, second.x0))
    overlap_height = max(0.0, min(first.y1, second.y1) - max(first.y0, second.y0))
    return overlap_width * overlap_height


def smaller_box_overlap(first: BoundingBox, second: BoundingBox) -> float:
    smaller_area = min(area(first), area(second))
    if smaller_area <= 0:
        return 0.0
    return intersection_area(first, second) / smaller_area


def first_box_overlap(first: BoundingBox, second: BoundingBox) -> float:
    first_area = area(first)
    if first_area <= 0:
        return 0.0
    return intersection_area(first, second) / first_area


def horizontal_overlap_ratio(first: BoundingBox, second: BoundingBox) -> float:
    smaller_width = min(width(first), width(second))
    if smaller_width <= 0:
        return 0.0
    overlap = max(0.0, min(first.x1, second.x1) - max(first.x0, second.x0))
    return overlap / smaller_width


def union(first: BoundingBox, second: BoundingBox) -> BoundingBox:
    return BoundingBox(
        x0=min(first.x0, second.x0),
        y0=min(first.y0, second.y0),
        x1=max(first.x1, second.x1),
        y1=max(first.y1, second.y1),
    )
