#!/bin/sh

# run adventure-bot in docker

docker run --name adventure-bot \
    --mount type=bind,source="$(pwd)"/shared,target=/shared \
    --env-file .env \
    --restart on-failure \
    --log-opt mode=non-blocking \
    --log-opt max-buffer-size=1m \
    -dt advent_bot