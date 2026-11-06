# aws-waste-hunter

Read-only, auditable AWS waste scanner that estimates the dollars you could save.
Built by [Helyx IT](https://helyxit.com).

> **Status:** pre-alpha (slice 0: security foundations). No scanning checks yet.

## Principles
- **Read-only**: only `Describe*`/`List*`/`Get*` AWS calls, enforced in code, tests and IAM.
- **Local**: runs on your machine or CI; nothing leaves your account.
- **Auditable**: small codebase, minimal dependencies, published least-privilege IAM policy.

## Develop
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && mypy src && pytest
```

Tests use [moto](https://github.com/getmoto/moto); no AWS account or credentials needed.

## What automation can't see
This tool finds mechanical waste. Architecture, data-transfer design and commitment strategy
need a human review - that's what Helyx does.

## License
Apache-2.0
