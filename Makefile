.PHONY: test test-unit test-cov local-play simulate lint format

test:           ## Esegue tutti i test
	pytest tests/ -v

test-unit:      ## Solo unit test
	pytest tests/unit/ -v

test-cov:       ## Test con coverage report
	pytest tests/ --cov=src --cov-report=html

local-play:     ## Partita locale interattiva
	python -m cli.play --players 2

simulate:       ## Simula 100 partite
	python -m cli.simulate --games 100 --players 4

lint:           ## Linting e type checking
	ruff check src/ tests/ cli/
	mypy src/

format:         ## Auto-format
	ruff format src/ tests/ cli/
