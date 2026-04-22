# Project Instructions for AI Agents

This is the **kicad-pedal-tools** monorepo, containing:

- `kicad_pedal_common/` — shared library (no PCM release, imported directly)
- `manifest-creator/` — PCM plugin + CLI for exporting board manifests
- `build-doc-plugin/` — PCM plugin for generating PDF build documents

The webapp (`pedal-build-manager`) lives in a separate repo at
`/Users/andrewmiller/Claude/pedal-build-manager`.

## Beads Issue Tracker

Beads lives at `.beads/` in this directory. Run `bd prime` for full workflow context.

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

## Python Path

Tests and CLI tools for each plugin need `kicad_pedal_common` on the path.
From a plugin subdirectory, set `PYTHONPATH=..` or run from the repo root.

## Releasing

Tags are prefixed by plugin:
- `manifest/v0.3.0` → triggers `release-manifest-creator.yml`
- `build-doc/v1.2.0` → triggers `release-build-doc.yml`

## PCM Archive Scripts

`PCM/create_pcm_archive.sh` in each plugin copies `kicad_pedal_common` from
`MONOREPO_ROOT` (one level up from the plugin dir). No `vendor.sh` needed.
