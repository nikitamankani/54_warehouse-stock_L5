# Lab 5 – Reflection

**1. Which issues were the easiest to fix, and which were the hardest? Why?**

The easiest were the Flake8 and Pylint style issues: blank lines, trailing whitespace, long lines, snake_case names, docstrings and unused imports. They are mechanical and the report tells you the exact line and what to change. Swapping `md5` for `sha256` and adding a `with open(...)` were also quick.

The hardest was the `eval()` in `applyAdjustment`. I couldn't just delete it, because the feature (a supervisor typing `current * 2`) still had to work. `ast.literal_eval` doesn't allow variables like `current`, so I wrote a small evaluator that walks the AST and only accepts ints, `current` and `+ - * //`. Removing the hardcoded password was also tricky: the program still needs a password, so it had to come from an environment variable instead. Bandit then flagged my constant `PASSWORD_ENV_VAR` too, just because the name contained "password", so I renamed it.

**2. Did the static analysis tools report any false positives? If so, describe one example.**

Yes. After my first fix, Bandit reported B105 (hardcoded password) on `PASSWORD_ENV_VAR = "WH_SUPERVISOR_PASSWORD"`. That string is only the *name* of an environment variable, not a secret. Bandit just pattern-matches on variable names containing "password". I renamed it to `SUPERVISOR_ENV_VAR`. Adding `# nosec` would also have been acceptable.

The MD5 finding (B324) is borderline. The hash is only a 6-character label fingerprint, not a security feature, so `usedforsecurity=False` would have been a valid fix. I chose SHA-256 anyway because it costs nothing.

**3. How would you integrate static analysis tools into your actual software development workflow?**

- **Locally:** run Flake8 and Pylint in the editor (VS Code extensions) so issues show up while typing, and add a `pre-commit` hook that runs Flake8, Pylint and Bandit before each commit.
- **In CI:** add a GitHub Actions workflow that runs all three tools on every push and pull request, and fails the build if Bandit finds Medium/High issues, Flake8 finds anything, or the Pylint score drops below a threshold (e.g. `--fail-under=9.5`).
- **Configuration:** keep the settings in `.pylintrc` / `setup.cfg` so the whole team uses the same rules, and suppress confirmed false positives inline with a comment explaining why.

**4. What tangible improvements did you observe in the code quality, readability, or potential robustness after applying the fixes?**

- **Security:** no `eval()`, no password in the source, and no weak hash. Bandit went from 5 issues (1 High, 2 Medium) to 0.
- **Correctness:** the program no longer creates negative stock (-4), stores an int SKU that turns into a string after save/load, or silently deletes WID-001 when asked to remove 500 units. It now logs a clear warning in each case. The mutable default list bug is gone. None of these output bugs were flagged by a tool; I only found them by running the program and reading the output.
- **Robustness:** files are always closed (`with`), errors are no longer swallowed by `except: pass`, and `get_stock` doesn't crash on unknown SKUs.
- **Readability:** PEP 8 names, docstrings on every function, f-strings and consistent formatting. Pylint went from 4.48/10 to 10.00/10 and Flake8 from 19 warnings to 0.
