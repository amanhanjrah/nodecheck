"""Command-line interface for nodecheck."""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Finding:
    level: str
    message: str


@dataclass
class Snapshot:
    generated_at: str
    hostname: str
    os: str
    kernel: str
    load: Optional[List[float]]
    memory_percent: Optional[float]
    filesystems: List[Dict[str, Any]]
    failed_services: Optional[List[str]]
    pending_updates: Optional[int]
    findings: List[Finding]


def _read_meminfo() -> Optional[float]:
    try:
        values: Dict[str, int] = {}
        with open("/proc/meminfo", encoding="ascii") as stream:
            for line in stream:
                key, value = line.split(":", 1)
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(value.strip().split()[0])
        total, available = values["MemTotal"], values["MemAvailable"]
        return round(100.0 * (total - available) / total, 1) if total else None
    except (OSError, KeyError, ValueError):
        return None


def _run_readonly(args: List[str], timeout: float = 5.0) -> Optional[str]:
    """Run a fixed local query without a shell; return None when unavailable."""
    try:
        result = subprocess.run(
            args, check=False, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
        if result.returncode == 0:
            return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _systemd_failures() -> Optional[List[str]]:
    if not shutil.which("systemctl"):
        return None
    output = _run_readonly(["systemctl", "--no-legend", "--plain", "--failed", "--type=service"])
    if output is None:
        return None
    return [line.split(None, 1)[0] for line in output.splitlines() if line.split()]


def _pending_updates() -> Optional[int]:
    """Count updates using the available package manager's read-only query."""
    if shutil.which("apt-get"):
        output = _run_readonly(["apt-get", "--simulate", "upgrade"], timeout=20.0)
        if output is not None:
            return sum(1 for line in output.splitlines() if line.startswith("Inst "))
    if shutil.which("dnf"):
        # dnf check-update returns 100 when updates are available.
        try:
            result = subprocess.run(
                ["dnf", "-q", "--cacheonly", "check-update"], capture_output=True, text=True,
                timeout=20.0, env={**os.environ, "LC_ALL": "C"}, check=False,
            )
            if result.returncode in (0, 100):
                return sum(1 for line in result.stdout.splitlines() if line and not line.startswith("Last metadata"))
        except (OSError, subprocess.TimeoutExpired):
            return None
    # Arch's checkupdates refreshes package databases, so it is deliberately
    # omitted to preserve the collector's strictly read-only behavior.
    return None


def _findings(filesystems: List[Dict[str, Any]], memory: Optional[float], load: Optional[List[float]], failed: Optional[List[str]], updates: Optional[int]) -> List[Finding]:
    findings: List[Finding] = []
    for fs in filesystems:
        if fs["usage_percent"] >= 90:
            findings.append(Finding("WARN", "{} is {}% full".format(fs["mountpoint"], fs["usage_percent"])))
        if fs["inode_percent"] is not None and fs["inode_percent"] >= 90:
            findings.append(Finding("WARN", "{} is {}% inode-full".format(fs["mountpoint"], fs["inode_percent"])))
    if memory is not None:
        findings.append(Finding("WARN" if memory >= 90 else "OK", "Memory usage is {:.1f}%{}".format(memory, " (high)" if memory >= 90 else " within limits")))
    else:
        findings.append(Finding("INFO", "Memory usage unavailable"))
    if load:
        cpu_count = os.cpu_count() or 1
        high_load = load[0] >= cpu_count * 2
        findings.append(Finding("WARN" if high_load else "INFO", "Load average: {:.2f}, {:.2f}, {:.2f}{}".format(*load, " (high for {} CPUs)".format(cpu_count) if high_load else "")))
    if failed is None:
        findings.append(Finding("INFO", "Failed systemd services unavailable"))
    elif failed:
        findings.append(Finding("WARN", "{} systemd services failed".format(len(failed))))
    else:
        findings.append(Finding("OK", "No failed systemd services"))
    if updates is not None and updates:
        findings.append(Finding("INFO", "{} package updates available".format(updates)))
    elif updates == 0:
        findings.append(Finding("OK", "No package updates available"))
    else:
        findings.append(Finding("INFO", "Package update count unavailable"))
    if not filesystems:
        findings.append(Finding("INFO", "Filesystem usage unavailable"))
    return findings


def collect_snapshot() -> Snapshot:
    filesystems: List[Dict[str, Any]] = []
    seen = set()
    # shutil.disk_usage is read-only; /proc/mounts supplies mount points without shell parsing.
    try:
        with open("/proc/mounts", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                fields = line.split()
                if len(fields) >= 3:
                    source, mount, filesystem = fields[:3]
                    mount_options = fields[3].split(",") if len(fields) >= 4 else []
                    mount = mount.replace("\\040", " ")
                    # Read-only filesystems (commonly snap squashfs images)
                    # are full by design and obscure actionable writable volumes.
                    if filesystem == "squashfs" or "ro" in mount_options:
                        continue
                    if mount not in seen:
                        seen.add(mount)
                        try:
                            usage = shutil.disk_usage(mount)
                            stats = os.statvfs(mount)
                            used_inodes = stats.f_files - stats.f_ffree
                            inode_percent = round(100.0 * used_inodes / stats.f_files, 1) if stats.f_files else None
                            filesystems.append({
                                "mountpoint": mount,
                                "usage_percent": round(100.0 * usage.used / usage.total, 1) if usage.total else 0.0,
                                "inode_percent": inode_percent,
                                "used_bytes": usage.used,
                                "total_bytes": usage.total,
                            })
                        except OSError:
                            continue
    except OSError:
        pass
    try:
        load = [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        load = None
    memory = _read_meminfo()
    failed = _systemd_failures()
    updates = _pending_updates()
    distro = platform.system()
    try:
        with open("/etc/os-release", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip().strip("\\\"")
                    break
    except OSError:
        pass
    return Snapshot(
        generated_at=datetime.now(timezone.utc).isoformat(), hostname=platform.node() or "unknown",
        os=distro, kernel=platform.release(), load=load,
        memory_percent=memory, filesystems=filesystems, failed_services=failed,
        pending_updates=updates,
        findings=_findings(filesystems, memory, load, failed, updates),
    )


def demo_snapshot() -> Snapshot:
    filesystems = [
        {"mountpoint": "/", "usage_percent": 68.0, "inode_percent": 12.4, "used_bytes": 73014444032, "total_bytes": 107374182400},
        {"mountpoint": "/var", "usage_percent": 91.0, "inode_percent": 34.2, "used_bytes": 97710505984, "total_bytes": 107374182400},
    ]
    memory, load, failed, updates = 62.5, [0.42, 0.58, 0.61], ["demo-worker.service", "demo-backup.service"], 14
    return Snapshot(
        generated_at="2025-01-15T12:00:00+00:00", hostname="demo-linux-host",
        os="Linux 6.8.0-demo", kernel="6.8.0-demo", load=load, memory_percent=memory,
        filesystems=filesystems, failed_services=failed, pending_updates=updates,
        findings=_findings(filesystems, memory, load, failed, updates),
    )


def _text(snapshot: Snapshot) -> str:
    lines = ["{}  {}".format(item.level, item.message) for item in snapshot.findings]
    lines.append("INFO  Host: {} | {} | kernel {}".format(snapshot.hostname, snapshot.os, snapshot.kernel))
    return "\n".join(lines) + "\n"


def _html(snapshot: Snapshot) -> str:
    rows = "\n".join(
        "<tr><td>{}</td><td>{}%</td><td>{}%</td></tr>".format(
            html.escape(fs["mountpoint"]), fs["usage_percent"],
            "n/a" if fs["inode_percent"] is None else fs["inode_percent"],
        ) for fs in snapshot.filesystems
    )
    findings = "\n".join("<li><strong>{}</strong> {}</li>".format(html.escape(item.level), html.escape(item.message)) for item in snapshot.findings)
    return """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>nodecheck report — {host}</title>
<style>body{{font:16px system-ui,sans-serif;max-width:880px;margin:2rem auto;padding:0 1rem;color:#172033}}table{{border-collapse:collapse}}td,th{{padding:.5rem 1rem;border:1px solid #ccd2dc;text-align:left}}li{{margin:.5rem 0}}.meta{{color:#586174}}</style>
<h1>nodecheck health report</h1><p class="meta">{host} · {os} · kernel {kernel}<br>Generated {generated}</p>
<h2>Findings</h2><ul>{findings}</ul><h2>Filesystems</h2><table><thead><tr><th>Mount</th><th>Space used</th><th>Inodes used</th></tr></thead><tbody>{rows}</tbody></table>
<h2>System details</h2><ul><li>Memory used: {memory}</li><li>Load average: {load}</li><li>Failed services: {services}</li><li>Pending package updates: {updates}</li></ul>
</html>
""".format(host=html.escape(snapshot.hostname), os=html.escape(snapshot.os), kernel=html.escape(snapshot.kernel), generated=html.escape(snapshot.generated_at), findings=findings, rows=rows,
           memory="unavailable" if snapshot.memory_percent is None else "{:.1f}%".format(snapshot.memory_percent),
           load="unavailable" if snapshot.load is None else html.escape(", ".join("{:.2f}".format(value) for value in snapshot.load)),
           services="unavailable" if snapshot.failed_services is None else (html.escape(", ".join(snapshot.failed_services)) or "none"),
           updates="unavailable" if snapshot.pending_updates is None else str(snapshot.pending_updates))


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Convenience: `nodecheck --demo` means `nodecheck scan --demo`.
    if argv and argv[0] == "--demo":
        argv.insert(0, "scan")
    parser = argparse.ArgumentParser(prog="nodecheck", description="Read-only Linux host health snapshot and troubleshooting report.")
    subparsers = parser.add_subparsers(dest="command")
    scan = subparsers.add_parser("scan", help="scan the local host (default)")
    scan.add_argument("--demo", action="store_true", help="show fixed sample data without inspecting this host")
    report = subparsers.add_parser("report", help="write a health report")
    report.add_argument("--format", choices=("html", "json", "text"), default="html")
    report.add_argument("--output", "-o", default="-", help="output path (default: stdout)")
    report.add_argument("--demo", action="store_true", help="use fixed sample data without inspecting this host")
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "scan"
        args.demo = False
    snapshot = demo_snapshot() if args.demo else collect_snapshot()
    if args.command == "scan":
        sys.stdout.write(_text(snapshot))
        return 0
    if args.format == "json":
        content = json.dumps(asdict(snapshot), indent=2) + "\n"
    elif args.format == "html":
        content = _html(snapshot)
    else:
        content = _text(snapshot)
    if args.output == "-":
        sys.stdout.write(content)
    else:
        Path(args.output).write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
