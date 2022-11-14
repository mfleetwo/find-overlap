PYTHON=python

check:
	PATH="$${PWD}:$${PATH}" $(PYTHON) -m pytest
