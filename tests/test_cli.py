"""k8sage 전체 동작 테스트. kubectl/subprocess 는 모두 모킹한다.

목표: 분기 포함 커버리지 99% 이상.
"""
import json
import subprocess
from importlib.metadata import PackageNotFoundError

import pytest

from k8sage import cli


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
class FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def make_stat(**kw) -> cli.NsStat:
    s = cli.NsStat()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
def test_palette_enabled_wraps():
    p = cli.Palette(True)
    for meth in (p.use, p.req, p.lim, p.head, p.ns, p.dim, p.warn, p.rule):
        out = meth("x")
        assert out.startswith("\033[") and out.endswith("\033[0m") and "x" in out


def test_palette_disabled_passthrough():
    p = cli.Palette(False)
    for meth in (p.use, p.req, p.lim, p.head, p.ns, p.dim, p.warn, p.rule):
        assert meth("x") == "x"


# ---------------------------------------------------------------------------
# want_color
# ---------------------------------------------------------------------------
def test_want_color_always_never():
    assert cli.want_color("always") is True
    assert cli.want_color("never") is False


def test_want_color_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.want_color("auto") is False


def test_want_color_auto_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    assert cli.want_color("auto") is True


def test_want_color_auto_not_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    assert cli.want_color("auto") is False


# ---------------------------------------------------------------------------
# 버전 해석
# ---------------------------------------------------------------------------
def test_git_short_hash_success(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(stdout="abc123\n", returncode=0))
    assert cli._git_short_hash() == "abc123"


def test_git_short_hash_nonzero(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(returncode=1))
    assert cli._git_short_hash() is None


def test_git_short_hash_empty(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(stdout="  \n", returncode=0))
    assert cli._git_short_hash() is None


def test_git_short_hash_no_git(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(cli.subprocess, "run", boom)
    assert cli._git_short_hash() is None


def test_get_version_from_metadata(monkeypatch):
    monkeypatch.setattr("importlib.metadata.version", lambda name: "9.9.9")
    assert cli.get_version() == "9.9.9"


def test_get_version_dev_hash(monkeypatch):
    def not_found(name):
        raise PackageNotFoundError(name)
    monkeypatch.setattr("importlib.metadata.version", not_found)
    monkeypatch.setattr(cli, "_git_short_hash", lambda: "deadbe")
    assert cli.get_version() == "deadbe"


def test_get_version_fallback_static(monkeypatch):
    def not_found(name):
        raise PackageNotFoundError(name)
    monkeypatch.setattr("importlib.metadata.version", not_found)
    monkeypatch.setattr(cli, "_git_short_hash", lambda: None)
    assert cli.get_version() == cli.__version__


def test_banner(monkeypatch):
    monkeypatch.setattr(cli, "get_version", lambda: "1.2.3")
    out = cli.banner(cli.Palette(False))
    assert out == "k8sage 1.2.3"


# ---------------------------------------------------------------------------
# kubectl
# ---------------------------------------------------------------------------
def test_kubectl_success(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(stdout='{"items": [1, 2]}'))
    assert cli.kubectl(["get", "pods"]) == {"items": [1, 2]}


def test_kubectl_not_found(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(cli.subprocess, "run", boom)
    with pytest.raises(SystemExit):
        cli.kubectl(["get", "pods"])


def test_kubectl_called_process_error(monkeypatch):
    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "kubectl", stderr="bad creds")
    monkeypatch.setattr(cli.subprocess, "run", boom)
    with pytest.raises(SystemExit):
        cli.kubectl(["get", "pods"])


def test_kubectl_timeout(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("kubectl", 60)
    monkeypatch.setattr(cli.subprocess, "run", boom)
    with pytest.raises(SystemExit):
        cli.kubectl(["get", "pods"])


# ---------------------------------------------------------------------------
# kubectl_top
# ---------------------------------------------------------------------------
def test_kubectl_top_success(monkeypatch):
    out = "ns1 pod-a 100m 128Mi\nns1 pod-b 2 1Gi\nshortline\n"
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(stdout=out, returncode=0))
    top = cli.kubectl_top()
    assert top[("ns1", "pod-a")] == (100, 128 * 1024**2)
    assert top[("ns1", "pod-b")] == (2000, 1024**3)
    # "shortline" 은 컬럼이 부족하므로 무시
    assert len(top) == 2


def test_kubectl_top_nonzero(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(returncode=1))
    assert cli.kubectl_top() is None


def test_kubectl_top_no_metrics(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(cli.subprocess, "run", boom)
    assert cli.kubectl_top() is None


# ---------------------------------------------------------------------------
# 파서 / 포매터 (test_parsers.py 와 일부 중복 — 경계값 추가)
# ---------------------------------------------------------------------------
def test_parse_cpu_variants():
    assert cli.parse_cpu("500m") == 500
    assert cli.parse_cpu("2") == 2000
    assert cli.parse_cpu("250000000n") == 250
    assert cli.parse_cpu(None) == 0


def test_parse_mem_variants():
    assert cli.parse_mem("128Mi") == 128 * 1024**2
    assert cli.parse_mem("512") == 512
    assert cli.parse_mem("garbage") == 0
    assert cli.parse_mem(None) == 0


def test_fmt_bytes_exabyte():
    # 루프를 모두 소진한 뒤의 최종 return 분기 (.replace 미적용)
    assert cli.fmt_bytes(1024**6) == "1.0Ei"


def test_fmt_cpu_fractional():
    assert cli.fmt_cpu(1500) == "1.5 cores"


# ---------------------------------------------------------------------------
# 막대 렌더링
# ---------------------------------------------------------------------------
def test_render_bar_layers():
    bar = cli.render_bar(10, 20, 30, 40, width=8)
    assert len(bar) == 8
    assert bar[0] == cli.BAR_USE
    assert bar[-1] == cli.BAR_GAP
    assert cli.BAR_REQ in bar and cli.BAR_LIM in bar


def test_render_bar_no_total():
    assert cli.render_bar(1, 1, 1, 0, width=5) == cli.BAR_GAP * 5


def test_render_bar_overcommit_all_lim():
    bar = cli.render_bar(0, 0, 100, 50, width=6)
    assert set(bar) == {cli.BAR_LIM}


def test_colorize_bar_off():
    bar = cli.render_bar(10, 20, 30, 40)
    assert cli.colorize_bar(bar, cli.Palette(False)) == bar


def test_colorize_bar_on_known_and_unknown():
    # 'X' 는 _BAR_COLOR 에 없어 무색 구간(else 분기)을, █ 는 색 구간을 탄다.
    out = cli.colorize_bar("XX" + cli.BAR_USE * 2, cli.Palette(True))
    assert "XX" in out
    assert "\033[92m" in out


def test_pct():
    assert cli._pct(0, 100) == "-"
    assert cli._pct(50, 0) == "-"
    assert cli._pct(50, 100) == "50%"
    assert cli._pct(150, 100) == "150%!"


def test_color_pct():
    pal = cli.Palette(False)
    assert cli._color_pct("150%!", pal, pal.use) == "150%!"
    assert cli._color_pct("50%", pal, pal.use) == "50%"


# ---------------------------------------------------------------------------
# cluster_capacity
# ---------------------------------------------------------------------------
def test_cluster_capacity(monkeypatch):
    nodes = {"items": [
        {"status": {"allocatable": {"cpu": "4", "memory": "8Gi"}}},
        {"status": {}},  # allocatable 없음 → 0 더해짐
    ]}
    monkeypatch.setattr(cli, "kubectl", lambda args: nodes)
    cpu, mem = cli.cluster_capacity()
    assert cpu == 4000
    assert mem == 8 * 1024**3


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------
def _fake_pods():
    return {"items": [
        {  # 실행 중 + init/일반 컨테이너 + top 매칭
            "metadata": {"namespace": "app", "name": "web"},
            "status": {"phase": "Running"},
            "spec": {
                "containers": [
                    {"resources": {"requests": {"cpu": "250m", "memory": "256Mi"},
                                   "limits": {"cpu": "500m", "memory": "512Mi"}}},
                ],
                "initContainers": [
                    {"resources": {"requests": {"cpu": "50m", "memory": "64Mi"}}},
                ],
            },
        },
        {  # 종료된 Pod → 스킵
            "metadata": {"namespace": "app", "name": "job-done"},
            "status": {"phase": "Succeeded"},
            "spec": {"containers": [{"resources": {"requests": {"cpu": "1"}}}]},
        },
        {  # Pending (top 에 없음) → use 미반영
            "metadata": {"namespace": "infra", "name": "pending"},
            "status": {"phase": "Pending"},
            "spec": {"containers": [{"resources": {"requests": {"cpu": "100m"}}}]},
        },
    ]}


def _fake_pvcs():
    return {"items": [
        {"metadata": {"namespace": "app"},
         "status": {"capacity": {"storage": "10Gi"}}},
        {"metadata": {"namespace": "infra"},  # status 없음 → spec.requests 로 폴백
         "spec": {"resources": {"requests": {"storage": "5Gi"}}}},
    ]}


def test_collect_with_usage(monkeypatch):
    def fake_kubectl(args):
        return _fake_pods() if "pods" in args else _fake_pvcs()
    monkeypatch.setattr(cli, "kubectl", fake_kubectl)
    monkeypatch.setattr(cli, "kubectl_top",
                        lambda: {("app", "web"): (123, 200 * 1024**2)})
    stats = cli.collect(None)
    app = stats["app"]
    assert app.pods == 1
    assert app.cpu_req == 250 + 50          # 일반 + init
    assert app.cpu_lim == 500
    assert app.mem_req == 256 * 1024**2 + 64 * 1024**2
    assert app.cpu_use == 123               # top 매칭분
    assert app.mem_use == 200 * 1024**2
    assert app.pvc_count == 1
    assert app.storage == 10 * 1024**3
    assert stats["infra"].storage == 5 * 1024**3
    assert stats["infra"].cpu_use == 0      # top 미매칭


def test_collect_namespace_scope_no_metrics(monkeypatch):
    captured = {}

    def fake_kubectl(args):
        captured.setdefault("scopes", []).append(args)
        return _fake_pods() if "pods" in args else _fake_pvcs()
    monkeypatch.setattr(cli, "kubectl", fake_kubectl)
    monkeypatch.setattr(cli, "kubectl_top", lambda: None)  # metrics-server 없음
    stats = cli.collect("app")
    # -n <ns> 스코프가 전달됐는지
    assert ["get", "pods", "-n", "app"] in captured["scopes"]
    assert all(s.cpu_use == 0 for s in stats.values())


# ---------------------------------------------------------------------------
# sort_rows / aggregate
# ---------------------------------------------------------------------------
def _sample_stats():
    return {
        "b": make_stat(cpu_req=100, mem_req=10, cpu_use=5, mem_use=50, storage=1),
        "a": make_stat(cpu_req=200, mem_req=20, cpu_use=1, mem_use=10, storage=9),
    }


@pytest.mark.parametrize("key,first", [
    ("ns", "a"),
    ("cpu", "a"),       # cpu_req 큰 순
    ("mem", "a"),
    ("cpu_use", "b"),
    ("mem_use", "b"),
    ("storage", "a"),
    ("unknown", "a"),   # 미지정 → ns 기본
])
def test_sort_rows(key, first):
    rows = cli.sort_rows(_sample_stats(), key)
    assert rows[0][0] == first


def test_aggregate():
    tot = cli.aggregate(_sample_stats())
    assert tot.cpu_req == 300
    assert tot.storage == 10


# ---------------------------------------------------------------------------
# print_table
# ---------------------------------------------------------------------------
def test_print_table_with_usage(capsys):
    stats = {"app": make_stat(pods=2, cpu_req=500, cpu_lim=1000, cpu_use=250,
                              mem_req=1024**3, mem_lim=2 * 1024**3,
                              mem_use=512 * 1024**2, pvc_count=1, storage=10 * 1024**3)}
    cli.print_table(stats, has_usage=True, sort_key="cpu")
    out = capsys.readouterr().out
    assert "NAMESPACE" in out and "CPU(use)" in out and "TOTAL" in out
    assert "usage/request ratio" in out


def test_print_table_usage_zero_requests(capsys):
    # has_usage 이지만 req 가 0 → 비율이 '-' 분기
    stats = {"x": make_stat(pods=1, mem_use=100)}
    cli.print_table(stats, has_usage=True, sort_key="ns")
    out = capsys.readouterr().out
    assert "= -" in out  # cpu/mem 비율 모두 '-'


def test_print_table_no_usage(capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100)}
    cli.print_table(stats, has_usage=False, sort_key="cpu")
    out = capsys.readouterr().out
    assert "metrics-server" in out
    assert "CPU(use)" not in out


# ---------------------------------------------------------------------------
# print_bars
# ---------------------------------------------------------------------------
def test_print_bars_with_usage_and_pvc(capsys):
    stats = {"app": make_stat(pods=3, cpu_req=2000, cpu_lim=8000, cpu_use=1000,
                              mem_req=1024**3, mem_lim=4 * 1024**3,
                              mem_use=512 * 1024**2, pvc_count=2, storage=20 * 1024**3)}
    cli.print_bars(stats, has_usage=True, cap_cpu=4000, cap_mem=8 * 1024**3,
                   sort_key="cpu", pal=cli.Palette(True), width=16)
    out = capsys.readouterr().out
    assert "Whole cluster" in out and "By namespace" in out
    assert "pvc 2" in out
    assert "!" in out  # cpu_lim(8000) > cap_cpu(4000) → overcommit 표시


def test_print_bars_no_usage(capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100, mem_req=1024**2)}
    cli.print_bars(stats, has_usage=False, cap_cpu=4000, cap_mem=8 * 1024**3,
                   sort_key="cpu", pal=cli.Palette(False), width=8)
    out = capsys.readouterr().out
    assert "metrics-server not found" in out


def test_bar_lines_zero_limit_dash():
    # lim 이 0 이면 우측 괄호에 '-' 표시 분기
    lines = cli._bar_lines((0, 100, 0), (0, 0, 0), 1000, 1000, 8, "  ",
                           cli.Palette(False))
    assert any("-" in ln for ln in lines)


# ---------------------------------------------------------------------------
# to_json
# ---------------------------------------------------------------------------
def test_to_json_with_usage():
    stats = {"app": make_stat(pods=1, cpu_req=200, cpu_use=100, mem_req=100,
                              mem_use=50)}
    data = json.loads(cli.to_json(stats, has_usage=True))
    assert data["app"]["cpu_usage_millicores"] == 100
    assert data["app"]["cpu_usage_pct_of_req"] == 50.0


def test_to_json_usage_zero_req_none():
    stats = {"app": make_stat(pods=1, cpu_use=10, mem_use=10)}  # req 0
    data = json.loads(cli.to_json(stats, has_usage=True))
    assert data["app"]["cpu_usage_pct_of_req"] is None
    assert data["app"]["mem_usage_pct_of_req"] is None


def test_to_json_no_usage():
    stats = {"app": make_stat(pods=1, cpu_req=200)}
    data = json.loads(cli.to_json(stats, has_usage=False))
    assert "cpu_usage_millicores" not in data["app"]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def test_main_no_kubectl(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.sys, "argv", ["k8sage"])
    with pytest.raises(SystemExit):
        cli.main()


def test_main_no_namespaces(monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/kubectl")
    monkeypatch.setattr(cli, "collect", lambda ns: {})
    monkeypatch.setattr(cli.sys, "argv", ["k8sage"])
    cli.main()
    assert "조회된 namespace" in capsys.readouterr().out


def test_main_json(monkeypatch, capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100, cpu_use=50)}
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/kubectl")
    monkeypatch.setattr(cli, "collect", lambda ns: stats)
    monkeypatch.setattr(cli.sys, "argv", ["k8sage", "--json"])
    cli.main()
    out = capsys.readouterr().out
    # JSON 모드에는 배너가 없어야 한다.
    assert not out.startswith("k8sage")
    json.loads(out)


def test_main_table(monkeypatch, capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100, cpu_use=50, mem_use=10)}
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/kubectl")
    monkeypatch.setattr(cli, "collect", lambda ns: stats)
    monkeypatch.setattr(cli, "get_version", lambda: "0.0.0")
    monkeypatch.setattr(cli.sys, "argv", ["k8sage", "--table", "--color", "never"])
    cli.main()
    out = capsys.readouterr().out
    assert out.startswith("k8sage 0.0.0")
    assert "NAMESPACE" in out


def test_main_bars(monkeypatch, capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100, cpu_use=50, mem_use=10)}
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/kubectl")
    monkeypatch.setattr(cli, "collect", lambda ns: stats)
    monkeypatch.setattr(cli, "cluster_capacity", lambda: (4000, 8 * 1024**3))
    monkeypatch.setattr(cli, "get_version", lambda: "0.0.0")
    monkeypatch.setattr(cli.sys, "argv", ["k8sage", "--color", "never"])
    cli.main()
    out = capsys.readouterr().out
    assert out.startswith("k8sage 0.0.0")
    assert "Cluster allocatable" in out


def test_main_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_version", lambda: "7.7.7")
    monkeypatch.setattr(cli.sys, "argv", ["k8sage", "--version"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert "7.7.7" in capsys.readouterr().out


# __main__ 진입 모듈 임포트 커버리지
def test_dunder_main_importable():
    import k8sage.__main__ as m
    assert callable(m.main)
