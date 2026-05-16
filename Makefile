.PHONY: deps test scan serve doctor version

deps:
	./scripts/session-browser.sh deps

test:
	./scripts/session-browser.sh test

scan:
	./scripts/session-browser.sh scan

serve:
	./scripts/session-browser.sh serve

doctor:
	bash scripts/harness/doctor.sh

version:
	./scripts/session-browser.sh version
