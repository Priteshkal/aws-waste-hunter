"""CloudWatch metric reads with a hard cost cap.

``GetMetricData`` is billed per metric requested (about $0.01 per 1,000). Every query is
charged against a :class:`MetricBudget` *before* the call is made; when the budget is
exhausted the check stops, reports what it found so far and records an error. A scan can
therefore never run up an unbounded CloudWatch bill.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from aws_waste_hunter.models import Finding
from aws_waste_hunter.readonly import client

DEFAULT_MAX_METRICS = 200  # per (account, region): ~$0.002 of CloudWatch charges
LOOKBACK_DAYS = 7
USD_PER_METRIC = 0.00001
_BATCH = 100  # queries per GetMetricData call (API limit is 500)


class MetricBudgetExceeded(RuntimeError):
    """Raised when a check would exceed the metric budget; carries findings found so far."""

    def __init__(self, message: str, partial: list[Finding] | None = None) -> None:
        super().__init__(message)
        self.partial: list[Finding] = partial or []


@dataclass
class MetricBudget:
    max_metrics: int = DEFAULT_MAX_METRICS
    used: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def charge(self, n: int) -> None:
        with self._lock:
            if self.used + n > self.max_metrics:
                raise MetricBudgetExceeded(
                    f"metric budget of {self.max_metrics} reached "
                    f"(~${self.max_metrics * USD_PER_METRIC:.3f}); "
                    "raise it with --max-metrics to scan the rest"
                )
            self.used += n

    @property
    def estimated_cost_usd(self) -> float:
        return round(self.used * USD_PER_METRIC, 5)


def lookback_start(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) - timedelta(days=LOOKBACK_DAYS)


def sum_metrics(
    session: Any,
    region: str,
    budget: MetricBudget,
    queries: dict[str, tuple[str, str, list[dict[str, str]]]],
    now: datetime | None = None,
) -> dict[str, float]:
    """Sum of each metric over the lookback window.

    ``queries`` maps a caller key to (namespace, metric name, dimensions). A metric with no
    datapoints sums to 0.0 (CloudWatch publishes nothing when there was no activity).
    """
    cw = client(session, "cloudwatch", region)
    end = now or datetime.now(timezone.utc)
    start = lookback_start(end)
    totals: dict[str, float] = {}
    items = list(queries.items())
    for i in range(0, len(items), _BATCH):
        chunk = items[i : i + _BATCH]
        budget.charge(len(chunk))
        ids = {f"q{n}": key for n, (key, _) in enumerate(chunk)}
        data_queries = [
            {
                "Id": qid,
                "MetricStat": {
                    "Metric": {"Namespace": ns, "MetricName": name, "Dimensions": dims},
                    "Period": 86400,
                    "Stat": "Sum",
                },
                "ReturnData": True,
            }
            for (qid, (_, (ns, name, dims))) in zip(ids, chunk, strict=True)
        ]
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "MetricDataQueries": data_queries,
                "StartTime": start,
                "EndTime": end,
            }
            if token:
                kwargs["NextToken"] = token
            resp = cw.get_metric_data(**kwargs)
            for res in resp["MetricDataResults"]:
                key = ids[res["Id"]]
                totals[key] = totals.get(key, 0.0) + float(sum(res.get("Values", [])))
            token = resp.get("NextToken")
            if not token:
                break
        for key in ids.values():
            totals.setdefault(key, 0.0)
    return totals
