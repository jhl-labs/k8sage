# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.2] - 2026-06-01

### Fixed
- Linux standalone binaries now run on older distributions (Ubuntu 20.04+,
  RHEL 8+, Debian 10+, …). They were built on Ubuntu 24.04 (glibc 2.39) and
  failed with `GLIBC_2.38 not found` on older systems. Linux binaries are now
  statically linked with `staticx`, bundling libc so they run regardless of the
  target's glibc version. macOS/Windows builds are unchanged.

## [0.3.1] - 2026-06-01

### Fixed
- Live PVC usage no longer double-counts a shared node filesystem. With
  local-path/hostPath provisioners every PVC reports the whole node root disk,
  so summing them inflated a namespace's storage (e.g. a 70 GiB disk shown as
  ~140 GiB). Volumes whose capacity equals the node root filesystem are now
  counted once per namespace (using the node `fs` usage), matching `df`;
  distinct volumes (CSI, etc.) are still summed.

## [0.3.0] - 2026-06-01

### Added
- **Live PVC storage usage** in the bars view and JSON output. The `STO` bar
  now shows real `used / capacity` from the kubelet stats summary API
  (`/api/v1/nodes/<node>/proxy/stats/summary`), so `100%` means a volume is
  actually full. JSON gains `storage_used_bytes`, `storage_capacity_bytes`, and
  `storage_usage_pct`.

### Notes
- Live usage needs `nodes/proxy` RBAC and only counts PVCs mounted by a running
  pod; otherwise it falls back to the requested-size relative view from 0.2.0.
- Some provisioners (local-path / hostPath) report the backing node filesystem
  rather than the PVC's logical size.

## [0.2.0] - 2026-06-01

### Added
- Per-namespace **PVC storage bar** in the bars view, scaled relative to the
  largest namespace (cluster-wide storage is not aggregated, as there is no
  single storage-capacity reference).

### Changed
- Legend symbols are now colored to match the bars (`█` green / `▓` yellow /
  `░` gray / `█` blue for storage), instead of being uniformly dimmed.
- The per-namespace PVC/storage summary moved from the header line into the
  dedicated `STO` bar line.

## [0.1.0] - 2026-06-01

### Added
- Initial release.
- Per-namespace CPU / memory / storage aggregation from `kubectl`.
- ASCII bar view (default), `--table`, and `--json` output modes.
- Live usage via `metrics-server` (`kubectl top`) when available, with a
  helpful hint when it is not.
- `--sort`, `--namespace`, and `--color` options.
- Packaged for `uv` / `pip` install with a `k8sage` console command.
- Standalone single-file binaries for Linux, macOS (Intel & Apple Silicon),
  and Windows, published via GitHub Releases.

[Unreleased]: https://github.com/jhl-labs/k8sage/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/jhl-labs/k8sage/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/jhl-labs/k8sage/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/jhl-labs/k8sage/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jhl-labs/k8sage/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jhl-labs/k8sage/releases/tag/v0.1.0
