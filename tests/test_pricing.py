from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from aws_waste_hunter import pricing
from aws_waste_hunter.pricing import PriceBook, fetch_live, load_prices
from aws_waste_hunter.regions import parse_region_list, validate_region


def _product(usagetype: str, usd: float) -> str:
    return json.dumps(
        {
            "product": {"attributes": {"usagetype": usagetype}},
            "terms": {
                "OnDemand": {"t": {"priceDimensions": {"d": {"pricePerUnit": {"USD": str(usd)}}}}}
            },
        }
    )


class FakePricing:
    """Mimics pricing.get_paginator('get_products') with canned responses."""

    def __init__(
        self,
        ebs: dict[str, float] | None = None,
        eip: float | None = 0.005,
        logs: float | None = 0.03,
        boom: Exception | None = None,
    ) -> None:
        self.ebs = {"gp2": 0.11, "gp3": 0.088, **(ebs or {})}
        self.eip, self.logs, self.boom = eip, logs, boom
        self.calls = 0

    def get_paginator(self, name: str) -> FakePricing:
        assert name == "get_products"
        return self

    def paginate(self, ServiceCode: str, Filters: list[dict[str, str]]) -> list[dict[str, Any]]:  # noqa: N803
        self.calls += 1
        if self.boom:
            raise self.boom
        f = {x["Field"]: x["Value"] for x in Filters}
        if "volumeApiName" in f:
            usd = self.ebs.get(f["volumeApiName"])
            return [{"PriceList": [_product("EBS:VolumeUsage", usd)] if usd else []}]
        if f.get("productFamily") == "IP Address":
            items = [_product("DataTransfer", 9.9)]
            if self.eip:
                items.append(_product("EUW1-ElasticIP:IdleAddress", self.eip))
            return [{"PriceList": items}]
        items = [] if self.logs is None else [_product("TimedStorage-ByteHrs", self.logs)]
        return [{"PriceList": items}]


def test_live_prices_override_offline_and_report_fallbacks() -> None:
    book = fetch_live(FakePricing(), "eu-west-1")
    assert book.ebs["gp2"] == 0.11 and book.ebs["gp3"] == 0.088
    assert book.eip_idle_hourly == 0.005
    assert "offline fallback for" in book.source and "ebs-io1" in book.source


def test_all_missing_raises() -> None:
    empty = FakePricing(ebs={}, eip=None, logs=None)
    empty.ebs = {}
    with pytest.raises(pricing.PricingError):
        fetch_live(empty, "eu-west-1")


def test_insane_live_price_is_rejected() -> None:
    book = fetch_live(FakePricing(ebs={"gp2": 50.0}), "eu-west-1")  # 500x the reference
    assert book.ebs["gp2"] == pricing.OFFLINE_EBS_GB_MONTH["gp2"]
    assert "ebs-gp2" in book.source


def test_failure_falls_back_offline_without_raising(tmp_path: Path) -> None:
    book = load_prices(
        None,
        "us-east-1",
        cache_dir=tmp_path,
        pricing_client=FakePricing(boom=RuntimeError("AccessDenied")),
    )
    assert book.ebs == PriceBook().ebs
    assert "live pricing unavailable: RuntimeError" in book.source
    assert not list(tmp_path.iterdir())  # failures are never cached


def test_cache_hit_expiry_and_permissions(tmp_path: Path) -> None:
    fake = FakePricing()
    t0 = 1_000_000.0
    first = load_prices(None, "eu-west-1", cache_dir=tmp_path, pricing_client=fake, now=lambda: t0)
    calls = fake.calls
    second = load_prices(
        None, "eu-west-1", cache_dir=tmp_path, pricing_client=fake, now=lambda: t0 + 60
    )
    assert fake.calls == calls and second.source.endswith("[cached]")
    assert second.ebs == first.ebs
    path = tmp_path / "prices-eu-west-1.json"
    assert (path.stat().st_mode & 0o777) == 0o600
    load_prices(
        None,
        "eu-west-1",
        cache_dir=tmp_path,
        pricing_client=fake,
        now=lambda: t0 + pricing.CACHE_TTL_SECONDS + 1,
    )
    assert fake.calls > calls  # expired -> refetched


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d: d["ebs"].update(gp2=-1),
        lambda d: d["ebs"].update(gp2=9999),
        lambda d: d.update(eip_idle_hourly="free"),
        lambda d: d.pop("ebs"),
    ],
)
def test_tampered_cache_is_ignored(tmp_path: Path, tamper: Any) -> None:
    fake = FakePricing()
    load_prices(None, "us-east-1", cache_dir=tmp_path, pricing_client=fake)
    path = tmp_path / "prices-us-east-1.json"
    data = json.loads(path.read_text())
    tamper(data)
    path.write_text(json.dumps(data))
    before = fake.calls
    book = load_prices(None, "us-east-1", cache_dir=tmp_path, pricing_client=fake)
    assert fake.calls > before and not book.source.endswith("[cached]")


def test_offline_mode_makes_no_calls(tmp_path: Path) -> None:
    fake = FakePricing()
    assert (
        load_prices(
            None, "us-east-1", mode="offline", cache_dir=tmp_path, pricing_client=fake
        ).source
        == pricing.OFFLINE_SOURCE
    )
    assert fake.calls == 0


def test_cache_path_cannot_escape_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_prices(None, "../../etc/passwd", cache_dir=tmp_path, pricing_client=FakePricing())


def test_region_validation() -> None:
    assert validate_region("ap-southeast-2") == "ap-southeast-2"
    assert parse_region_list(" us-east-1, eu-west-1 ,us-east-1") == ["us-east-1", "eu-west-1"]
    for bad in ["", "us east 1", "us-east-1\n", "a.b-c-1", "us-east-"]:
        with pytest.raises(ValueError):
            validate_region(bad)
    with pytest.raises(ValueError):
        parse_region_list(" , ")
    assert os.sep not in "us-east-1" and time.time() > 0
