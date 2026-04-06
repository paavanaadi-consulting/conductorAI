Run the test suite and report results.

```bash
pytest --cov=conductor -q
```

If tests fail, analyze the failures and suggest fixes. If $ARGUMENTS is provided, pass it to pytest as additional arguments (e.g., a specific test file or marker).

```bash
pytest $ARGUMENTS
```
