.PHONY: help link link-dry-run doctor check

help:
	@echo "  make link          - Symlink skills into each agent's skills directory (idempotent; also run after git pull)"
	@echo "  make link-dry-run  - Preview what link would change"
	@echo "  make doctor        - Report link, dependency and environment status"
	@echo "  make check         - Lint scripts, validate skills, run tests (what CI runs)"

link:
	bash bin/link.sh

link-dry-run:
	bash bin/link.sh --dry-run

doctor:
	bash bin/link.sh --doctor

check:
	bash bin/check.sh
