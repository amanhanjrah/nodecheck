# nodecheck

A read-only Linux host health and troubleshooting CLI. `nodecheck` collects a
local snapshot, highlights common issues, and writes a report that can be
shared with an administrator. It uses only the Python standard library and
degrades gracefully when optional Linux tools are unavailable.

**No remediation, package installation, telemetry, or network requests.**

## Try it safely

See fixed sample output without querying your machine:

```console
$ ./bin/nodecheck scan --demo
WARN  /var is 91.0% full
WARN  2 systemd services failed
OK  Memory usage is 62.5% within limits
INFO  Load average: 0.42, 0.58, 0.61
INFO  14 package updates available
INFO  Host: demo-linux-host | Linux 6.8.0-demo | kernel 6.8.0-demo
```

The sample is static, reproducible, and contains no real host information.
A ready-to-view [sample HTML report](examples/demo-report.html) and a short
[asciinema terminal recording](examples/demo.cast) are included. The recording
can be replayed with `asciinema play examples/demo.cast` when asciinema is
installed. Generate the sample report as HTML:

```sh
./bin/nodecheck report --demo --format html --output report.html
```

Other formats are `json` and `text`. Omit `--output` (or use `-`) to write
the report to standard output.

## Install

Install with pipx from a Git checkout:

```sh
pipx install ./nodecheck
nodecheck scan --demo
nodecheck report --format html --output report.html
```

Or run directly from checkout using `./bin/nodecheck`. To install from PyPI
once published: `pipx install nodecheck`.

## Scan a host

```sh
nodecheck scan
nodecheck report --format html --output report.html
nodecheck report --format json --output report.json
```

`scan` can also be invoked as `nodecheck` with no subcommand, or `nodecheck --demo`
for sample output. The scan reports
filesystem space and inode use, memory, load averages, failed systemd services,
OS and kernel details, and pending package updates where a supported package
manager query is available (apt or dnf). Package queries
use local package-manager metadata and may take up to 20 seconds. nodecheck
does not refresh that metadata.

Filesystem and memory figures are read from `/proc`, `statvfs`, and standard
Python APIs. The systemd query is `systemctl --failed`, and package commands
are limited to query operations. Arch database refresh is intentionally not
attempted because its common update-check helper refreshes package metadata.
Read-only squashfs images are excluded from disk alerts because they are full
by design. Some hosts may restrict information access; unavailable checks are
reported as `INFO` rather than treated as healthy.

## Development

```sh
make -C nodecheck check
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md),
[SECURITY.md](SECURITY.md), and [LICENSE](LICENSE).

## Privacy

Reports include host name, OS/kernel, mount points, and health measurements.
Review output before sharing it. The `--demo` mode uses only bundled sample
data and does not inspect the current host.
