#!/usr/bin/env python3
"""
k8sage - 클러스터의 namespace별 CPU/메모리/스토리지 사용 현황 조회

kubectl 을 호출해 다음을 namespace 단위로 집계한다.
  - CPU / 메모리: Pod 컨테이너의 requests / limits 합계
                  (metrics-server 가 있으면 실사용량도 함께 표시)
  - 스토리지: 해당 namespace 의 PVC 요청 용량 합계

사용법:
    k8sage                # ASCII 막대 그래프 (기본, 컬러). 총 가용량 대비 use/req/lim
    k8sage --table        # 같은 내용을 표 형태로
    k8sage --json         # JSON 출력
    k8sage --color never  # 컬러 끄기 (auto|always|never)
    k8sage --sort mem     # 정렬 기준: ns|cpu|mem|cpu_use|mem_use|storage
    k8sage -n my-ns       # 특정 namespace 만
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict

from k8sage import __version__


# ----------------------------------------------------------------------------
# 버전 해석
# ----------------------------------------------------------------------------
def _git_short_hash() -> str | None:
    """소스 체크아웃에서 실행될 때 k8sage 저장소의 짧은 커밋 해시(6글자).

    git 이 없거나 .git 저장소 밖(설치본·단일 실행파일)에서는 None.
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        proc = subprocess.run(
            ["git", "-C", pkg_dir, "rev-parse", "--short=6", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def get_version() -> str:
    """표시용 버전 문자열을 반환한다.

    1) 정식 설치본: 패키지 메타데이터 버전 (예: '0.1.0').
    2) dev(소스 실행): git 커밋 해시 6글자.
    3) 둘 다 불가: 정적 __version__.
    """
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("k8sage")
    except PackageNotFoundError:
        pass
    h = _git_short_hash()
    if h:
        return h
    return __version__


# ----------------------------------------------------------------------------
# ANSI 컬러
# ----------------------------------------------------------------------------
class Palette:
    """ANSI 색상 래퍼. enabled 가 False 면 원문을 그대로 돌려준다."""

    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def _w(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def use(self, s: str) -> str:   return self._w("92", s)    # 실사용: 밝은 초록
    def req(self, s: str) -> str:   return self._w("33", s)    # 예약: 노랑
    def lim(self, s: str) -> str:   return self._w("90", s)    # 상한: 어두운 회색
    def head(self, s: str) -> str:  return self._w("1;36", s)  # 섹션 제목: 굵은 청록
    def ns(self, s: str) -> str:    return self._w("1;37", s)  # namespace 이름: 굵은 흰색
    def dim(self, s: str) -> str:   return self._w("2", s)     # 부가 설명
    def warn(self, s: str) -> str:  return self._w("1;31", s)  # 초과(!): 굵은 빨강
    def rule(self, s: str) -> str:  return self._w("90", s)    # 구분선


def want_color(mode: str) -> bool:
    """--color 옵션과 환경(NO_COLOR, tty 여부)으로 컬러 사용 여부 결정."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


# ----------------------------------------------------------------------------
# kubectl 호출
# ----------------------------------------------------------------------------
def kubectl(args: list[str]) -> dict:
    """kubectl 을 -o json 으로 실행하고 파싱한 dict 를 반환한다."""
    cmd = ["kubectl", *args, "-o", "json"]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=60
        ).stdout
    except FileNotFoundError:
        sys.exit("오류: kubectl 을 찾을 수 없습니다. PATH 를 확인하세요.")
    except subprocess.CalledProcessError as e:
        sys.exit(f"오류: kubectl 실행 실패\n{e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        sys.exit("오류: kubectl 응답 시간 초과")
    return json.loads(out)


def kubectl_top() -> dict[tuple[str, str], tuple[int, int]] | None:
    """`kubectl top pods -A` 실사용량을 (cpu_m, mem_bytes) 로 반환.

    metrics-server 가 없으면 None.
    """
    try:
        proc = subprocess.run(
            ["kubectl", "top", "pods", "-A", "--no-headers"],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None  # Metrics API not available 등

    usage: dict[tuple[str, str], tuple[int, int]] = {}
    for line in proc.stdout.splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        ns, pod, cpu, mem = cols[0], cols[1], cols[2], cols[3]
        usage[(ns, pod)] = (parse_cpu(cpu), parse_mem(mem))
    return usage


# ----------------------------------------------------------------------------
# 단위 파서: CPU(millicores), 메모리/스토리지(bytes)
# ----------------------------------------------------------------------------
def parse_cpu(val: str | None) -> int:
    """CPU 수량을 millicores(정수)로 변환. '500m' -> 500, '2' -> 2000."""
    if not val:
        return 0
    val = val.strip()
    if val.endswith("m"):
        return int(float(val[:-1]))
    if val.endswith("n"):  # nanocores (top 출력에서 드물게)
        return int(float(val[:-1]) / 1_000_000)
    return int(float(val) * 1000)


_MEM_FACTORS = {
    "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4, "Pi": 1024**5,
    "K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4, "P": 1000**5,
    "k": 1000,
}


def parse_mem(val: str | None) -> int:
    """메모리/스토리지 수량을 bytes(정수)로 변환. '128Mi', '1Gi', '512' 지원."""
    if not val:
        return 0
    val = val.strip()
    m = re.fullmatch(r"([0-9.]+)\s*([A-Za-z]+)?", val)
    if not m:
        return 0
    num = float(m.group(1))
    suffix = m.group(2) or ""
    return int(num * _MEM_FACTORS.get(suffix, 1))


# ----------------------------------------------------------------------------
# 포매터
# ----------------------------------------------------------------------------
def fmt_cpu(millicores: int) -> str:
    if millicores == 0:
        return "-"
    if millicores < 1000:
        return f"{millicores}m"
    return f"{millicores / 1000:.2f}".rstrip("0").rstrip(".") + " cores"


def fmt_bytes(b: int) -> str:
    if b == 0:
        return "-"
    for unit in ("B", "Ki", "Mi", "Gi", "Ti", "Pi"):
        if abs(b) < 1024:
            return f"{b:.1f}{unit}".replace(".0", "")
        b /= 1024
    return f"{b:.1f}Ei"


# ----------------------------------------------------------------------------
# ASCII 막대 (usage / request / limit 을 총 가용량 위에 겹쳐 표현)
# ----------------------------------------------------------------------------
BAR_USE = "█"   # 실사용 (usage) / storage 채움
BAR_REQ = "▓"   # 예약 (request, 실사용 초과분)
BAR_LIM = "░"   # 상한 (limit, 예약 초과분)
BAR_GAP = "·"   # 미사용 여유 (옅은 점선 트랙)

STO_CODE = "94"  # storage: 밝은 파랑

_BAR_COLOR = {BAR_USE: "92", BAR_REQ: "33", BAR_LIM: "90", BAR_GAP: "90"}
_STO_COLOR = {BAR_USE: STO_CODE, BAR_GAP: "90"}


def colorize_bar(bar: str, pal: Palette, color_map: dict | None = None) -> str:
    """막대 문자열을 같은 문자 구간끼리 묶어 색을 입힌다(이스케이프 최소화)."""
    if not pal.on:
        return bar
    cmap = color_map if color_map is not None else _BAR_COLOR
    out, i, n = [], 0, len(bar)
    while i < n:
        j = i
        while j < n and bar[j] == bar[i]:
            j += 1
        code = cmap.get(bar[i])
        run = bar[i:j]
        out.append(f"\033[{code}m{run}\033[0m" if code else run)
        i = j
    return "".join(out)


def render_storage_bar(value: int, total: int, width: int = 32) -> str:
    """value 를 total(=최대 namespace storage) 대비 채운 단색 막대.

    storage 는 use/req/lim 구분이 없어 채움(█)/여백(·) 단색으로만 표현한다.
    """
    if total <= 0 or value <= 0:
        return BAR_GAP * width
    fill = min(width, round(value / total * width))
    return BAR_USE * fill + BAR_GAP * (width - fill)


def render_bar(usage: int, request: int, limit: int, total: int, width: int = 32) -> str:
    """total(가용량)을 width 칸으로 보고 usage<=request<=limit 순으로 겹쳐 채운다.

    각 칸의 중심 위치가 어느 임계값 이하인지에 따라 문자를 고른다.
    limit 이 total 을 넘으면(overcommit) 막대는 끝까지 ░ 로 채워진다.
    """
    if total <= 0:
        return BAR_GAP * width
    u = usage / total * width
    r = request / total * width
    lim_w = limit / total * width
    cells = []
    for i in range(width):
        c = i + 0.5
        if c <= u:
            cells.append(BAR_USE)
        elif c <= r:
            cells.append(BAR_REQ)
        elif c <= lim_w:
            cells.append(BAR_LIM)
        else:
            cells.append(BAR_GAP)
    return "".join(cells)


def _pct(v: int, total: int) -> str:
    if not total or v == 0:
        return "-"
    p = v / total * 100
    return f"{p:.0f}%{'!' if p > 100 else ''}"


def cluster_capacity() -> tuple[int, int]:
    """노드 allocatable 합계 (cpu_millicores, mem_bytes)."""
    nodes = kubectl(["get", "nodes"])
    cpu = mem = 0
    for n in nodes.get("items", []):
        alloc = n.get("status", {}).get("allocatable", {})
        cpu += parse_cpu(alloc.get("cpu"))
        mem += parse_mem(alloc.get("memory"))
    return cpu, mem


# ----------------------------------------------------------------------------
# 집계
# ----------------------------------------------------------------------------
class NsStat:
    __slots__ = (
        "pods", "cpu_req", "cpu_lim", "mem_req", "mem_lim",
        "cpu_use", "mem_use", "pvc_count", "storage",
    )

    def __init__(self) -> None:
        self.pods = 0
        self.cpu_req = self.cpu_lim = 0
        self.mem_req = self.mem_lim = 0
        self.cpu_use = self.mem_use = 0
        self.pvc_count = 0
        self.storage = 0


def collect(namespace: str | None) -> dict[str, NsStat]:
    scope = ["-n", namespace] if namespace else ["-A"]
    stats: dict[str, NsStat] = defaultdict(NsStat)

    # --- Pods: requests / limits ---
    pods = kubectl(["get", "pods", *scope])
    top = kubectl_top()  # None 이면 실사용량 미표시

    for pod in pods.get("items", []):
        ns = pod["metadata"]["namespace"]
        name = pod["metadata"]["name"]
        phase = pod.get("status", {}).get("phase")
        if phase in ("Succeeded", "Failed"):
            continue  # 종료된 Pod 는 자원 점유 안 함
        st = stats[ns]
        st.pods += 1
        spec = pod.get("spec", {})
        containers = spec.get("containers", []) + spec.get("initContainers", [])
        for c in containers:
            res = c.get("resources", {})
            req, lim = res.get("requests", {}), res.get("limits", {})
            st.cpu_req += parse_cpu(req.get("cpu"))
            st.cpu_lim += parse_cpu(lim.get("cpu"))
            st.mem_req += parse_mem(req.get("memory"))
            st.mem_lim += parse_mem(lim.get("memory"))
        if top is not None and (ns, name) in top:
            cu, mu = top[(ns, name)]
            st.cpu_use += cu
            st.mem_use += mu

    # --- PVC: 스토리지 ---
    pvcs = kubectl(["get", "pvc", *scope])
    for pvc in pvcs.get("items", []):
        ns = pvc["metadata"]["namespace"]
        cap = (
            pvc.get("status", {}).get("capacity", {}).get("storage")
            or pvc.get("spec", {}).get("resources", {}).get("requests", {}).get("storage")
        )
        st = stats[ns]
        st.pvc_count += 1
        st.storage += parse_mem(cap)

    return stats


# ----------------------------------------------------------------------------
# 출력
# ----------------------------------------------------------------------------
def sort_rows(stats: dict[str, NsStat], sort_key: str) -> list[tuple[str, NsStat]]:
    sorters = {
        "ns": lambda kv: kv[0],
        "cpu": lambda kv: -kv[1].cpu_req,
        "mem": lambda kv: -kv[1].mem_req,
        "cpu_use": lambda kv: -kv[1].cpu_use,
        "mem_use": lambda kv: -kv[1].mem_use,
        "storage": lambda kv: -kv[1].storage,
    }
    return sorted(stats.items(), key=sorters.get(sort_key, sorters["ns"]))


def aggregate(stats: dict[str, NsStat]) -> NsStat:
    tot = NsStat()
    for s in stats.values():
        tot.pods += s.pods
        tot.cpu_req += s.cpu_req; tot.cpu_lim += s.cpu_lim; tot.cpu_use += s.cpu_use
        tot.mem_req += s.mem_req; tot.mem_lim += s.mem_lim; tot.mem_use += s.mem_use
        tot.pvc_count += s.pvc_count; tot.storage += s.storage
    return tot


def print_table(stats: dict[str, NsStat], has_usage: bool, sort_key: str) -> None:
    rows = sort_rows(stats, sort_key)

    headers = ["NAMESPACE", "PODS", "CPU(req)", "CPU(lim)"]
    if has_usage:
        headers.append("CPU(use)")
    headers += ["MEM(req)", "MEM(lim)"]
    if has_usage:
        headers.append("MEM(use)")
    headers += ["PVC", "STORAGE"]

    def make_row(ns: str, s: NsStat) -> list[str]:
        r = [ns, str(s.pods), fmt_cpu(s.cpu_req), fmt_cpu(s.cpu_lim)]
        if has_usage:
            r.append(fmt_cpu(s.cpu_use))
        r += [fmt_bytes(s.mem_req), fmt_bytes(s.mem_lim)]
        if has_usage:
            r.append(fmt_bytes(s.mem_use))
        r += [str(s.pvc_count), fmt_bytes(s.storage)]
        return r

    table = [make_row(ns, s) for ns, s in rows]

    # 합계
    tot = aggregate(stats)
    table.append(make_row("TOTAL", tot))

    widths = [len(h) for h in headers]
    for row in table:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def line(cells: list[str], pad: str = " ") -> str:
        return pad + (pad * 2).join(c.ljust(w) for c, w in zip(cells, widths)) + pad

    sep = "-" * (sum(widths) + 2 * len(widths) + (len(widths) - 1) * 1)
    print(line(headers))
    print(sep)
    for row in table[:-1]:
        print(line(row))
    print(sep)
    print(line(table[-1]))

    if has_usage:
        # requests 대비 실사용 비율(효율) — 과다 예약 여부를 한눈에
        cpu_pct = f"{tot.cpu_use / tot.cpu_req * 100:.0f}%" if tot.cpu_req else "-"
        mem_pct = f"{tot.mem_use / tot.mem_req * 100:.0f}%" if tot.mem_req else "-"
        print(
            f"\n* usage/request ratio (total): CPU {tot.cpu_use}m / {tot.cpu_req}m = {cpu_pct}, "
            f"MEM {fmt_bytes(tot.mem_use)} / {fmt_bytes(tot.mem_req)} = {mem_pct}"
        )
        print(
            "  A low ratio means requests are over-provisioned "
            "(reserves scheduling capacity without actually using it)."
        )
        print(
            "* '-' in CPU(use)/MEM(use) means the pod is not running "
            "(Pending/ImagePullBackOff/Completed, etc.)."
        )
    else:
        print(no_metrics_hint())


def no_metrics_hint() -> str:
    return (
        "\n* usage (use) hidden: metrics-server (Metrics API) is not available, "
        "so live usage cannot be fetched.\n"
        "  Showing requests/limits instead.\n"
        "\n  [To see live usage, install metrics-server]\n"
        "    kubectl apply -f https://github.com/kubernetes-sigs/"
        "metrics-server/releases/latest/download/components.yaml\n"
        "\n  On self-managed clusters (on-prem/Rancher), if pods don't show up, "
        "add the kubelet TLS option:\n"
        "    kubectl patch deployment metrics-server -n kube-system --type=json \\\n"
        "      -p='[{\"op\":\"add\",\"path\":"
        "\"/spec/template/spec/containers/0/args/-\","
        "\"value\":\"--kubelet-insecure-tls\"}]'\n"
        "  Re-run after 1-2 minutes and the usage columns will appear."
    )


def _color_pct(padded: str, pal: Palette, base) -> str:
    """퍼센트 문자열을 색칠. 100% 초과(!) 는 빨강, 그 외엔 base 색."""
    return pal.warn(padded) if "!" in padded else base(padded)


def _bar_lines(cpu: tuple[int, int, int], mem: tuple[int, int, int],
               cap_cpu: int, cap_mem: int, width: int, indent: str,
               pal: Palette) -> list[str]:
    """(use, req, lim) 튜플로 CPU/MEM 막대 2줄을 만든다 (컬러 적용).

    막대(▓/░)는 req/lim 의 '분포'를, 우측 값은 실사용량과 가용 대비 % 를,
    맨 오른쪽 괄호는 정확한 (req / lim) 수치를 보여준다.
    lim 이 총 가용을 넘으면(overcommit) 막대 옆에 ! 표시.
    """
    out = []
    for res, (u, rq, lm), total, fmt in (
        ("CPU", cpu, cap_cpu, fmt_cpu),
        ("MEM", mem, cap_mem, fmt_bytes),
    ):
        bar = colorize_bar(render_bar(u, rq, lm, total, width), pal)
        over = pal.warn("!") if total and lm > total else " "
        rq_s = f"{fmt(rq):>6}"
        lm_s = f"{(fmt(lm) if lm else '-'):>10}"
        paren = (pal.dim("(") + pal.req(rq_s) + pal.dim(" / ")
                 + pal.lim(lm_s) + pal.dim(")"))
        out.append(
            f"{indent}{pal.dim(res)} [{bar}]{over} "
            f"{pal.use(f'{fmt(u):>7}')} {_color_pct(f'{_pct(u, total):>4}', pal, pal.use)}  "
            f"{paren}"
        )
    return out


def _storage_line(storage: int, pvc_count: int, max_storage: int,
                  width: int, indent: str, pal: Palette) -> str:
    """namespace PVC storage 막대 1줄. 가장 큰 namespace 를 가득으로 한 상대 비교.

    클러스터 전체 storage 총량은 기준이 없으므로 namespace 간 상대 크기로 표현하고,
    오른쪽에 절대 용량과 PVC 개수를 보여준다.
    """
    bar = colorize_bar(render_storage_bar(storage, max_storage, width),
                       pal, _STO_COLOR)
    share = _pct(storage, max_storage)
    val = pal._w(STO_CODE, f"{fmt_bytes(storage):>7}")
    pvc = pal.dim(f"pvc {pvc_count}")
    return (f"{indent}{pal.dim('STO')} [{bar}]  "
            f"{val} {pal.dim(f'{share:>4}')}  {pvc}")


def print_bars(stats: dict[str, NsStat], has_usage: bool,
               cap_cpu: int, cap_mem: int, sort_key: str, pal: Palette,
               width: int = 32) -> None:
    tot = aggregate(stats)
    rows = sort_rows(stats, sort_key)

    print(pal.head("Cluster allocatable")
          + f"  CPU {pal.use(fmt_cpu(cap_cpu))}  │  MEM {pal.use(fmt_bytes(cap_mem))}")
    # 레전드 기호는 막대와 같은 색으로 칠해 한눈에 매칭되게 한다.
    print(pal.dim("Legend  bar  ") + pal.use(BAR_USE) + pal.dim(" use  ")
          + pal.req(BAR_REQ) + pal.dim(" req  ") + pal.lim(BAR_LIM)
          + pal.dim(" lim   (filled = share of allocatable)"))
    print(pal.dim("        value = usage / alloc%,   (req / lim) shown on the right"))
    print(pal.dim("        ") + pal._w(STO_CODE, BAR_USE)
          + pal.dim(" STO = PVC storage per namespace, relative to the largest ns"))
    print(pal.dim("        ! = limit exceeds allocatable"))
    if not has_usage:
        print(pal.warn("Note: metrics-server not found → 'use' shown as '-'/0."))

    print("\n" + pal.head("■ Whole cluster"))
    for ln in _bar_lines(
        (tot.cpu_use, tot.cpu_req, tot.cpu_lim),
        (tot.mem_use, tot.mem_req, tot.mem_lim),
        cap_cpu, cap_mem, width, indent="  ", pal=pal,
    ):
        print(ln)

    print("\n" + pal.head("■ By namespace"))
    name_w = max((len(ns) for ns, _ in rows), default=0)
    max_storage = max((s.storage for _, s in rows), default=0)
    for ns, s in rows:
        print(f"  {pal.ns(ns.ljust(name_w))}   {pal.dim(f'pods {s.pods}')}")
        for ln in _bar_lines(
            (s.cpu_use, s.cpu_req, s.cpu_lim),
            (s.mem_use, s.mem_req, s.mem_lim),
            cap_cpu, cap_mem, width, indent="    ", pal=pal,
        ):
            print(ln)
        if s.storage:
            print(_storage_line(s.storage, s.pvc_count, max_storage,
                                width, indent="    ", pal=pal))

    if not has_usage:
        print(no_metrics_hint())


def to_json(stats: dict[str, NsStat], has_usage: bool) -> str:
    out = {}
    for ns, s in stats.items():
        d = {
            "pods": s.pods,
            "cpu_requests_millicores": s.cpu_req,
            "cpu_limits_millicores": s.cpu_lim,
            "mem_requests_bytes": s.mem_req,
            "mem_limits_bytes": s.mem_lim,
            "pvc_count": s.pvc_count,
            "storage_bytes": s.storage,
        }
        if has_usage:
            d["cpu_usage_millicores"] = s.cpu_use
            d["mem_usage_bytes"] = s.mem_use
            d["cpu_usage_pct_of_req"] = (
                round(s.cpu_use / s.cpu_req * 100, 1) if s.cpu_req else None
            )
            d["mem_usage_pct_of_req"] = (
                round(s.mem_use / s.mem_req * 100, 1) if s.mem_req else None
            )
        out[ns] = d
    return json.dumps(out, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------------
def banner(pal: Palette) -> str:
    """출력 최상단에 보일 'k8sage <version>' 배너."""
    return pal.head("k8sage") + pal.dim(f" {get_version()}")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="k8sage",
        description="namespace별 CPU/메모리/스토리지 사용 현황 조회 (kubectl 기반)",
    )
    ap.add_argument(
        "--version", action="version", version=f"%(prog)s {get_version()}",
    )
    ap.add_argument("-n", "--namespace", help="특정 namespace 만 조회")
    ap.add_argument("--json", action="store_true", help="JSON 으로 출력")
    ap.add_argument(
        "--table", action="store_true",
        help="ASCII 막대 대신 표로 출력 (막대 그래프와 내용은 동일)",
    )
    # 하위 호환: 예전 기본은 표였고 --bar 로 막대를 봤다. 이제 막대가 기본이라
    # --bar 는 아무 동작도 바꾸지 않는다(무시).
    ap.add_argument("--bar", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument(
        "--color", choices=["auto", "always", "never"], default="auto",
        help="컬러 출력 (기본: auto = 터미널이면 켜고 파이프/리다이렉트면 끔)",
    )
    ap.add_argument(
        "--sort", default="cpu",
        choices=["ns", "cpu", "mem", "cpu_use", "mem_use", "storage"],
        help="정렬 기준 (기본: cpu). cpu_use/mem_use 는 실사용량 기준",
    )
    args = ap.parse_args()

    if not shutil.which("kubectl"):
        sys.exit("오류: kubectl 이 설치되어 있지 않습니다.")

    stats = collect(args.namespace)
    if not stats:
        print("조회된 namespace 가 없습니다.")
        return
    has_usage = any(s.cpu_use or s.mem_use for s in stats.values())

    if args.json:
        # JSON 은 기계가 파싱하므로 배너를 섞지 않는다.
        print(to_json(stats, has_usage))
        return

    pal = Palette(want_color(args.color))
    print(banner(pal))  # 최상단 버전 정보
    if args.table:
        print_table(stats, has_usage, args.sort)
    else:
        cap_cpu, cap_mem = cluster_capacity()
        print_bars(stats, has_usage, cap_cpu, cap_mem, args.sort, pal)


if __name__ == "__main__":
    main()
