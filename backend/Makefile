.PHONY: test test-regression test-10x cache-clear

test:
	PYTHONPATH=src python -m pytest -x

test-regression:
	PYTHONPATH=src python -m pytest tests/test_regression.py --regression -v

test-10x:
	bash scripts/test_10x.sh

cache-clear:
	PYTHONPATH=src python scripts/clear_llm_cache.py
