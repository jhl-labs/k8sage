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
# kubectl_raw / pvc_usage
# ---------------------------------------------------------------------------
def test_kubectl_raw_success(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(stdout='{"ok": 1}', returncode=0))
    assert cli.kubectl_raw("/x") == {"ok": 1}


def test_kubectl_raw_nonzero(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(returncode=1))
    assert cli.kubectl_raw("/x") is None


def test_kubectl_raw_not_found(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(cli.subprocess, "run", boom)
    assert cli.kubectl_raw("/x") is None


def test_kubectl_raw_bad_json(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: FakeProc(stdout="not json", returncode=0))
    assert cli.kubectl_raw("/x") is None


_SUMMARY = {"pods": [
    {"volume": [
        {"pvcRef": {"namespace": "app", "name": "p1"},
         "usedBytes": 100, "capacityBytes": 1000},
        {"pvcRef": {"namespace": "app", "name": "p2"},
         "usedBytes": 50, "capacityBytes": 500},
        {"name": "emptydir-no-pvcref"},                       # pvcRef 없음 → skip
        {"pvcRef": {"namespace": "app"},                      # ns 만, used None → skip
         "usedBytes": None, "capacityBytes": 1},
        {"pvcRef": {"name": "q"},                             # namespace 없음 → skip
         "usedBytes": 1, "capacityBytes": 2},
    ]},
    {},  # volume 키 없는 pod
]}


def test_pvc_usage_success(monkeypatch):
    monkeypatch.setattr(cli, "kubectl",
                        lambda args: {"items": [{"metadata": {"name": "n1"}}]})
    monkeypatch.setattr(cli, "kubectl_raw", lambda path: _SUMMARY)
    usage = cli.pvc_usage()
    assert usage == {"app": (150, 1500)}


def test_pvc_usage_no_access(monkeypatch):
    # 모든 노드 proxy 실패(RBAC 등) → None
    monkeypatch.setattr(cli, "kubectl",
                        lambda args: {"items": [{"metadata": {"name": "n1"}}]})
    monkeypatch.setattr(cli, "kubectl_raw", lambda path: None)
    assert cli.pvc_usage() is None


def test_pvc_usage_dedupes_node_rootfs(monkeypatch):
    # app 의 두 PVC 는 노드 루트 fs(cap==1000) 공유 → 한 번만(노드 fs used=800).
    # db 의 PVC 는 별도 볼륨(cap=500) → 그대로 합산.
    summary = {
        "node": {"fs": {"capacityBytes": 1000, "usedBytes": 800}},
        "pods": [{"volume": [
            {"pvcRef": {"namespace": "app", "name": "a"},
             "usedBytes": 790, "capacityBytes": 1000},
            {"pvcRef": {"namespace": "app", "name": "b"},
             "usedBytes": 795, "capacityBytes": 1000},
            {"pvcRef": {"namespace": "db", "name": "c"},
             "usedBytes": 100, "capacityBytes": 500},
        ]}],
    }
    monkeypatch.setattr(cli, "kubectl",
                        lambda args: {"items": [{"metadata": {"name": "n1"}}]})
    monkeypatch.setattr(cli, "kubectl_raw", lambda path: summary)
    assert cli.pvc_usage() == {"app": (800, 1000), "db": (100, 500)}


def test_pvc_usage_rootfs_without_node_used(monkeypatch):
    # 노드 fs capacity 는 있으나 usedBytes 가 없으면 볼륨의 used 를 사용
    summary = {
        "node": {"fs": {"capacityBytes": 1000}},
        "pods": [{"volume": [
            {"pvcRef": {"namespace": "app", "name": "a"},
             "usedBytes": 790, "capacityBytes": 1000},
        ]}],
    }
    monkeypatch.setattr(cli, "kubectl",
                        lambda args: {"items": [{"metadata": {"name": "n1"}}]})
    monkeypatch.setattr(cli, "kubectl_raw", lambda path: summary)
    assert cli.pvc_usage() == {"app": (790, 1000)}


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


def test_render_storage_bar():
    assert cli.render_storage_bar(0, 100, 8) == cli.BAR_GAP * 8     # value 0
    assert cli.render_storage_bar(50, 0, 8) == cli.BAR_GAP * 8      # total 0
    assert cli.render_storage_bar(50, 100, 8) == cli.BAR_USE * 4 + cli.BAR_GAP * 4
    assert cli.render_storage_bar(200, 100, 8) == cli.BAR_USE * 8   # value>total → cap


def test_colorize_bar_storage_map():
    bar = cli.render_storage_bar(50, 100, 4)
    out = cli.colorize_bar(bar, cli.Palette(True), cli._STO_COLOR)
    assert f"\033[{cli.STO_CODE}m" in out  # storage 파랑 코드


def test_storage_usage_line():
    # used 5Gi / cap 10Gi -> 50%, 총 용량은 괄호에
    line = cli._storage_usage_line(5 * 1024**3, 10 * 1024**3, 2, 16, "  ",
                                   cli.Palette(False))
    assert "STO" in line and "5Gi" in line and "10Gi" in line
    assert "50%" in line and "pvc 2" in line


def test_storage_req_line():
    line = cli._storage_req_line(6 * 1024**3, 2, 6 * 1024**3, 16, "  ",
                                 cli.Palette(False))
    assert "STO" in line and "6Gi" in line
    assert "requested (no live usage)" in line and "pvc 2" in line


def test_pct():
    assert cli._pct(0, 100) == "-"
    assert cli._pct(50, 0) == "-"
    assert cli._pct(50, 100) == "50%"
    assert cli._pct(150, 100) == "150%!"


def test_color_pct():
    pal = cli.Palette(False)
    assert cli._color_pct("150%!", pal, pal.use) == "150%!"
    assert cli._color_pct("50%", pal, pal.use) == "50%"


def test_pct_of():
    assert cli._pct_of(0, 100) == "-"
    assert cli._pct_of(50, 0) == "-"
    assert cli._pct_of(50, 100) == "50%"
    assert cli._pct_of(150, 100) == "150%"  # 부호('!') 없이 정수%


def test_bar_lines_show_req_lim_pct():
    # req 50/100=50%, lim 200/100=200% 가 CPU 줄에 표시된다
    lines = cli._bar_lines((0, 50, 200), (0, 0, 0), 100, 1000, 16, "  ",
                           cli.Palette(False))
    assert "50%" in lines[0] and "200%" in lines[0]


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


def test_node_capacities(monkeypatch):
    nodes = {"items": [
        {"metadata": {"name": "node-a"},
         "status": {"allocatable": {"cpu": "2", "memory": "4Gi"}}},
        {"metadata": {},
         "status": {"allocatable": {"cpu": "1", "memory": "1Gi"}}},
    ]}
    monkeypatch.setattr(cli, "kubectl", lambda args: nodes)
    assert cli.node_capacities() == {"node-a": (2000, 4 * 1024**3)}


def test_node_filesystems(monkeypatch):
    def fake_raw(path):
        if "node-a" in path:
            return {"node": {"fs": {"usedBytes": 10, "capacityBytes": 100}}}
        if "node-b" in path:
            return {"node": {"fs": {"usedBytes": 10}}}
        return None

    monkeypatch.setattr(cli, "kubectl_raw", fake_raw)
    assert cli.node_filesystems(["node-a", "node-b", "node-c"]) == {"node-a": (10, 100)}


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
    # 실사용량: app 은 stats 에 있어 반영, ghost 는 없어 건너뜀
    monkeypatch.setattr(cli, "pvc_usage",
                        lambda: {"app": (8 * 1024**3, 10 * 1024**3),
                                 "ghost": (1, 1)})
    stats = cli.collect(None)
    app = stats["app"]
    assert app.stor_used == 8 * 1024**3
    assert app.stor_cap == 10 * 1024**3
    assert "ghost" not in stats
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
    monkeypatch.setattr(cli, "pvc_usage", lambda: None)    # storage 사용량 미접근
    stats = cli.collect("app")
    # -n <ns> 스코프가 전달됐는지
    assert ["get", "pods", "-n", "app"] in captured["scopes"]
    assert all(s.cpu_use == 0 for s in stats.values())
    assert all(s.stor_cap == 0 for s in stats.values())


def test_collect_nodes_with_usage(monkeypatch):
    pods = _fake_pods()
    pods["items"][0]["spec"]["nodeName"] = "node-a"
    pods["items"][2]["spec"]["nodeName"] = "node-b"
    monkeypatch.setattr(cli, "kubectl", lambda args: pods)
    monkeypatch.setattr(cli, "kubectl_top",
                        lambda: {("app", "web"): (123, 200 * 1024**2)})
    monkeypatch.setattr(cli, "collect_node_storage",
                        lambda ns: [("node-a", 2, 15 * 1024**3)])

    stats = cli.collect_nodes(None)

    assert stats["node-a"].pods == 1
    assert stats["node-a"].cpu_req == 300
    assert stats["node-a"].cpu_use == 123
    assert stats["node-a"].pvc_count == 2
    assert stats["node-a"].storage == 15 * 1024**3
    assert stats["node-b"].pods == 1
    assert stats["node-b"].cpu_req == 100


def test_collect_nodes_skips_unscheduled(monkeypatch):
    pods = _fake_pods()
    monkeypatch.setattr(cli, "kubectl", lambda args: pods)
    monkeypatch.setattr(cli, "kubectl_top", lambda: None)
    monkeypatch.setattr(cli, "collect_node_storage", lambda ns: [])
    assert cli.collect_nodes(None) == {}


def test_pv_node_name_none():
    assert cli._pv_node_name({"spec": {}}) is None
    assert cli._pv_node_name({"spec": {"nodeAffinity": {"required": {
        "nodeSelectorTerms": [{"matchExpressions": [
            {"key": "other", "values": ["node-a"]},
            {"key": "kubernetes.io/hostname", "values": []},
        ]}],
    }}}}) is None


def test_collect_node_storage_selected_node(monkeypatch):
    pvcs = {"items": [
        {"metadata": {"namespace": "app",
                      "annotations": {"volume.kubernetes.io/selected-node": "node-a"}},
         "status": {"capacity": {"storage": "10Gi"}}},
        {"metadata": {"namespace": "app",
                      "annotations": {"volume.kubernetes.io/selected-node": "node-a"}},
         "spec": {"resources": {"requests": {"storage": "5Gi"}}}},
    ]}
    monkeypatch.setattr(cli, "kubectl", lambda args: pvcs)

    assert cli.collect_node_storage(None) == [("node-a", 2, 15 * 1024**3)]


def test_collect_namespace_storage_fs(monkeypatch):
    pvcs = {"items": [
        {"metadata": {"namespace": "app",
                      "annotations": {"volume.kubernetes.io/selected-node": "node-a"}},
         "status": {"capacity": {"storage": "10Gi"}}},
        {"metadata": {"namespace": "app",
                      "annotations": {"volume.kubernetes.io/selected-node": "node-a"}},
         "status": {"capacity": {"storage": "5Gi"}}},
        {"metadata": {"namespace": "infra",
                      "annotations": {"volume.kubernetes.io/selected-node": "node-b"}},
         "status": {"capacity": {"storage": "1Gi"}}},
    ]}
    node_fs = {
        "node-a": (20 * 1024**3, 100 * 1024**3),
        "node-b": (5 * 1024**3, 50 * 1024**3),
    }
    monkeypatch.setattr(cli, "kubectl", lambda args: pvcs)

    assert cli.collect_namespace_storage_fs(None, node_fs) == {
        "app": (20 * 1024**3, 100 * 1024**3),
        "infra": (5 * 1024**3, 50 * 1024**3),
    }


def test_collect_node_storage_pv_node_affinity(monkeypatch):
    pvcs = {"items": [
        {"metadata": {"namespace": "app", "annotations": {}},
         "spec": {"volumeName": "pv-a", "resources": {"requests": {"storage": "2Gi"}}}},
    ]}
    pvs = {"items": [
        {"metadata": {"name": "pv-a"},
         "spec": {"nodeAffinity": {"required": {"nodeSelectorTerms": [
             {"matchExpressions": [
                 {"key": "kubernetes.io/hostname", "values": ["node-b"]},
             ]},
         ]}}}},
    ]}

    def fake_kubectl(args):
        return pvs if args[:2] == ["get", "pv"] else pvcs

    monkeypatch.setattr(cli, "kubectl", fake_kubectl)
    assert cli.collect_node_storage(None) == [("node-b", 1, 2 * 1024**3)]


def test_pvc_node_rows_skips_unusable_pvcs(monkeypatch):
    pvcs = {"items": [
        {"metadata": {"annotations": {"volume.kubernetes.io/selected-node": "node-a"}},
         "status": {"capacity": {"storage": "1Gi"}}},
        {"metadata": {"namespace": "app", "annotations": {}},
         "status": {"capacity": {}}},
        {"metadata": {"namespace": "app", "annotations": {}},
         "spec": {"volumeName": "pv-missing", "resources": {"requests": {"storage": "1Gi"}}}},
    ]}
    pvs = {"items": [{"metadata": {"name": "other-pv"}, "spec": {}}]}

    def fake_kubectl(args):
        return pvs if args[:2] == ["get", "pv"] else pvcs

    monkeypatch.setattr(cli, "kubectl", fake_kubectl)
    assert cli._pvc_node_rows(None) == []


def test_collect_namespace_storage_fs_ignores_unknown_node(monkeypatch):
    pvcs = {"items": [
        {"metadata": {"namespace": "app",
                      "annotations": {"volume.kubernetes.io/selected-node": "node-missing"}},
         "status": {"capacity": {"storage": "1Gi"}}},
    ]}
    monkeypatch.setattr(cli, "kubectl", lambda args: pvcs)
    assert cli.collect_namespace_storage_fs(None, {}) == {}


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
    # stor_cap 없음 → 요청-용량 폴백 STO 라인
    assert "STO" in out and "requested (no live usage)" in out
    assert "!" in out  # cpu_lim(8000) > cap_cpu(4000) → overcommit 표시


def test_print_bars_namespace_storage_backing_fs(capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100, pvc_count=2,
                              storage=20 * 1024**3)}
    cli.print_bars(stats, has_usage=True, cap_cpu=4000, cap_mem=8 * 1024**3,
                   sort_key="cpu", pal=cli.Palette(False), width=16,
                   ns_storage_fs={"app": (30 * 1024**3, 100 * 1024**3)})
    out = capsys.readouterr().out
    assert "20Gi" in out and "20%" in out and "100Gi backing fs" in out
    assert "requested (no live usage)" not in out


def test_print_bars_with_node_section(capsys):
    stats = {"app": make_stat(pods=1, cpu_req=1000, cpu_use=500,
                              mem_req=1024**3, mem_use=512 * 1024**2)}
    nodes = {"node-a": make_stat(pods=1, cpu_req=1000, cpu_use=500,
                                 mem_req=1024**3, mem_use=512 * 1024**2,
                                 pvc_count=2, storage=10 * 1024**3)}
    caps = {"node-a": (2000, 2 * 1024**3)}
    fs = {"node-a": (25 * 1024**3, 100 * 1024**3)}

    cli.print_bars(stats, has_usage=True, cap_cpu=4000, cap_mem=8 * 1024**3,
                   sort_key="cpu", pal=cli.Palette(False), width=16,
                   node_stats=nodes, node_caps=caps, node_fs=fs)
    out = capsys.readouterr().out

    assert out.index("Whole cluster") < out.index("By node") < out.index("By namespace")
    assert "node-a" in out and "alloc" in out
    assert "50%" in out  # node-a CPU request is 1000m / 2000m allocatable
    assert "10Gi" in out and "100Gi fs" in out and "pvc 2 · requested" in out


def test_node_storage_line_without_fs():
    line = cli._node_storage_line(5 * 1024**3, 1, None, 10 * 1024**3, 8, "  ",
                                  cli.Palette(False))
    assert "requested (no live usage)" in line


def test_print_bars_empty_node_section(capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100)}
    cli.print_bars(stats, has_usage=True, cap_cpu=1000, cap_mem=1024**3,
                   sort_key="cpu", pal=cli.Palette(False), width=8,
                   node_stats={}, node_caps={})
    assert "By node" not in capsys.readouterr().out


def test_print_bars_storage_live_usage(capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100, cpu_use=10, mem_use=5,
                              pvc_count=2, storage=6 * 1024**3,
                              stor_used=5 * 1024**3, stor_cap=10 * 1024**3)}
    cli.print_bars(stats, has_usage=True, cap_cpu=4000, cap_mem=8 * 1024**3,
                   sort_key="cpu", pal=cli.Palette(False), width=16)
    out = capsys.readouterr().out
    # 실사용 STO 라인: used/cap 와 실제 % 표시
    assert "STO" in out and "5Gi" in out and "10Gi" in out and "50%" in out
    assert "requested (no live usage)" not in out


def test_print_bars_no_usage(capsys):
    stats = {"app": make_stat(pods=1, cpu_req=100, mem_req=1024**2)}
    cli.print_bars(stats, has_usage=False, cap_cpu=4000, cap_mem=8 * 1024**3,
                   sort_key="cpu", pal=cli.Palette(False), width=8)
    out = capsys.readouterr().out
    assert "live usage unavailable" in out


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
    assert "storage_used_bytes" not in data["app"]


def test_to_json_storage_usage():
    stats = {"app": make_stat(pods=1, pvc_count=1, storage=10 * 1024**3,
                              stor_used=5 * 1024**3, stor_cap=10 * 1024**3)}
    data = json.loads(cli.to_json(stats, has_usage=False))["app"]
    assert data["storage_used_bytes"] == 5 * 1024**3
    assert data["storage_capacity_bytes"] == 10 * 1024**3
    assert data["storage_usage_pct"] == 50.0


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
    monkeypatch.setattr(cli, "node_capacities", lambda: {"node-a": (4000, 8 * 1024**3)})
    monkeypatch.setattr(cli, "collect_nodes", lambda ns: {"node-a": stats["app"]})
    monkeypatch.setattr(cli, "node_filesystems", lambda names: {})
    monkeypatch.setattr(cli, "collect_namespace_storage_fs", lambda ns, fs: {})
    monkeypatch.setattr(cli, "get_version", lambda: "0.0.0")
    monkeypatch.setattr(cli.sys, "argv", ["k8sage", "--color", "never"])
    cli.main()
    out = capsys.readouterr().out
    assert out.startswith("k8sage 0.0.0")
    assert "Cluster allocatable" in out
    assert "By node" in out


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
