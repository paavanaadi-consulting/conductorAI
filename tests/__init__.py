"""
ConductorAI Test Suite
======================

Test organization mirrors the source code structure:
    tests/
    ├── test_core/          → Tests for conductor.core (config, models, enums)
    ├── test_agents/        → Tests for conductor.agents (base + specialized)
    ├── test_orchestration/ → Tests for conductor.orchestration (bus, state, etc.)
    ├── test_infrastructure/→ Tests for conductor.infrastructure (storage, repos)
    ├── test_integrations/  → Tests for conductor.integrations (LLM, notifications)
    ├── test_integration/   → End-to-end integration tests
    └── conftest.py         → Shared pytest fixtures

Running Tests:
    pytest                          # Run all tests
    pytest tests/test_core/         # Run only core tests
    pytest -m unit                  # Run only unit tests
    pytest -m integration           # Run only integration tests
    pytest --cov=conductor          # Run with coverage report
"""
