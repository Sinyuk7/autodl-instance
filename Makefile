.PHONY: build clean test test-unit test-integration lint todo release smoke version help

HATCH := $(shell command -v hatch 2>/dev/null || echo .venv/bin/hatch)
VERSION := $(shell python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo "0.0.0")
WHEEL := dist/autodl_instance-$(VERSION)-py3-none-any.whl

help:
	@echo "autodl-instance $(VERSION)"
	@echo ""
	@echo "  make build          Build wheel"
	@echo "  make clean          Remove build artifacts"
	@echo "  make test           Run all tests"
	@echo "  make test-unit      Run unit tests only"
	@echo "  make test-integration  Run integration tests only"
	@echo "  make lint           Run ruff check"
	@echo "  make todo           List TODOs (exclude noise)"
	@echo "  make release        Tag + push (after smoke)"
	@echo "  make smoke          Local wheel install + verify"

build:
	$(HATCH) build

clean:
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

lint:
	ruff check src/ tests/

todo:
	@echo "=== src/ ==="
	@grep -rn "TODO\|FIXME\|HACK\|XXX" src/ --include="*.py" 2>/dev/null || echo "  (none)"
	@echo ""
	@echo "=== tests/ ==="
	@grep -rn "TODO\|FIXME\|HACK\|XXX" tests/ --include="*.py" 2>/dev/null || echo "  (none)"

smoke: build
	@echo "=== Smoke: installing $(WHEEL) ==="
	pip install $(WHEEL) --force-reinstall --no-deps
	@echo ""
	@echo "=== Smoke: autodl --help ==="
	autodl --help
	@echo ""
	@echo "=== Smoke: autodl status ==="
	-autodl status 2>/dev/null || echo "  (expected: no config yet)"
	@echo ""
	@echo "=== Smoke: autodl doctor ==="
	-autodl doctor 2>/dev/null || echo "  (expected: no config yet)"
	@echo ""
	@echo "=== Smoke: uninstall ==="
	pip uninstall autodl-instance -y
	@echo ""
	@echo "=== Smoke PASSED ==="

release: build
	@test "$(VERSION)" != "0.0.0" || (echo "ERROR: cannot read version from pyproject.toml" && exit 1)
	@echo "=== Release v$(VERSION) ==="
	@echo "wheel: $(WHEEL)"
	@echo ""
	@echo "Next steps:"
	@echo "  git tag v$(VERSION)"
	@echo "  git push origin v$(VERSION)"
	@echo "  gh release create v$(VERSION) $(WHEEL) --title 'v$(VERSION)'"
	@echo "  $(HATCH) publish  # for PyPI"

version:
	@echo $(VERSION)
