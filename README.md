# linuxdiag

A read-only, **standard-library-only** Linux CLI that takes one short sample
(default 1 s) and tells an operator, in plain text or JSON, whether anything is
wrong with compute or storage right now — and produces evidence the next
engineer can trust.

It answers the questions an operator asks first:

- Is a **logical CPU** busy? Is **iowait** elevated? (per CPU and aggregate)
- Is **memory** running low? (based on `MemAvailable`, not `MemFree`)
- Is a **disk** moving data? (MiB/s read/write, whole devices, labeled)
- Is a **filesystem** running out of blocks or inodes? (df-style used%)
- Is a **NIC** accumulating errors or drops? (delta over the window, not history)

It is deliberately *not* an agent, a daemon, a monitoring system, or a
remediation tool. It reads kernel counters, computes a few honest numbers,
compares them against thresholds you set, and prints the result. That is all.

---

## Why the design is the way it is

Three rules drive everything, and they are worth understanding because they
separate an honest tool from a misleading one.

**1. A zero delta is a real zero; a value we can't compute is "unavailable."**
If a counter is valid and simply didn't change, that is a legitimate `0.0` and
is reported as such. If we *cannot* compute a value — the denominator over the
window was zero, a counter moved backwards (a reset), an interface vanished, a
field is missing — the value is marked **unavailable with a reason**, never a
negative number and never a silent `0`. In JSON that is `"value": null` with a
`"reason"`.

**2. NIC errors/drops alert on the *delta*, not the cumulative total.**
Every interface carries historical drops. Alerting on the running total means
alerting about things that already happened. linuxdiag alerts only when the
count *rises during your sample window*. A host with 2,087 historical RX drops
that did not increase will not alert.

**3. Disk throughput is context, not a verdict.**
A high MiB/s figure does not by itself mean a disk is saturated — it depends
on the workload. linuxdiag reports it so you can correlate, but it has **no
threshold flag** and never fires an alert on its own.

---

## Requirements

- A **Linux** host (it reads `/proc`, `/sys`, and `statvfs`). RHEL/CentOS 9 or
  Ubuntu 22.04 both work.
- **Python 3.9+** — the runtime uses *only* the standard library. No `pip`
  dependencies.
- **Unprivileged** is fine: all sources it reads are world-readable. It does
  nothing that requires `sudo`.

> `python3 -m venv` is used only to get an installable entry point (and `pip`
> for the editable install). The tool itself imports nothing outside the stdlib.

---

## Install

### Option A — install the `linuxdiag` command (recommended)

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/linuxdiag            # or add .venv/bin to PATH
```

### Option B — no install

Run the package directly from the checkout:

```sh
python3 -m linuxdiag
```

Both run the same code (`linuxdiag.cli:main`).

---

## Quick start

```sh
linuxdiag                                # 1 s sample, / only, text output
linuxdiag --interval 2 --mount / --mount /var
linuxdiag --format json                  # one valid JSON object on stdout
linuxdiag --format json > report.json
```

A typical text run looks like this (synthetic values for illustration):

```
linuxdiag — status: alert  (host: vm-01, window: 2.00 s, 2026-11-04T12:00:00Z)

FINDINGS (3):
  - cpu3 busy 94.0% >= 90% over 2.00 s
  - memory used 92.0% >= 90% over 2.00 s
  - ens3 rx drops 1 >= 1 over 2.00 s

CPU (per logical CPU; busy = executing %; iowait/steal reported separately):
  NAME           BUSY%   IOWAIT%   STEAL%
  aggregate      26.0%     0.0%     0.0%
  cpu0            5.0%     0.0%     0.0%
  cpu3           94.0%     0.0%     0.0%

MEMORY:
  total=... B   available=... B   used=92.0%

DISK (MiB/s; context only — a high MiB/s does not by itself mean a saturated disk):
  DEVICE       READ MiB/s   WRITE MiB/s
  sdb               1.00         0.50

NIC (errors/drops; delta-over-window/cumulative):
  IFACE    RX ERR d/cum   TX ERR d/cum  RX DROP d/cum  TX DROP d/cum
  ens3           0/0           0/0          1/101          0/0
```

The output always **leads with status and findings**, then the per-resource
tables.

---

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--interval SECONDS` | `1.0` | Sample window. Must be positive and finite. |
| `--mount PATH` | `/` | Filesystem to inspect. **Repeatable.** |
| `--format {text,json}` | `text` | Output format. |
| `--warn-cpu-busy PCT` | `90` | Alert when any logical CPU (or aggregate) busy% **>=** PCT. `[0-100]` |
| `--warn-iowait PCT` | `20` | Alert when any logical CPU (or aggregate) iowait% **>=** PCT. `[0-100]` |
| `--warn-memory-used PCT` | `90` | Alert when memory used% **>=** PCT. `[0-100]` |
| `--warn-space-used PCT` | `90` | Alert when any filesystem space-used% **>=** PCT. `[0-100]` |
| `--warn-inodes-used PCT` | `90` | Alert when any filesystem inode-used% **>=** PCT. `[0-100]` |
| `--warn-nic-errors COUNT` | `1` | Alert when any NIC error **delta** **>=** COUNT. Positive int. |
| `--warn-nic-drops COUNT` | `1` | Alert when any NIC drop **delta** **>=** COUNT. Positive int. |

There is deliberately **no** `--warn-disk-*`: disk throughput is context only.

Thresholds are compared **inclusively** (`value >= threshold`) on the
**unrounded** value, then rounded for display.

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Complete collection, **no** alerts. |
| `1` | Complete collection, **one or more** alerts. |
| `2` | Invalid arguments, **or** an incomplete collection. |

An **incomplete** collection takes precedence over alerts: the exit code is `2`,
but the report still lists every alert it managed to compute. This is what makes
the tool safe to script — you can branch on the code and still read the findings
on a partial failure.

A collection is *incomplete* when a requested source failed to read or parse
(a `severity: "error"` issue). A *legitimate empty* — no whole block devices,
no non-loopback NIC — is recorded as a `severity: "info"` issue and does **not**
fail the run.

---

## How each metric is computed

- **CPU** (`/proc/stat`): `total` = the first 8 fields
  (`user nice system idle iowait irq softirq steal`). The `guest` /
  `guest_nice` columns are *excluded* because the kernel already counts them in
  `user`/`nice` — including them would double-count. `busy% = 100·Δ(user+nice+system+irq+softirq) /
  Δ(total)`, `iowait% = Δ(iowait)/Δ(total)`, `steal% = Δ(steal)/Δ(total)`. Rates
  use the **actual elapsed** time (monotonic clock), not the requested interval.
  This matches `mpstat`'s notion of busy.
- **Memory** (`/proc/meminfo`): `used% = 100·(MemTotal − MemAvailable)/MemTotal`.
  It is defined against `MemAvailable` (the kernel's estimate of memory usable
  without swapping), **not** `MemFree` — a host with low `MemFree` but high
  `MemAvailable` is, by this definition, mostly free.
- **Disk** (`/proc/diskstats` + `/sys/block`): `MiB/s = Δ(sectors)·512 / elapsed
  / 1048576`, read and write separately. The kernel reports **512-byte
  accounting sectors** even on 4 KiB physical media, so `512` is correct. Whole
  devices are those in `/sys/block` (partitions appear only in
  `/sys/class/block`); `loop*`, `ram*`, `zram*`, `sr*`, `scd*` are skipped by
  default. Stacked devices (`dm-*`, `nvme*`) are kept and labeled individually —
  never summed across layers.
- **Filesystem** (`os.statvfs`): space used% is computed df-style,
  `(f_blocks−f_bfree)/((f_blocks−f_bfree)+f_bavail)` — using `f_bavail` on the
  free side accounts for root-reserved blocks an unprivileged user can't use.
  Inode used% is `(f_files−f_ffree)/f_files`; if `f_files == 0` the inode
  percentage is unavailable (some network/tmp filesystems report none).
- **NIC** (`/proc/net/dev`): loopback is excluded; RX/TX errors and drops are
  reported as both the **cumulative** count and the **delta** over the window,
  and thresholds apply to the **delta** only.

---

## JSON output

`--format json` prints **exactly one valid JSON object** to stdout. Stable key
set:

```
schema_version, generated_at_utc, hostname, elapsed_seconds, status,
metrics { cpu[], memory, disk[], filesystem[], nic[] },
alerts[], collection_issues[]
```

- Every derived leaf is `{"value": <number|null>, "reason": <string|null>}` —
  a number, or an explicit null with a reason.
- Every alert has all five of: `resource`, `metric`, `observed`, `unit`,
  `threshold`.
- `status` is one of `ok` | `alert` | `incomplete`.
- Non-finite numbers (NaN/Infinity) are sanitized to `null` before
  serialization, so the output is always strictly valid JSON.
- Diagnostics stay off the data stream: in JSON mode, stdout is exactly the
  document.

---

## Testing

No third-party test framework is required. The whole suite is `unittest`,
stdlib-only, and runs cross-platform (the pure math is platform-independent; a
few live `/sys` checks skip themselves off-Linux).

```sh
python3 -m unittest discover -s tests -v
```

The tests cover the spec's six categories directly, with the spec's exact
expected numbers:

- **CPU** — a fixture with Δuser=20, system=10, idle=50, iowait=15, steal=5 and a
  non-zero guest delta must give `busy=30%`, `iowait=15%`, `steal=5%` (guest must
  not shift the totals); busy-single-CPU + quiet-aggregate; zero-delta ⇒ `0.0`;
  zero-denominator and negative-delta ⇒ unavailable.
- **Disk** — 2 s window, +4096 read / +2048 written sectors ⇒ `1.0` / `0.5` MiB/s;
  zero-activity ⇒ `0.0`; zero-elapsed ⇒ unavailable; counter reset ⇒ unavailable;
  whole-device selection keeps `sdb`/`dm-*` and drops partitions and `loop*`.
- **Filesystem + memory** — reserved blocks change the space used%; high inode%
  with low byte%; low `MemFree` + high `MemAvailable` ⇒ low used%.
- **NIC** — RX drops 100→100 ⇒ no alert; 100→101 ⇒ alert (inclusive, default 1);
  an interface disappearing or a counter resetting ⇒ unavailable, never negative.
- **CLI** — one parseable JSON document; exit codes 0/1/2; a missing mount plus a
  healthy mount (healthy still reports; missing ⇒ issue ⇒ exit 2); invalid
  input ⇒ actionable stderr message + exit 2.
- **Demo** — a deterministic fixture (below) where `cpu3` crosses the busy
  threshold while the aggregate stays below it.

---

## Deterministic demo (no load)

A small driver runs the *real* parse→compute→evaluate→render path over fixed
fixture files with the sample window pinned at 2.0 s. It applies no load and
touches no live counters — it exists so the numbers are reproducible and easy
to audit.

```sh
python3 scripts/run_demo.py
# or, using the venv:
.venv/bin/python scripts/run_demo.py
```

It is clearly labeled **SYNTHETIC** and shows the intended behaviors: `cpu3`
crosses `--warn-cpu-busy` while the aggregate stays under it; memory, a
filesystem (bytes *and* inodes), and a NIC drop-delta all alert; disk
throughput is reported but not thresholded; and the NIC alert is driven by the
delta, not the historical total.

---

## Project layout

```
linuxdiag/
  cli.py            # argparse + main(argv) -> exit code
  config.py         # Config dataclass + validate() (ranges, actionable errors)
  model.py          # Value / Alert / CollectionIssue / per-area samples / Report
  sampling.py       # the ONLY module that reads the real FS or sleeps
  cpu.py memory.py  # parse_* (thin) + compute_* (pure)
  disk.py filesystem.py nic.py
  evaluate.py       # inclusive thresholds on unrounded values -> [Alert]
  render_text.py    # status + findings first, then tables
  render_json.py    # one valid JSON object, null+reason, NaN/Inf sanitized
  report.py         # assemble Report, status, exit code
tests/              # unittest suite + tests/fixtures/demo/
scripts/run_demo.py # deterministic synthetic run
```

The layering — `parse → compute → evaluate → render`, with only `sampling.py`
touching the machine — is what lets every calculation, threshold, and render
path be tested without sleeping and without a Linux box.

---

## What it is not

- Not a daemon, agent, or persistent monitor (no state, no scheduling).
- Not a remediation tool (read-only; it reports, it never fixes).
- No databases, web dashboards, remote collectors, or AI integrations.
- Not a substitute for a tuned threshold model: pick your `--warn-*` values for
  your fleet. The defaults are simple starting points.
