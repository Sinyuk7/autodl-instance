# tests/ Knowledge Base

**Purpose:** Test suite - unit and integration tests

## STRUCTURE

```
tests/
├── conftest.py          # Pytest fixtures
├── mocks.py             # MockContext for unit tests
├── unit/                # Unit tests (isolated)
│   ├── addons/          # Per-addon tests
│   ├── test_main.py
│   └── test_pipeline.py
└── integration/         # Integration tests (full pipeline)
    ├── test_setup_pipeline.py
    ├── test_start_pipeline.py
    └── test_sync_pipeline.py
```

## FIXTURES (conftest.py)

- `temp_project_dir` - Temporary project root
- `mock_context` - Pre-configured MockContext
- `addon_under_test` - Instantiate specific addon

## MOCKS

**`MockContext`:**
- In-memory state manager
- Captured commands (for assertions)
- Temp directories for file operations

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Test specific addon | `unit/addons/test_{name}_addon.py` |
| Test pipeline flow | `test_pipeline.py` or `integration/test_*_pipeline.py` |
| Add new fixture | `conftest.py` |
| Update mocks | `mocks.py` |

## CONVENTIONS

**Unit Tests:**
- Mock all external dependencies (network, filesystem)
- Use `MockContext` for addon tests
- One test file per addon

**Integration Tests:**
- Run full pipeline with mocked installers and temporary directories; no partial lifecycle options
- Use temp directories (not real paths)
- Mark slow tests with `@pytest.mark.slow`

**Running Tests:**
```bash
# All tests
pytest tests/ -v

# Unit only
pytest tests/unit/ -v

# Specific addon
pytest tests/unit/addons/test_system_addon.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```
