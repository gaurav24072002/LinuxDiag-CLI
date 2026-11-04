"""Network interface errors/drops from /proc/net/dev.

Each interface row has 16 numbers after the name:
    RX: bytes packets errs drop fifo frame compressed multicast
    TX: bytes packets errs drop fifo colls carrier compressed

We report RX/TX errors and RX/TX drops, each as:
  * the *cumulative* count (the latest snapshot value), and
  * the *delta* across the sample window.

Thresholds are evaluated against the **delta** only. A historical drop count
that did not change during the window must not alert, so a zero delta is a
legitimately-available ``0.0``. If an interface appears or disappears between
snapshots, or a counter resets backwards, the delta is unavailable — never a
negative number. Loopback is excluded by default.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from linuxdiag.model import NicSample, Value

DEFAULT_NETDEV_PATH = "/proc/net/dev"
DEFAULT_EXCLUDE = ("lo",)


def parse_netdev(text: str) -> Dict[str, Dict[str, int]]:
    """Return ``{iface: {rx_errors, rx_drops, tx_errors, tx_drops}}``.

    The two header lines contain no ':' and are skipped.
    """
    result: Dict[str, Dict[str, int]] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        fields = rest.split()
        if len(fields) < 16:
            continue
        try:
            nums = [int(x) for x in fields[:16]]
        except ValueError:
            continue
        result[name] = {
            "rx_errors": nums[2],
            "rx_drops": nums[3],
            "tx_errors": nums[10],
            "tx_drops": nums[11],
        }
    return result


def read_netdev(path: str = DEFAULT_NETDEV_PATH) -> str:
    with open(path, "r", encoding="ascii") as handle:
        return handle.read()


def _delta(a_val: Optional[int], b_val: Optional[int]) -> Value:
    if a_val is None or b_val is None:
        return Value.unavailable("interface absent in one snapshot")
    d = b_val - a_val
    if d < 0:
        return Value.unavailable("counter reset (delta negative)")
    return Value.number(float(d))


def _field(a_rec: Optional[Dict], b_rec: Optional[Dict], key: str) -> Tuple[int, Value]:
    """Return (cumulative, delta) for one counter on one interface."""
    a_val = a_rec.get(key) if a_rec else None
    b_val = b_rec.get(key) if b_rec else None
    cumulative = b_val if b_val is not None else a_val
    return (cumulative if cumulative is not None else 0), _delta(a_val, b_val)


def compute_nic(
    a: Dict[str, Dict[str, int]],
    b: Dict[str, Dict[str, int]],
    exclude: Tuple[str, ...] = DEFAULT_EXCLUDE,
) -> List[NicSample]:
    """Report each non-excluded interface seen in either snapshot."""
    names = sorted((set(a) | set(b)) - set(exclude))
    samples: List[NicSample] = []
    for name in names:
        a_rec = a.get(name)
        b_rec = b.get(name)
        rx_errors_cum, rx_errors_delta = _field(a_rec, b_rec, "rx_errors")
        tx_errors_cum, tx_errors_delta = _field(a_rec, b_rec, "tx_errors")
        rx_drops_cum, rx_drops_delta = _field(a_rec, b_rec, "rx_drops")
        tx_drops_cum, tx_drops_delta = _field(a_rec, b_rec, "tx_drops")
        samples.append(NicSample(
            name=name,
            rx_errors_cumulative=rx_errors_cum, rx_errors_delta=rx_errors_delta,
            tx_errors_cumulative=tx_errors_cum, tx_errors_delta=tx_errors_delta,
            rx_drops_cumulative=rx_drops_cum, rx_drops_delta=rx_drops_delta,
            tx_drops_cumulative=tx_drops_cum, tx_drops_delta=tx_drops_delta,
        ))
    return samples
