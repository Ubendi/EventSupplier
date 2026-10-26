# CI/CD Setup Guide

This document explains the CI/CD configuration for the mqtt_interface_app project.

## 🚀 Quick Start

The project uses **GitHub Actions** for CI/CD. All workflows are defined in `.github/workflows/` directory.

### What's Already Set Up

1. **`test-simple.yml`** - Basic test workflow
   - Runs on push to `main` branch
   - Runs on pull requests to `main` branch
   - Tests on Python 3.14 on Ubuntu
   - Installs dependencies and runs unit tests

2. **`test.yml`** - Full test workflow (optional)
   - Tests across multiple Python versions (3.9 - 3.14)
   - Includes code linting with Ruff
   - Includes type checking with mypy
   - Uploads coverage reports to Codecov

3. **`pytest.ini`** - Pytest configuration
   - Defines test discovery patterns
   - Configures verbosity and output
   - Supports async tests

## 📋 Available Workflows

### 1. test-simple.yml (Recommended to start with)

**Trigger:** Push to `main`, or PR to `main`

**What it does:**
- Checks out code
- Sets up Python 3.14
- Installs dependencies from `requirements.txt`
- Installs pytest packages
- Runs all tests in `tests/` directory

**Status badge:**
```markdown
![Tests](https://github.com/Ubendi/EventSupplier/actions/workflows/test-simple.yml/badge.svg)
```

### 2. test.yml (Comprehensive - Optional)

**Trigger:** Push to `main` or `develop`, or PR to `main`

**What it does:**
1. **Test Job** (Matrix):
   - Runs on Python 3.9, 3.10, 3.11, 3.12, 3.13, 3.14
   - Installs dependencies
   - Runs tests with coverage
   - Uploads coverage to Codecov (if CODECOV_TOKEN is set)

2. **Lint Job:**
   - Runs Ruff linter on source and test code

3. **Type Check Job:**
   - Runs mypy on vlc_main.py for type checking

**Requirements:**
- For Codecov: Add `CODECOV_TOKEN` to GitHub Secrets

**Status badge:**
```markdown
![Full Tests](https://github.com/Ubendi/EventSupplier/actions/workflows/test.yml/badge.svg)
```

## 🛠️ Setup Instructions

### Step 1: Enable GitHub Actions

GitHub Actions is automatically enabled for public repositories. For private repos:
1. Go to your repository on GitHub
2. Click **Settings** → **Actions** → **General**
3. Ensure "Actions permissions" is set to allow workflows to run

### Step 2: Verify It Works

1. Make a small change to `vlc_main.py` (e.g., add a comment)
2. Commit and push to `main` branch
3. Go to **Actions** tab on GitHub
4. Watch the workflow run

### Step 3: (Optional) Set Up Codecov

1. Go to [codecov.io](https://codecov.io) and sign in with GitHub
2. Add your repository
3. Copy the repository token
4. On GitHub, go to **Settings** → **Secrets** → **Actions**
5. Click **New repository secret**
6. Name: `CODECOV_TOKEN`
7. Value: Your Codecov token
8. Click **Add secret**

## 📊 Understanding the Workflow Files

### test-simple.yml

```yaml
name: Python Tests (Simple)

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio pytest-mock
      - run: pytest tests/test_vlc_main.py -v
```

This is the minimal setup that:
- Runs on every push/PR to main
- Uses Python 3.14
- Installs your dependencies
- Runs your unit tests

### test.yml (Full)

This workflow has three parallel jobs:

1. **test** - Runs tests on multiple Python versions using a matrix strategy
2. **lint** - Runs Ruff linter
3. **type-check** - Runs mypy for type checking

The matrix strategy allows testing across multiple Python versions simultaneously, which helps catch compatibility issues.

## 🔧 Customizing the Workflows

### Change Python Versions

Edit `test.yml` and modify the matrix:
```yaml
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12"]
```

### Add More Test Commands

In the test job, add more run commands:
```yaml
- name: Run tests
  run: |
    cd mqtt_interface_app
    pytest tests/test_vlc_main.py -v
    pytest tests/ -v --cov=vlc_interface
```

### Add Environment Variables

```yaml
- name: Run tests
  env:
    VLC_HOST: localhost
    MQTT_HOST: localhost
  run: pytest tests/ -v
```

### Run on Schedule

Add a schedule trigger to run tests periodically:
```yaml
on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 0 * * *'  # Run daily at midnight UTC
```

## 📝 Best Practices

### 1. Test on Pull Requests
Always test pull requests before merging to catch issues early.

### 2. Start Simple
Use `test-simple.yml` first. Add complexity as needed.

### 3. Use Caching
The workflow uses `cache: 'pip'` to cache installed packages between runs, making tests faster.

### 4. Monitor Test Time
GitHub Actions has limits on free accounts:
- 2,000 minutes/month for private repos
- Unlimited for public repos (with some restrictions)
- Individual jobs limited to 6 hours

### 5. Use Status Badges
Add workflow badges to your README:
```markdown
[![Tests](https://github.com/Ubendi/EventSupplier/actions/workflows/test-simple.yml/badge.svg)](https://github.com/Ubendi/EventSupplier/actions/workflows/test-simple.yml)
```

## 🔍 Troubleshooting

### Workflow Not Triggering
- Check that the branch name matches in the `on:` section
- Verify GitHub Actions is enabled for the repository

### Tests Failing
- Check the workflow run logs on GitHub
- Run tests locally first: `pytest tests/ -v`
- Ensure all dependencies are in `requirements.txt`

### Dependencies Not Found
- Make sure all packages in your code are in `requirements.txt`
- Use `pip freeze > requirements.txt` to capture all dependencies

### Slow Tests
- Consider splitting tests into multiple jobs
- Use caching for pip installations
- Run faster tests first

## 🚀 Next Steps

1. **Commit and push** the `.github/` directory to your repository
2. **Verify** the workflow runs on GitHub Actions
3. **Monitor** the first few runs
4. **Customize** as needed for your project

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Python Testing with pytest](https://docs.pytest.org/)
- [pytest-asyncio](https://pypi.org/project/pytest-asyncio/)
- [Codecov](https://about.codecov.io/)
