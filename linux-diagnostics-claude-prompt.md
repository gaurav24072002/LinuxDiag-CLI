# Build a Linux Compute & Storage Diagnostics CLI

Act as a Python engineer pairing with me on an SRE interview project. Implement a working local prototype called `linuxdiag` in the current repository. Inspect the repository first, give a short implementation plan, then write the code, run the tests, and demonstrate the CLI in this session. Preserve unrelated work. Use readable Python that I can explain at a whiteboard.

## Operator and scope

An engineer receives a latency alert on a Linux host. They need one short, read-only sample to see whether a logical CPU is busy, the kernel reports elevated iowait, available memory is low, a disk is moving data, a filesystem is running out of blocks or inodes, or an interface is accumulating errors or drops. They should be able to save evidence for the next engineer. Present observations and their sampling window. A threshold crossing alone does not establish root cause.

Target an unprivileged Linux user, including RHEL 9 with Python 3.9 or later. Use the Python standard library at runtime. Read kernel interfaces directly. Keep the project to a local CLI with a terminal view and JSON output. Exclude remote monitoring, agents, databases, web dashboards, AI integrations, and automated remediation.

## What I should be able to run

    linuxdiag
    linuxdiag --interval 2 --mount / --mount /var
    linuxdiag --interval 2 --format json > report.json
    linuxdiag --warn-cpu-busy 85 --warn-iowait 15 --warn-inodes-used 90
    python -m linuxdiag --help

Install the entry point through pyproject.toml. By default, take one 1-second sample, inspect the filesystem containing /, and exit. Allow repeated --mount PATH flags to select additional filesystems. Require a positive, finite interval. Allow an unprivileged user to run the CLI on a VM. Explain which counters are visible if someone runs it inside a container or on a VM hosted on a Mac. On macOS itself, give a short actionable Linux requirement.

## How sampling and each metric should work

Capture snapshot A, wait once, capture snapshot B, and calculate rates from the actual elapsed seconds using a monotonic clock. All interval-based collectors share this window. Keep UTC wall-clock time for the report. Read memory and capacity gauges once near the end. Separate parsing, delta calculations, threshold evaluation, and rendering enough to test each without sleeping.

| Area | Source and required behavior |
| --- | --- |
| CPU | Read aggregate cpu and each cpuN row from /proc/stat. Label cpuN as a logical CPU. Let total be the sum of user, nice, system, idle, iowait, irq, softirq and steal. Guest fields are already included in user/nice. Define busy for this project as executing time: 100 × delta(user + nice + system + irq + softirq) / delta(total). Report iowait and steal separately as percentages of delta(total). Document this convention so results can be compared with mpstat. The aggregate comes from the aggregate row. |
| Memory | Read MemTotal and MemAvailable from /proc/meminfo, convert KiB to bytes, and report total, available, and used percentage defined as 100 × (total − available) / total. A missing MemAvailable makes the derived metric unavailable. |
| Disk | Read sectors read and written from /proc/diskstats. For each selected whole block device report read and write MiB/s separately using delta(sectors) × 512 / elapsed_seconds / 1048576. These accounting sectors are 512 bytes even on a device with 4 KiB physical sectors. Use sysfs to distinguish partitions from whole devices. Skip loop and RAM devices by default. Keep stacked devices individually labeled and do not sum across layers. |
| Filesystem | Use os.statvfs for each requested path. Report total, used, and space available to an unprivileged user, plus inode totals, used, and available. Use f_frsize for block conversion. For df-style space use%, divide used blocks (f_blocks − f_bfree) by used blocks + f_bavail. State the inode formula and handle filesystems with no meaningful inode count. A missing path produces an issue for that path while other mounts still report. |
| NIC | Read /proc/net/dev, excluding lo by default. For each interface report RX errors, TX errors, RX drops, and TX drops separately, both as cumulative counts and increases across the sample. Evaluate thresholds against increases within the interval. A historical drop count that did not change must not trigger an alert. |

If a device appears between samples, a counter decreases, or a denominator is zero, mark the affected derived value unavailable and record the reason. A genuine zero delta on a valid counter produces a zero rate. In particular, Linux iowait can decrease and is difficult to attribute per CPU. Preserve unaffected sections when one source fails. Distinguish absence of eligible devices from a read or parse failure.

## Thresholds and reports

Support the flags below. Defaults are demo settings that an operator can override. Validate percentages in [0,100] and NIC counts as positive integers. Thresholds are inclusive and operate on unrounded values.

| Flag | Trigger |
| --- | --- |
| --warn-cpu-busy 90 | Aggregate or an individual logical CPU reaches the busy percentage |
| --warn-iowait 20 | Aggregate or an individual logical CPU reaches the iowait percentage |
| --warn-memory-used 90 | Host reaches the memory used percentage |
| --warn-space-used 90 | A requested filesystem reaches the space used percentage |
| --warn-inodes-used 90 | A requested filesystem reaches the inode used percentage |
| --warn-nic-errors 1 and --warn-nic-drops 1 | Any individual direction on an interface reaches its error or drop delta threshold |

Display disk throughput as context. A high MiB/s number alone does not identify a saturated disk. In text mode, lead with status and findings, then show compact tables with resource names, values, units, and sample duration. An alert should be as specific as “cpu3 busy 94.2% ≥ 90% over 2.01 s.” Format numbers for display only.

For --format json, emit exactly one valid JSON object on stdout. Include schema_version, UTC timestamp, hostname, elapsed_seconds, status, metrics grouped by area, alerts, and collection_issues. Give every alert a resource, metric, observed value, unit, and threshold. Use stable keys and JSON null for unavailable values. Keep diagnostics off JSON stdout and disallow NaN/Infinity. Define exit codes: 0 for complete with no alerts, 1 for complete with one or more alerts, 2 for invalid arguments or incomplete collection. An incomplete report must retain any valid alerts and take precedence in the exit status.

## Tests with explicit expected results

Use unittest or pytest. Run deterministic tests against fixtures or injected snapshots. Keep pure calculation tests runnable on macOS, where I may develop, and exercise the real collector on Linux when available.

1. CPU: over a window, delta user=20, system=10, idle=50, iowait=15, steal=5, all other included fields zero. Expect busy=30%, iowait=15%, steal=5%. Give the guest column a nonzero delta to catch accidental double counting. Test a busy single CPU with a quiet aggregate.
2. Disk: over exactly 2 seconds, 4096 additional read sectors and 2048 additional written sectors must give 1.0 MiB/s read and 0.5 MiB/s write. Include a zero-activity interval, a zero elapsed duration, and a reset counter.
3. Filesystem and memory: include reserved filesystem blocks, high inode use with plenty of bytes free, and a host with low MemFree but substantial MemAvailable.
4. NIC: cumulative RX drops 100 → 100 must not alert, while 100 → 101 must alert at the default threshold. A disappearing interface or a counter reset must not produce a negative delta.
5. CLI: verify one parseable JSON document, inclusive threshold boundaries, relevant exit codes, and a missing mount alongside a healthy one. Verify invalid input returns an actionable error.
6. Provide one reproducible demo fixture covering all collectors. A short dev-only script may run the genuine calculation, threshold, and rendering path on that fixture. Label its output synthetic. Make cpu3 cross a threshold while the aggregate stays below it. Let me reproduce the demo without creating real load or filling a filesystem.

## Deliver and verify

Keep the repository small: installable package, tests and fixtures, README, and any minimal demo script. Prefer clear function names and explicit units to clever abstractions. Include setup, exact run/test commands, metric definitions, threshold and exit-code tables, and a 90-second interview walkthrough in the README.

On Linux, run a live sample without sudo and validate against available independent tools: mpstat -P ALL 1 1 for CPU fields, iostat -dx -y 1 1 for interval disk activity (check output units), free for memory, df -h and df -i for the selected path, and ip -s link for NIC counters. Compare the same device, scope, units, and approximately the same window. Document one real observation and explain any timing or rounding differences. Avoid installing system tools automatically. If a tool or a Linux host is unavailable, say exactly what was skipped and provide the command I can run on my RHEL VM. Distinguish live results from synthetic examples.

At completion, show the project tree, the install command, the live command, the deterministic demo command, the test command and its actual result, and which live cross-checks ran. Explain the path from kernel counters to one reported alert so I can walk an interviewer through it. Only claim validation you actually performed.

Primary references for checking field definitions:
- https://docs.kernel.org/filesystems/proc.html
- https://docs.kernel.org/admin-guide/iostats.html
- https://docs.kernel.org/block/stat.html
