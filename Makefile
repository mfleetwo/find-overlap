PYTHON=python

check: unit-tests

unit-tests:
	$(PYTHON) -m pytest -k 'not test_integration'

integration-tests:
	$(PYTHON) -m pytest -k 'test_integration'

all-tests:
	$(PYTHON) -m pytest
