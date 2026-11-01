# Contributing

Thank you for your interest in contributing to MotoGP Sensor!

## Branch model

This project uses two contribution paths depending on what you are changing.

### Code changes

For changes to the integration itself — sensors, binary sensors, configuration flow, coordinator logic, fixes, features, tests — use the code path:

- `dev` — the active development branch. All code contributions must target this branch.
- `beta` — pre-release testing. Promoted from `dev` by the maintainer.
- `main` — stable production releases. Promoted from `beta` by the maintainer.

The `beta` and `main` branches are managed exclusively by the maintainer. PRs targeting those branches are closed automatically.

### Documentation changes

For changes to documentation that are independent of any code change, use the content path:

- `content` — the dedicated branch for documentation contributions. PRs targeting this branch are merged directly to `main` by the maintainer, without going through beta.

No version bump or release is triggered when only documentation files change.

### Which branch should I target?

| What I am changing | Target branch |
|---|---|
| Integration code, sensors, fixes, features | `dev` |
| Tests only | `dev` |
| Documentation for an upcoming code change | `dev` (keep docs with the code) |
| Standalone documentation fix or update | `content` |

If your PR mixes code changes with documentation changes, target `dev`. The docs will be published when the code ships.

## How to submit a pull request

1. Fork the repository.
2. Identify the correct target branch using the table above.
3. Create a feature branch based on that target branch in your fork.
4. Make your changes and commit them with clear messages.
5. Open a pull request against the correct branch of this repository.

## Code layout and checks

- `api.py` does the HTTP requests, `parsers.py` turns the JSON into the dataclasses of `models.py`. Neither depends on Home Assistant state, so new parsing logic gets a unit test in `tests/test_parsers.py`.
- `coordinator.py` holds the data update coordinators, the platforms only read their data.
- `strings.json` is the source of the translations: copy changes to `translations/en.json` and translate them in the other files.

Before opening a pull request:

```bash
pip install -r requirements_test.txt
pytest
ruff check . && ruff format --check .
```

CI also runs hassfest and the HACS validation.

## API data and reverse engineering

MotoGP Sensor relies on public REST endpoints exposed by Pulselive. If you discover changes in the API response schema, please open an issue describing the new structure before submitting a fix — this helps coordinate testing across different race weekend scenarios. Add the new payload to `tests/fixtures` so the change is covered by the tests.

## Questions

If you are unsure whether a change fits the project direction, open an issue before starting work. This prevents effort being spent on contributions that may not be accepted.
