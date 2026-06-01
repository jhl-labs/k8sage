<!-- markdownlint-disable MD033 MD041 -->
<div align="center">

# k8sage

**Per-namespace CPU / memory / storage usage for a Kubernetes cluster — straight from `kubectl`.**

Namespace 단위 CPU / 메모리 / 스토리지 사용 현황을 `kubectl` 만으로 한눈에.

[![CI](https://github.com/jhl-labs/k8sage/actions/workflows/ci.yml/badge.svg)](https://github.com/jhl-labs/k8sage/actions/workflows/ci.yml)
[![Release](https://github.com/jhl-labs/k8sage/actions/workflows/release.yml/badge.svg)](https://github.com/jhl-labs/k8sage/actions/workflows/release.yml)
[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm--Noncommercial--1.0.0-blue.svg)](LICENSE)

[English](#english) · [한국어](#한국어)

</div>

---

<a name="english"></a>

## English

`k8sage` reads your cluster through `kubectl` and aggregates, **per namespace**:

- **CPU / Memory** — the sum of every Pod container's `requests` and `limits`.
  If `metrics-server` is installed, **live usage** (`kubectl top`) is shown too.
- **Storage** — the sum of PVC requested capacity in the namespace.

It renders this as colored ASCII bars (`use ▏ req ▏ lim` overlaid on cluster
allocatable), a plain table, or JSON. Every run prints `k8sage <version>` at the
top (a 6-char git commit hash for dev builds).

### Requirements

- [`kubectl`](https://kubernetes.io/docs/tasks/tools/) on your `PATH`, configured
  for the target cluster (`kubectl get nodes` should work).
- For live usage columns: [`metrics-server`](https://github.com/kubernetes-sigs/metrics-server)
  installed in the cluster (optional — the tool still works without it).
- For the `uv` / `pip` install: Python **3.9+**. The standalone binaries need
  nothing — Python is bundled.

### Install

#### Option A — `uv` (recommended)

```bash
# Install the latest release as a global tool
uv tool install git+https://github.com/jhl-labs/k8sage

# …or run it once without installing
uvx --from git+https://github.com/jhl-labs/k8sage k8sage

# Pin a specific version
uv tool install git+https://github.com/jhl-labs/k8sage@v0.1.0
```

#### Option B — standalone binary (no Python needed)

Download the file for your platform from the
[**Releases**](https://github.com/jhl-labs/k8sage/releases/latest) page:

| Platform | Asset |
|----------|-------|
| Linux x86_64 | `k8sage-linux-x86_64` |
| Linux aarch64 | `k8sage-linux-aarch64` |
| macOS (Intel) | `k8sage-macos-x86_64` |
| macOS (Apple Silicon) | `k8sage-macos-aarch64` |
| Windows x86_64 | `k8sage-windows-x86_64.exe` |

```bash
# Linux / macOS example
curl -L -o k8sage https://github.com/jhl-labs/k8sage/releases/latest/download/k8sage-linux-x86_64
chmod +x k8sage
sudo mv k8sage /usr/local/bin/
k8sage --version
```

Each binary ships with a `.sha256` file — verify with `sha256sum -c <asset>.sha256`.

#### Option C — `pip` / `pipx`

```bash
pipx install git+https://github.com/jhl-labs/k8sage
# or
pip install git+https://github.com/jhl-labs/k8sage
```

#### Option D — from source (development / dev mode)

No `uv` required — plain `python3` works. Because the package uses a `src/`
layout, you need to point Python at `src/`:

```bash
git clone https://github.com/jhl-labs/k8sage
cd k8sage

# Run straight from source (dev mode) — no install needed
PYTHONPATH=src python3 -m k8sage --version   # -> shows the 6-char git commit hash
PYTHONPATH=src python3 -m k8sage             # full run

# …or do an editable install, then run `k8sage` from anywhere
pip install -e .            # add --break-system-packages on PEP-668 systems
k8sage --version            # -> shows the release version, e.g. 0.1.0

# …or with uv, if you have it
uv run k8sage
```

> **Version display:** running uninstalled from source is treated as a *dev*
> build and shows the **6-char git commit hash**; an installed copy
> (editable / pip / uv / binary) shows the package version (e.g. `0.1.0`).
> Note: `python3 -m k8sage` **without** `PYTHONPATH=src` fails with
> `No module named k8sage`, and running the file directly
> (`python3 src/k8sage/cli.py`) fails on the absolute import — use the `-m`
> form above.

### Usage

```bash
k8sage                 # colored ASCII bars (default): use/req/lim vs allocatable
k8sage --table         # same data as a plain table
k8sage --json          # machine-readable JSON (no banner)
k8sage --color never   # disable color (auto|always|never)
k8sage --sort mem      # sort by: ns | cpu | mem | cpu_use | mem_use | storage
k8sage -n my-ns        # a single namespace only
k8sage --version       # print version and exit
```

#### Reading the bars

```
CPU [████▓▓▓░░········]!  1.2 cores  38%  (   2 cores /        4 cores)
     └ use └ req └ lim                      └ request    └ limit
```

- **█ use** — live usage (needs `metrics-server`)
- **▓ req** — requested (reserved) capacity
- **░ lim** — limit ceiling
- **·** — unused headroom of cluster allocatable
- **!** — the limit exceeds cluster allocatable (overcommit)
- The right-hand value is `usage` and its `% of allocatable`; the parentheses
  show exact `(request / limit)`.

A **low usage/request ratio** means requests are over-provisioned — you're
reserving scheduling capacity you don't actually use.

#### No `metrics-server`?

The tool still works; the `use` columns are hidden and it prints instructions to
install `metrics-server`. To enable live usage:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### License

`k8sage` is released under the **PolyForm Noncommercial License 1.0.0**.

- ✅ **Free** for personal, hobby, study, research, academic, nonprofit, and
  government use.
- 💼 **Commercial use requires a separate license.** Contact the author at
  **<bkperio@gmail.com>**.

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.

### Contributing

Issues and PRs are welcome. Before committing, run:

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest      # enforces ≥99% coverage
```

By contributing you agree your contributions are licensed under the project
license.

---

<a name="한국어"></a>

## 한국어

`k8sage` 는 `kubectl` 로 클러스터를 읽어 **namespace 단위**로 다음을 집계합니다.

- **CPU / 메모리** — 각 Pod 컨테이너의 `requests` / `limits` 합계.
  `metrics-server` 가 설치돼 있으면 **실사용량**(`kubectl top`)도 함께 표시합니다.
- **스토리지** — 해당 namespace 의 PVC 요청 용량 합계.

이 정보를 컬러 ASCII 막대(클러스터 가용량 위에 `use ▏ req ▏ lim` 을 겹쳐 표현),
표, 또는 JSON 으로 출력합니다. 실행할 때마다 최상단에 `k8sage <버전>` 이
표시됩니다(개발 빌드는 6자리 git 커밋 해시).

### 요구 사항

- `PATH` 에 [`kubectl`](https://kubernetes.io/docs/tasks/tools/) 이 있고 대상
  클러스터로 설정되어 있어야 합니다 (`kubectl get nodes` 가 동작해야 함).
- 실사용량 열을 보려면 클러스터에
  [`metrics-server`](https://github.com/kubernetes-sigs/metrics-server) 설치 필요
  (선택 — 없어도 동작합니다).
- `uv` / `pip` 설치 시 Python **3.9 이상**. 단일 실행파일은 Python 이 포함되어
  있어 별도 설치가 필요 없습니다.

### 설치

#### 방법 A — `uv` (권장)

```bash
# 최신 릴리스를 전역 도구로 설치
uv tool install git+https://github.com/jhl-labs/k8sage

# …설치 없이 한 번만 실행
uvx --from git+https://github.com/jhl-labs/k8sage k8sage

# 특정 버전 고정
uv tool install git+https://github.com/jhl-labs/k8sage@v0.1.0
```

#### 방법 B — 단일 실행파일 (Python 불필요)

[**Releases**](https://github.com/jhl-labs/k8sage/releases/latest) 페이지에서 사용
중인 플랫폼용 파일을 내려받으세요.

| 플랫폼 | 파일 |
|--------|------|
| Linux x86_64 | `k8sage-linux-x86_64` |
| Linux aarch64 | `k8sage-linux-aarch64` |
| macOS (Intel) | `k8sage-macos-x86_64` |
| macOS (애플 실리콘) | `k8sage-macos-aarch64` |
| Windows x86_64 | `k8sage-windows-x86_64.exe` |

```bash
# Linux / macOS 예시
curl -L -o k8sage https://github.com/jhl-labs/k8sage/releases/latest/download/k8sage-linux-x86_64
chmod +x k8sage
sudo mv k8sage /usr/local/bin/
k8sage --version
```

각 바이너리에는 `.sha256` 파일이 동봉됩니다 —
`sha256sum -c <파일>.sha256` 으로 검증하세요.

#### 방법 C — `pip` / `pipx`

```bash
pipx install git+https://github.com/jhl-labs/k8sage
# 또는
pip install git+https://github.com/jhl-labs/k8sage
```

#### 방법 D — 소스에서 실행 (개발 / dev 모드)

`uv` 불필요 — 표준 `python3` 로 됩니다. 패키지가 `src/` 레이아웃이라 Python 에
`src/` 를 알려줘야 합니다.

```bash
git clone https://github.com/jhl-labs/k8sage
cd k8sage

# 소스에서 바로 실행 (dev 모드) — 설치 불필요
PYTHONPATH=src python3 -m k8sage --version   # -> git 커밋 해시 6자리 표시
PYTHONPATH=src python3 -m k8sage             # 전체 실행

# …또는 editable 설치 후 어디서나 k8sage 실행
pip install -e .            # PEP-668 환경은 --break-system-packages 추가
k8sage --version            # -> 릴리스 버전 표시 (예: 0.1.0)

# …uv 가 있다면
uv run k8sage
```

> **버전 표기:** 미설치 상태로 소스에서 실행하면 *dev* 빌드로 간주되어
> **git 커밋 해시 6자리**가, 설치본(editable·pip·uv·바이너리)은 패키지 버전
> (예: `0.1.0`)이 표시됩니다. 참고로 `PYTHONPATH=src` **없이**
> `python3 -m k8sage` 는 `No module named k8sage` 로 실패하고, 파일 직접 실행
> (`python3 src/k8sage/cli.py`)은 절대 import 때문에 실패하니 위의 `-m` 형식을
> 쓰세요.

### 사용법

```bash
k8sage                 # 컬러 ASCII 막대 (기본): 가용량 대비 use/req/lim
k8sage --table         # 동일 내용을 표로
k8sage --json          # 기계가 읽기 좋은 JSON (배너 없음)
k8sage --color never   # 컬러 끄기 (auto|always|never)
k8sage --sort mem      # 정렬 기준: ns | cpu | mem | cpu_use | mem_use | storage
k8sage -n my-ns        # 특정 namespace 만
k8sage --version       # 버전 출력 후 종료
```

#### 막대 읽는 법

```
CPU [████▓▓▓░░········]!  1.2 cores  38%  (   2 cores /        4 cores)
     └ use └ req └ lim                      └ request    └ limit
```

- **█ use** — 실사용량 (`metrics-server` 필요)
- **▓ req** — 예약(request)된 용량
- **░ lim** — 상한(limit)
- **·** — 클러스터 가용량 중 미사용 여유
- **!** — limit 이 클러스터 가용량을 초과(overcommit)
- 오른쪽 값은 `실사용량` 과 `가용량 대비 %`, 괄호는 정확한 `(request / limit)`.

**usage/request 비율이 낮다**는 것은 request 가 과다 예약됐다는 뜻입니다 —
실제로 쓰지 않는 스케줄링 용량을 잡아두고 있는 상태입니다.

#### `metrics-server` 가 없다면?

없어도 동작하며, `use` 열만 숨기고 설치 방법을 안내합니다. 실사용량을 켜려면:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### 라이선스

`k8sage` 는 **PolyForm Noncommercial License 1.0.0** 으로 배포됩니다.

- ✅ 개인 · 취미 · 학습 · 연구 · 학교 · 비영리 · 정부 용도는 **무료**.
- 💼 **상업적 이용은 별도 라이선스가 필요**합니다. 저작자에게 문의:
  **<bkperio@gmail.com>**.

자세한 내용은 [LICENSE](LICENSE), [NOTICE](NOTICE) 참고.

### 기여

이슈와 PR 환영합니다. 커밋 전에 실행하세요:

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest      # 커버리지 99% 이상 강제
```

기여 시, 기여물이 프로젝트 라이선스를 따른다는 데 동의하는 것으로 간주합니다.
