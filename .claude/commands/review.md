Review the current changes for code quality and correctness.

1. Check the git diff for staged and unstaged changes:
```bash
git diff
```

2. Run the linter on changed files:
```bash
ruff check src/ tests/
```

3. Run the type checker:
```bash
mypy src/conductor/
```

4. Run relevant tests based on the changed files.

Provide a summary of findings including:
- Code quality issues
- Type errors
- Test failures related to the changes
- Suggestions for improvement
