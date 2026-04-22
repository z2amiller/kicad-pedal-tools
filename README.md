# kicad-pedal-common

Shared Python library for KiCad pedal build tooling.

Used by:
- `manifest-creator` (KiCad plugin) — vendored at build time via `scripts/vendor.sh`
- `pedal-build-manager` (webapp) — pip installed normally

## Requirements

Python 3.9+ (compatible with KiCad's embedded Python 3.9).

## Installation

```bash
pip install kicad-pedal-common
```

For development:

```bash
pip install -e ".[dev]"
```

## Vendoring for KiCad plugins

```bash
scripts/vendor.sh /path/to/plugin/directory
```

## Modules

- `kicad_pedal_common.bom` — BOM grouping, humanized value sorting
- `kicad_pedal_common.footprint` — footprint iteration helpers
- `kicad_pedal_common.plotting` — layer plotting / kicad-cli helpers
- `kicad_pedal_common.schema` — JSON schema files for manifest and BOM entries

## Development

### Distribution model

KiCad plugins (`kicad-build-doc-plugin`, `manifest-creator`) vendor this library
at build time using `scripts/vendor.sh`, which copies `kicad_pedal_common/` directly
into the plugin directory. This avoids pip install requirements at plugin runtime.
Webapps (e.g. `pedal-build-manager`) install the package normally via pip.

### Consumer test suites

PRs to this repo automatically run the test suites of both consumer plugins after
the library's own tests pass. This catches breaking changes before merge.

To run a consumer's tests locally:

```bash
# From the kicad-pedal-common checkout:
bash scripts/vendor.sh /path/to/kicad-build-doc-plugin
cd /path/to/kicad-build-doc-plugin
pytest tests/ -v
```
