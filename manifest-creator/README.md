# manifest-creator

Exports a pedal build manifest (`.manifest.zip`) from a KiCad board for use with [pedal-build-manager](https://github.com/z2amiller/pedal-build-manager). Available as a KiCad IPC plugin (GUI) or a standalone CLI tool.

## ⏱ Build time

Generating a manifest takes **30–60 seconds** depending on board complexity. Most of the time is spent in `kicad-cli` exporting SVG layers and footprint art. The plugin shows a live log window with a progress bar; the CLI streams log lines to stderr.

---

## Installation

### Option A — KiCad Plugin (GUI)

Install via KiCad's **Plugin and Content Manager**:

1. Open KiCad → **Plugin and Content Manager**
2. Click **Manage** → add the self-hosted repository URL:
   ```
   https://raw.githubusercontent.com/z2amiller/kicad-pcm/main/repository.json
   ```
3. Find **Manifest Creator** in the list and install it.

Or install directly from a release ZIP:
- Download `manifest-creator-vX.Y.Z.zip` from the [Releases](https://github.com/z2amiller/manifest-creator/releases) page
- KiCad → **Plugin and Content Manager** → **Install from File**

Once installed, the plugin appears as a toolbar button in the PCB editor. Click it, choose a save location, and the export runs with a live progress window.

> **Note:** The PCM plugin runs inside KiCad's Python environment. It does **not** make `python -m manifest_creator` available on the system — see Option B for that.

### Option B — CLI (headless / scripting)

Install into your system or project Python environment:

```bash
pip install git+https://github.com/z2amiller/manifest-creator.git
```

This also installs `kiutils` for full BOM and footprint geometry export without a running KiCad session.

**Basic usage:**

```bash
python -m manifest_creator \
    --board path/to/your-board.kicad_pcb \
    --out your-board-1.0.0.manifest.zip \
    --version 1.0.0
```

**Upload directly to pedal-build-manager:**

```bash
python -m manifest_creator \
    --board your-board.kicad_pcb \
    --out your-board-1.0.0.manifest.zip \
    --version 1.0.0 \
    --upload-to https://your-server.example.com \
    --password <admin-password>
```

Set `MANIFEST_ADMIN_PASSWORD` in your environment to avoid passing `--password` on the command line.

**Upload a PDF build document alongside the manifest:**

```bash
python -m manifest_creator \
    --board your-board.kicad_pcb \
    --out your-board-1.0.0.manifest.zip \
    --version 1.0.0 \
    --upload-to https://your-server.example.com \
    --pdf your-board-build-doc.pdf
```

---

## CLI reference

| Flag | Description |
|------|-------------|
| `--board PATH` | Path to the `.kicad_pcb` file (required) |
| `--out PATH` | Output path for the `.manifest.zip` (required) |
| `--version VERSION` | Version string, e.g. `1.0.0` (required) |
| `--display-name NAME` | Human-readable board name (defaults to file stem) |
| `--kicad-cli PATH` | Explicit path to `kicad-cli` (auto-detected if omitted) |
| `--upload-to URL` | Base URL of a pedal-build-manager instance to upload to |
| `--password PASSWORD` | Admin password for `--upload-to` (or `MANIFEST_ADMIN_PASSWORD` env var) |
| `--pdf PATH` | PDF build document to upload alongside the manifest |

---

## Development

Vendor `kicad-pedal-common` and install dev dependencies:

```bash
/path/to/kicad-pedal-common/scripts/vendor.sh .
pip install -e ".[dev]"
```

Run tests:

```bash
pytest tests/ -v
```
