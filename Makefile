PYTHON ?= python3

.PHONY: test shortcuts check

test:
	$(PYTHON) -m unittest discover -s tests -v

shortcuts:
	$(PYTHON) -m voice_kanban.build_shortcut --platform mobile
	$(PYTHON) -m voice_kanban.build_shortcut --platform mac

check: test shortcuts
	/bin/sh -n scripts/consume.sh config.example.sh
