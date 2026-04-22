# manifest-creator

KiCad IPC plugin that exports a pedal build manifest (`.zip`) for use with pedal-build-manager.

## Development

Vendor `kicad-pedal-common` and install dev dependencies:

```bash
/Users/andrewmiller/Claude/kicad-pedal-common/scripts/vendor.sh .
pip install -e ".[dev]"
```

Run tests:

```bash
pytest tests/ -v
```
