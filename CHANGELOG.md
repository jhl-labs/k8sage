# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/jhl-labs/k8sage/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jhl-labs/k8sage/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jhl-labs/k8sage/releases/tag/v0.1.0
