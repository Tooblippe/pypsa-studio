@echo off
setlocal
set UV_CACHE_DIR=.uv-cache

uv run black --check pypsa_studio tests
if errorlevel 1 exit /b %errorlevel%

uv run pytest --basetemp=.pytest_tmp --tb=short --cov=pypsa_studio --cov-report=term --cov-report=html
if errorlevel 1 exit /b %errorlevel%

node --test --test-reporter=spec tests\js\canvas_helpers.test.mjs
if errorlevel 1 exit /b %errorlevel%

uv run reflex compile
if errorlevel 1 exit /b %errorlevel%
