# Security Guidelines

- Never commit secrets, tokens, or credentials.
- Treat all user/remote inputs as untrusted.
- Use parameterized queries for SQL operations.
- Avoid exposing raw exception details containing sensitive values to end users.
- Use Databricks resource bindings and secret scopes instead of inline credentials.
