# kicad-pedal-tools

KiCad plugins and tools for guitar pedal PCB design. This monorepo contains:

| Plugin | Description |
|--------|-------------|
| [`build-doc-plugin/`](build-doc-plugin/) | Generates a PDF build document (cover page, BOM, 1:1 enclosure drilling template, schematic) from a KiCad board |
| [`manifest-creator/`](manifest-creator/) | Exports a `.manifest.zip` for the [pedal-build-manager](https://github.com/z2amiller/pedal-build-manager) web app — SVG layers, BOM, footprint art |
| [`kicad_pedal_common/`](kicad_pedal_common/) | Shared library used by both plugins (board adapter, drill extraction, BOM export) |

Both plugins work in two modes:

- **KiCad IPC plugin** — runs inside the KiCad PCB editor via the toolbar button
- **Headless CLI** — runs from the command line without KiCad open, using [kiutils](https://github.com/mvnmgrx/kiutils) to parse `.kicad_pcb` files directly

---

## ⚠️ Important: enable the KiCad IPC API

The toolbar plugins communicate with KiCad via its IPC API, which is **disabled by default**. Without enabling it the plugin button does nothing.

**In the KiCad PCB editor:**

1. Open **Preferences → Preferences**
2. Navigate to **PCB Editor → Scripting** in the left sidebar
3. Enable **"Allow external plugins to connect via IPC"** (or similar — the exact label varies slightly between KiCad 9 and 10)
4. Click **OK** and restart the PCB editor

You only need to do this once per KiCad installation.

---

## Quick start

### Install via KiCad Plugin Manager

1. Open KiCad → **Plugin and Content Manager**
2. Click **Manage** (next to the repository selector) → **Add**
3. Enter the repository URL:
   ```
   https://raw.githubusercontent.com/z2amiller/kicad-pcm/main/repository.json
   ```
4. Install **Build Document Generator** and/or **Manifest Creator**
5. Enable the IPC API (see above)

### Install CLI tools

Both plugins can also be installed as standalone Python CLI tools:

```bash
# Build doc generator
pip install "build-doc @ git+https://github.com/z2amiller/kicad-pedal-tools.git#subdirectory=build-doc-plugin"

# Manifest creator
pip install "manifest-creator @ git+https://github.com/z2amiller/kicad-pedal-tools.git#subdirectory=manifest-creator"
```

See each plugin's README for full CLI usage.

---

## Releases

Tags are prefixed by plugin:

| Tag prefix | Plugin | Example |
|------------|--------|---------|
| `build-doc/vX.Y.Z` | Build Document Generator | `build-doc/v1.2.2` |
| `manifest/vX.Y.Z` | Manifest Creator | `manifest/v0.3.1` |

GitHub Actions builds the PCM `.zip` archive and attaches it to the release automatically on each tag push.

---

## Repository layout

```
kicad-pedal-tools/
├── build-doc-plugin/       # PDF build document generator plugin + CLI
│   ├── PCM/                # KiCad Package and Content Manager packaging
│   └── tests/
├── manifest-creator/       # Board manifest exporter plugin + CLI
│   ├── manifest_creator/   # Python package (importable)
│   └── PCM/
├── kicad_pedal_common/     # Shared library (not released via PCM)
│   └── kicad_pedal_common/
└── .github/workflows/      # CI (per-plugin, path-scoped) + release pipelines
```

## License

MIT — see [LICENSE](build-doc-plugin/LICENSE).
