PYTHON ?= python3

.PHONY: test shortcuts launchagent native check

test:
	$(PYTHON) -m unittest discover -s tests -v

shortcuts:
	$(PYTHON) -m voice_kanban.build_shortcut --platform mobile
	$(PYTHON) -m voice_kanban.build_shortcut --platform mac-audio
	$(PYTHON) -m voice_kanban.build_shortcut --platform mac

launchagent:
	$(PYTHON) -m voice_kanban.build_launchagent

native:
	mkdir -p dist .local/swift-module-cache
	xcrun swiftc -parse-as-library -O -module-cache-path .local/swift-module-cache native/transcribe.swift -o dist/concodispatch-transcribe
	xcrun swiftc -parse-as-library -O -module-cache-path .local/swift-module-cache native/receiver.swift -o dist/ConcoDispatchReceiver

check: test shortcuts launchagent
	/bin/sh -n scripts/consume.sh config.example.sh
