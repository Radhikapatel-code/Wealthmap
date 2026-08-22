.PHONY: help install build-engine test-rust test-python test run-api run-dashboard

help:
	@echo "Available commands:"
	@echo "  make install        Install Python dependencies and maturin"
	@echo "  make build-engine   Build and install Rust wealthmap-engine extension"
	@echo "  make test-rust      Run Rust unit & integration tests"
	@echo "  make test-python    Run Python test suite"
	@echo "  make test           Run all tests (Rust and Python)"
	@echo "  make run-api        Start FastAPI backend server"
	@echo "  make run-dashboard  Start Streamlit dashboard"

install:
	pip install -r requirements.txt
	pip install maturin

build-engine:
	cd wealthmap-engine && maturin develop --release

test-rust:
	cargo test --release --manifest-path wealthmap-engine/Cargo.toml

test-python:
	python -m pytest tests/ -v

test: test-rust test-python

run-api:
	uvicorn api.main:app --reload --port 8000

run-dashboard:
	streamlit run dashboard/app.py --server.port 8501
