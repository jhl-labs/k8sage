"""단위 파서/포매터/막대 렌더링 테스트 (kubectl 없이 순수 함수만 검증)."""
from k8sage.cli import (
    BAR_GAP,
    BAR_LIM,
    BAR_REQ,
    BAR_USE,
    fmt_bytes,
    fmt_cpu,
    parse_cpu,
    parse_mem,
    render_bar,
    want_color,
)


def test_parse_cpu():
    assert parse_cpu("500m") == 500
    assert parse_cpu("2") == 2000
    assert parse_cpu("1.5") == 1500
    assert parse_cpu("250000000n") == 250  # nanocores -> millicores
    assert parse_cpu(None) == 0
    assert parse_cpu("") == 0


def test_parse_mem():
    assert parse_mem("128Mi") == 128 * 1024**2
    assert parse_mem("1Gi") == 1024**3
    assert parse_mem("512") == 512
    assert parse_mem("1M") == 1000**2
    assert parse_mem(None) == 0
    assert parse_mem("garbage") == 0


def test_fmt_cpu():
    assert fmt_cpu(0) == "-"
    assert fmt_cpu(250) == "250m"
    assert fmt_cpu(2000) == "2 cores"
    assert fmt_cpu(1500) == "1.5 cores"


def test_fmt_bytes():
    assert fmt_bytes(0) == "-"
    assert fmt_bytes(1024) == "1Ki"
    assert fmt_bytes(1024**3) == "1Gi"


def test_render_bar_layers():
    # use <= req <= lim <= total -> 네 종류 문자가 순서대로 나타난다.
    bar = render_bar(usage=10, request=20, limit=30, total=40, width=8)
    assert len(bar) == 8
    assert set(bar) <= {BAR_USE, BAR_REQ, BAR_LIM, BAR_GAP}
    # 앞쪽은 use, 뒤쪽은 gap 이어야 한다.
    assert bar[0] == BAR_USE
    assert bar[-1] == BAR_GAP


def test_render_bar_no_capacity():
    assert render_bar(1, 1, 1, total=0, width=5) == BAR_GAP * 5


def test_want_color_modes():
    assert want_color("always") is True
    assert want_color("never") is False
