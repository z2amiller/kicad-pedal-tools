SRC := ../kicad-pedal-common/kicad_pedal_common
DST := kicad_pedal_common

# Files from kicad-pedal-common that manifest-creator uses.
# ipc_watchdog.py is IPC-plugin-only and intentionally excluded.
SYNC_FILES := \
	__init__.py \
	board_adapter.py \
	bom.py \
	drill.py \
	footprint.py \
	kiutils_board_adapter.py \
	plotting.py \
	plugin_utils.py

.PHONY: sync test

sync:
	@echo "Syncing kicad_pedal_common from $(SRC)…"
	@for f in $(SYNC_FILES); do \
		cp -v $(SRC)/$$f $(DST)/$$f; \
	done
	@rsync -av --delete $(SRC)/schema/ $(DST)/schema/
	@echo "Done."

test:
	python3 -m pytest tests/ -v
