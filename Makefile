PYTHON ?= python3

.PHONY: check

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m compileall -q src
	./bin/nodecheck --help >/dev/null
	./bin/nodecheck scan --demo >/dev/null
	./bin/nodecheck report --demo --format html >/dev/null
