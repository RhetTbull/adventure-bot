# Adventure Bot

Twitter bot that plays Colossal Cave Adventure.  @ mention the bot and it will start a new game of Adventure with you that's playable through tweets.

## Background

This was inspired by listening to an interview with [Brandon Rhodes](https://twitter.com/brandon_rhodes) on [Test and Code](https://testandcode.com/151) podcast.  Brandon ported the classic Colossal Cave Adventure to [python](https://github.com/brandon-rhodes/python-adventure) which made it fairly easy to implement this as a bot.

## Installation

- `git clone ` this repo
- `python3 -m pip install -r requirements.txt`
- Set up a [twitter developer account](https://developer.twitter.com/en/apply-for-access)
- Generate twitter API keys for your new bot (left as an exercise for the reader)
- export the API keys as environment variables (see `set_env.sh` in this repo for the environment variable names)
- `python3 advent_bot.py`

Alternatively, you can use Docker.  See `Dockerfile`, `docker_build.sh`, and `docker_run.sh` in this repo.

To get this running on [Oracle Cloud](https://www.oracle.com/cloud/sign-in.html?redirect_uri=https%3A%2F%2Fcloud.oracle.com%2F), I did the following:

- Follow instructions [here](https://oracle-base.com/articles/linux/docker-install-docker-on-oracle-linux-ol8) to install Docker
- Follow instructions [here](https://oracle-base.com/articles/linux/docker-host-file-system-permissions-for-container-persistent-host-volumes) to set permissions correctly for persistent storage


## Warnings

This is a toy project not meant for production.  It's easy to get your account locked by twitter for exceeding API rate limits, etc.  I've made attempts to in the code to avoid this but use at your own risk.  It's also my first time using Docker so there's a good chance the entire configuration is completely insecure and will lead to your server being pwned and you being killed by a dwarf.  You have been warned. 
