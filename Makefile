PLUGINS := claude-usage.5s.py

# SwiftBar stores its plugin folder in a preference. Fall back to the default
# location if that isn't set. Override explicitly with:
#   make install PLUGIN_DIR="/path/to/your/plugin/folder"
PLUGIN_DIR ?= $(shell defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null)
ifeq ($(strip $(PLUGIN_DIR)),)
	PLUGIN_DIR := $(HOME)/Library/Application Support/SwiftBar/Plugins
endif

.PHONY: install uninstall debug

install:
	@command -v swiftbar >/dev/null 2>&1 || test -d "/Applications/SwiftBar.app" || \
		echo "note: SwiftBar not found — install it with: brew install --cask swiftbar"
	@mkdir -p "$(PLUGIN_DIR)"
	@for p in $(PLUGINS); do \
		cp "$$p" "$(PLUGIN_DIR)/$$p"; \
		chmod +x "$(PLUGIN_DIR)/$$p"; \
		echo "Installed $$p → $(PLUGIN_DIR)"; \
	done
	@open -g -a SwiftBar 2>/dev/null || true
	@open "swiftbar://refreshallplugins" 2>/dev/null || true
	@echo "Done. If you don't see it, open SwiftBar → Refresh all."

uninstall:
	@for p in $(PLUGINS); do \
		rm -f "$(PLUGIN_DIR)/$$p" && echo "Removed $$p from $(PLUGIN_DIR)"; \
	done
	@open "swiftbar://refreshallplugins" 2>/dev/null || true

debug:
	@python3 claude-usage.5s.py --debug
