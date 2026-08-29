#!/bin/sh
set -e

KAFKA_URL="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
topics="truck-assignment-requested:1 truck-assignment-completed:1"

for topic in $topics; do
  name=${topic%%:*}
  partitions=${topic##*:}

  echo "Creating topic: $name (partitions=$partitions)..."
  kafka-topics --create --topic "$name" --if-not-exists --partitions "$partitions" --replication-factor 1 --bootstrap-server "$KAFKA_URL"
done

echo "All topics created."
