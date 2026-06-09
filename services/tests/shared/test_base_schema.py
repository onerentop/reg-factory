from shared.base_schema import (
    PaginationParams,
    PaginatedResponse,
    ApiResponse,
    ErrorResponse,
)


def test_pagination_defaults():
    p = PaginationParams()
    assert p.page == 1
    assert p.page_size == 20


def test_pagination_clamp():
    p = PaginationParams(page=0, page_size=200)
    assert p.page == 1
    assert p.page_size == 100


def test_pagination_offset():
    p = PaginationParams(page=3, page_size=10)
    assert p.offset == 20


def test_api_response_success():
    resp = ApiResponse(data={"key": "value"})
    assert resp.success is True
    assert resp.data == {"key": "value"}


def test_paginated_response():
    resp = PaginatedResponse(
        items=["a", "b"],
        total=10,
        page=1,
        page_size=2,
    )
    assert resp.total_pages == 5
    assert resp.has_next is True
    assert resp.has_prev is False


def test_error_response():
    resp = ErrorResponse(code="NOT_FOUND", message="not found")
    assert resp.success is False
