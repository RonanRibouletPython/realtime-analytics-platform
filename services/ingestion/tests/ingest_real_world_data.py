import asyncio
from datetime import datetime as dt
from datetime import timezone as tz
from typing import Dict, List

import structlog

logger = structlog.get_logger()

import httpx


class RealDataIngester:
    """Fetch and ingest data from public APIs"""

    def __init__(
        self,
        api_url: str = "http://localhost:8000/api/v1/metrics",
    ):
        self.api_url = api_url
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def send_metric(self, metric: dict) -> bool:
        """Send metric to our API"""
        try:
            response = await self.client.post(self.api_url, json=metric)
            return response.status_code == 201
        except Exception as e:
            logger.info(f"Error sending metric: {e}")
            return False

    async def fetch_crypto_prices(self) -> List[dict]:
        """
        Fetch real-time cryptocurrency prices from CoinGecko
        """
        logger.info("Fetching cryptocurrency prices...")

        try:
            response = await self.client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin,ethereum,cardano,solana,polkadot",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                },
            )

            if response.status_code != 200:
                logger.info(f"CoinGecko API error: {response.status_code}")
                return []

            data = response.json()
            metrics = []

            for coin, values in data.items():
                # Price metric
                metrics.append(
                    {
                        "name": "crypto_price_usd",
                        "value": values["usd"],
                        "labels": {
                            "coin": coin,
                            "currency": "usd",
                            "source": "coingecko",
                        },
                    }
                )

                # 24h change metric
                if "usd_24h_change" in values:
                    metrics.append(
                        {
                            "name": "crypto_price_change_24h",
                            "value": values["usd_24h_change"],
                            "labels": {"coin": coin, "source": "coingecko"},
                        }
                    )

                # Market cap metric
                if "usd_market_cap" in values:
                    metrics.append(
                        {
                            "name": "crypto_market_cap_usd",
                            "value": values["usd_market_cap"],
                            "labels": {"coin": coin, "source": "coingecko"},
                        }
                    )

            logger.info(f"Fetched {len(metrics)} crypto metrics")
            return metrics

        except Exception as e:
            logger.info(f"Error fetching crypto data: {e}")
            return []

    async def ingest_all_sources(self):
        """Fetch and ingest data from crypto source"""
        logger.info("\n" + "=" * 60)
        logger.info("FETCHING REAL-WORLD DATA FROM PUBLIC API")
        logger.info("=" * 60 + "\n")

        all_metrics = []

        # Fetch from crypto source
        all_metrics.extend(await self.fetch_crypto_prices())
        await asyncio.sleep(1)

        # Send all metrics to our API
        logger.info(f"\nSending {len(all_metrics)} metrics to our API...")

        successful = 0
        for i, metric in enumerate(all_metrics):
            if await self.send_metric(metric):
                successful += 1

            if (i + 1) % 10 == 0:
                logger.info(f"  Progress: {i + 1}/{len(all_metrics)}")

        logger.info(f"\nSuccessfully ingested {successful}/{len(all_metrics)} metrics!")

        return successful


async def continuous_monitoring(interval_seconds: int = 60, duration_minutes: int = 10):
    """
    Continuously fetch and ingest real data at regular intervals.

    Args:
        interval_seconds: How often to fetch data
        duration_minutes: How long to run
    """
    logger.info("Starting continuous monitoring...")
    logger.info(f"Interval: {interval_seconds}s")
    logger.info(f"Duration: {duration_minutes} minutes\n")

    iterations = (duration_minutes * 60) // interval_seconds

    for i in range(iterations):
        logger.info(f"\n--- Iteration {i + 1}/{iterations} ---")

        async with RealDataIngester() as ingester:
            await ingester.ingest_all_sources()

        if i < iterations - 1:
            logger.info(f"\nWaiting {interval_seconds}s before next fetch...")
            await asyncio.sleep(interval_seconds)

    logger.info("\n Continuous monitoring complete!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "continuous":
        # Continuous mode: fetch every 60 seconds for 10 minutes
        asyncio.run(continuous_monitoring(interval_seconds=60, duration_minutes=10))
    else:
        # Single fetch mode
        async def main():
            async with RealDataIngester() as ingester:
                await ingester.ingest_all_sources()

        asyncio.run(main())
