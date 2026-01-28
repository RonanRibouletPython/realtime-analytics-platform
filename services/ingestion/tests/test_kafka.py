import asyncio

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer


async def test_kafka_connection():
    # 1. Configuration
    KAFKA_SERVER = "localhost:9092"
    TOPIC = "test-topic"

    print(f"Connecting to Kafka at {KAFKA_SERVER}...")

    # 2. Produce a message
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_SERVER)
    await producer.start()
    try:
        await producer.send_and_wait(TOPIC, b"Hello Kafka from Python!")
        print("Message produced successfully")
    finally:
        await producer.stop()

    # 3. Consume the message
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_SERVER,
        auto_offset_reset="earliest",
        group_id="test-group",
    )
    await consumer.start()
    try:
        msg = await consumer.getone()
        print(f"Message consumed: {msg.value.decode()}")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(test_kafka_connection())
