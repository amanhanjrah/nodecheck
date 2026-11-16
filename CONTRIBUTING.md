# Contributing to nodecheck

Thanks for helping make nodecheck useful and safe for Linux administrators.

## Development setup

- Python 3.9 or newer
- No runtime dependencies; tests use the Python standard library

From the repository root:

```sh
make -C nodecheck check
python3 -m pip install --user -e ./nodecheck
nodecheck scan --demo
```

## Changes

1. Open an issue for substantial changes and describe the use case.
2. Keep collection read-only, local, bounded in time, and tolerant of missing
   commands, restricted permissions, and non-systemd systems.
3. Never add network access, telemetry, automatic remediation, or privileged
   operations without prior discussion and explicit documentation.
4. Add or update tests and documentation, then run `make -C nodecheck check`.
5. Submit a focused pull request with a clear summary and test results.

By contributing, you agree that your contributions are provided under the
project's MIT License.
