#!/usr/bin/env python3
"""Short-lived AMQP smoke test; NEVER point at production queues or vhosts."""
from __future__ import annotations

import argparse
import json
import uuid

from kombu import Connection, Exchange, Producer, Queue


def smoke(url: str) -> None:
    queue_name = f"gitmonitor-smoke-{uuid.uuid4().hex}"
    exchange = Exchange(queue_name, type="direct", durable=True, auto_delete=False)
    queue = Queue(queue_name, exchange=exchange, routing_key=queue_name, durable=True, auto_delete=False)

    with Connection(url, heartbeat=0, connect_timeout=8) as connection:
        channel = connection.channel()
        queue.maybe_bind(connection)
        queue.declare()
        producer = Producer(channel, exchange=exchange, routing_key=queue_name, serializer="json")
        expected = [f"job-{n}" for n in range(1, 4)]
        for job_id in expected:
            producer.publish({"job_id": job_id}, declare=[queue], retry=True)
        simple = connection.SimpleQueue(queue)
        try:
            observed = []
            for _ in expected:
                message = simple.get(block=True, timeout=8)
                try:
                    observed.append(message.payload["job_id"])
                finally:
                    message.ack()
            assert observed == expected, (observed, expected)
            # Explicitly demonstrate RabbitMQ requeue on a rejected delivery.
            producer.publish({"job_id": "retry-me"}, declare=[queue], retry=True)
            retried = simple.get(block=True, timeout=8)
            assert retried.payload["job_id"] == "retry-me"
            retried.reject(requeue=True)
            again = simple.get(block=True, timeout=8)
            assert again.payload["job_id"] == "retry-me"
            again.ack()
            assert simple.qsize() == 0, "Messages left after acknowledgements"
            print(json.dumps({"ok": True, "published": 4, "acked": 4, "requeue": 1}))
        finally:
            simple.close()
            queue.delete(if_unused=False, if_empty=False)
            channel.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Disposable RabbitMQ AMQP URL")
    args = parser.parse_args()
    smoke(args.url)


if __name__ == "__main__":
    main()
