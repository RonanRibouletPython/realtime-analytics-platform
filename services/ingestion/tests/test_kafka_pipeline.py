import asyncio

import httpx


async def test_pipeline():
    """Send metrics and verify they're processed."""
    client = httpx.AsyncClient()

    print("Testing Kafka Pipeline...")
    print("-" * 60)

    # 1. Send metrics
    print("\nSending 10 test metrics...")
    for i in range(10):
        response = await client.post(
            "http://localhost:8000/api/v1/metrics",
            json={
                "name": f"test_metric_{i}",
                "value": float(i * 10),
                "labels": {"test": "pipeline", "batch": "1"},
            },
        )
        assert response.status_code == 202
        print(f"    Metric {i + 1} queued")

    # 2. Wait for processing
    print("\n   Waiting 5 seconds for consumer to process...")
    await asyncio.sleep(5)

    # 3. Verify in database
    print("\n   Checking database...")
    response = await client.get("http://localhost:8000/api/v1/metrics?limit=10")
    metrics = response.json()

    test_metrics = [m for m in metrics if m["labels"].get("test") == "pipeline"]

    print(f"  Found {len(test_metrics)} test metrics in database")

    if len(test_metrics) == 10:
        print("\n   Pipeline test PASSED!")
    else:
        print(f"\n  Pipeline test FAILED! Expected 10, got {len(test_metrics)}")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(test_pipeline())
