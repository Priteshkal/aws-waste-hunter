"""Pricing used for dollar estimates.

Prices come from the AWS Price List API (``pricing:GetProducts``, read-only) per region, are
cached on disk for 24h, and fall back to a static us-east-1 list-price table if the live
lookup fails. Every report states which source was used.

Defences: live and cached values must be positive numbers within a sane band of the offline
reference (guards parsing mistakes and a tampered cache), and the cache file is private (0600).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aws_waste_hunter.readonly import client
from aws_waste_hunter.regions import validate_region

HOURS_PER_MONTH = 730.0
CACHE_TTL_SECONDS = 24 * 3600
PRICING_API_REGION = "us-east-1"  # the Price List API is only served from a few regions
_MAX_PAGES = 5
_SANITY_LOW, _SANITY_HIGH = 0.25, 4.0  # accepted ratio vs the offline reference price

# $/GB-month by EBS volume type (us-east-1 list price) - also the fallback table.
OFFLINE_EBS_GB_MONTH: dict[str, float] = {
    "gp2": 0.10,
    "gp3": 0.08,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
    "standard": 0.05,
}
OFFLINE_EIP_IDLE_HOURLY = 0.005
OFFLINE_LOGS_GB_MONTH = 0.03
OFFLINE_SOURCE = "offline-us-east-1-list-price"


class PricingError(RuntimeError):
    pass


@dataclass(frozen=True)
class PriceBook:
    source: str = OFFLINE_SOURCE
    ebs: dict[str, float] = field(default_factory=lambda: dict(OFFLINE_EBS_GB_MONTH))
    eip_idle_hourly: float = OFFLINE_EIP_IDLE_HOURLY
    logs_storage_gb_month: float = OFFLINE_LOGS_GB_MONTH

    def ebs_gb_month(self, volume_type: str) -> float:
        return self.ebs.get(volume_type, self.ebs["gp2"])

    @property
    def eip_idle_monthly(self) -> float:
        return round(self.eip_idle_hourly * HOURS_PER_MONTH, 2)


def _sane(value: Any, reference: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and reference * _SANITY_LOW <= value <= reference * _SANITY_HIGH
    )


def _usd(price_json: str) -> float:
    data = json.loads(price_json)
    for term in data["terms"]["OnDemand"].values():
        for dim in term["priceDimensions"].values():
            return float(dim["pricePerUnit"]["USD"])
    raise PricingError("no on-demand price dimension")


def _products(pricing: Any, service: str, filters: dict[str, str]) -> list[dict[str, Any]]:
    flt = [{"Type": "TERM_MATCH", "Field": k, "Value": v} for k, v in filters.items()]
    out: list[dict[str, Any]] = []
    pages = pricing.get_paginator("get_products").paginate(ServiceCode=service, Filters=flt)
    for i, page in enumerate(pages):
        if i >= _MAX_PAGES:
            break
        out.extend(json.loads(item) for item in page["PriceList"])
    return out


def _pick(products: list[dict[str, Any]], usagetype_suffix: str | None = None) -> float | None:
    for prod in products:
        usage = prod.get("product", {}).get("attributes", {}).get("usagetype", "")
        if usagetype_suffix and not usage.endswith(usagetype_suffix):
            continue
        try:
            price = _usd(json.dumps(prod))
        except (KeyError, ValueError, PricingError):
            continue
        if price > 0:
            return price
    return None


def fetch_live(pricing: Any, region: str) -> PriceBook:
    """Build a PriceBook from the Price List API; raise PricingError if nothing usable."""
    validate_region(region)
    fallbacks: list[str] = []
    ebs = dict(OFFLINE_EBS_GB_MONTH)
    for vtype, ref in OFFLINE_EBS_GB_MONTH.items():
        prods = _products(
            pricing,
            "AmazonEC2",
            {"productFamily": "Storage", "regionCode": region, "volumeApiName": vtype},
        )
        price = _pick(prods)
        if price is not None and _sane(price, ref):
            ebs[vtype] = price
        else:
            fallbacks.append(f"ebs-{vtype}")
    eip = _pick(
        _products(pricing, "AmazonEC2", {"productFamily": "IP Address", "regionCode": region}),
        "ElasticIP:IdleAddress",
    )
    if eip is None or not _sane(eip, OFFLINE_EIP_IDLE_HOURLY):
        eip = OFFLINE_EIP_IDLE_HOURLY
        fallbacks.append("eip-idle")
    logs = _pick(
        _products(
            pricing, "AmazonCloudWatch", {"productFamily": "Storage Snapshot", "regionCode": region}
        ),
        "TimedStorage-ByteHrs",
    )
    if logs is None or not _sane(logs, OFFLINE_LOGS_GB_MONTH):
        logs = OFFLINE_LOGS_GB_MONTH
        fallbacks.append("logs-storage")
    if len(fallbacks) == len(OFFLINE_EBS_GB_MONTH) + 2:
        raise PricingError("Price List API returned no usable prices")
    source = "live-price-list-api"
    if fallbacks:
        source += f" (offline fallback for: {', '.join(fallbacks)})"
    return PriceBook(source=source, ebs=ebs, eip_idle_hourly=eip, logs_storage_gb_month=logs)


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "aws-waste-hunter"


def _cache_path(cache_dir: Path, region: str) -> Path:
    return cache_dir / f"prices-{validate_region(region)}.json"


def _load_cache(path: Path, now: float, ttl: float) -> PriceBook | None:
    try:
        data = json.loads(path.read_text())
        if now - float(data["fetched_at"]) > ttl:
            return None
        ebs = data["ebs"]
        book = PriceBook(
            source=str(data["source"]) + " [cached]",
            ebs={k: float(ebs[k]) for k in OFFLINE_EBS_GB_MONTH},
            eip_idle_hourly=float(data["eip_idle_hourly"]),
            logs_storage_gb_month=float(data["logs_storage_gb_month"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None
    ok = all(_sane(book.ebs[k], ref) for k, ref in OFFLINE_EBS_GB_MONTH.items())
    ok = ok and _sane(book.eip_idle_hourly, OFFLINE_EIP_IDLE_HOURLY)
    ok = ok and _sane(book.logs_storage_gb_month, OFFLINE_LOGS_GB_MONTH)
    return book if ok else None


def _save_cache(path: Path, book: PriceBook, now: float) -> None:
    payload = json.dumps(
        {
            "fetched_at": now,
            "source": book.source,
            "ebs": book.ebs,
            "eip_idle_hourly": book.eip_idle_hourly,
            "logs_storage_gb_month": book.logs_storage_gb_month,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(payload)
    os.chmod(path, 0o600)


def load_prices(
    session: Any,
    region: str,
    mode: str = "live",
    cache_dir: Path | None = None,
    now: Callable[[], float] = time.time,
    pricing_client: Any = None,
) -> PriceBook:
    """Return prices for a region. Never raises for pricing problems: falls back offline."""
    if mode == "offline":
        return PriceBook()
    path = _cache_path(cache_dir or default_cache_dir(), region)
    cached = _load_cache(path, now(), CACHE_TTL_SECONDS)
    if cached is not None:
        return cached
    try:
        pricing = pricing_client or client(session, "pricing", PRICING_API_REGION)
        book = fetch_live(pricing, region)
    except Exception as exc:  # noqa: BLE001 - any failure must degrade to the offline table
        reason = type(exc).__name__
        return PriceBook(source=f"{OFFLINE_SOURCE} (live pricing unavailable: {reason})")
    try:
        _save_cache(path, book, now())
    except OSError:
        pass  # caching is best effort
    return book
