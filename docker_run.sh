docker run --name adventure-bot -v /Users/Shared:/shared --restart on-failure --log-opt mode=non-blocking --log-opt max-buffer-size=1m -dt advent_bot

