# Adventure Bot

Twitter bot that plays Colossal Cave Adventure.  @ mention [the bot](https://twitter.com/Colossal_Cave) and it will start a new game of Adventure with you that's playable through tweets.

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

## Implementation

This bot uses [tweepy](https://github.com/tweepy/tweepy) to interface with the Twitter API.  It periodically checks Twitter mentions and when it receives one, the code checks a database of saved games (implemented in sqlite) to see if it has a saved game associted with the "in reply to" tweet ID.  If so, it loads that game and plays the move from the tweet body.  If it doesn't find a matching tweet ID, it creates a new game and saves it to the database associated with the tweet ID.  Effectively, this means every tweet is it's own branch in the game.  If you fall into a pit or get killed by a dwarf, you can go back to a previous tweet and reply to "fork" the game.  It also means other users can fork your game which opens the possibility for shared play.  The code uses the save/resume feature built into `python-adventure` to save the game to a `ByteIO` object which is stored in the database.  `python-adventure` implements save/resume using zlib-compressed pickle and every saved game is ~35KB in size.  This isn't super efficient but given I expect no more than one or two people using the bot at any time and storage is cheap, it's "good enough".

## Warnings

This is a toy project not meant for production.  It's easy to get your account locked by twitter for exceeding API rate limits, etc.  I've made attempts to in the code to avoid this but use at your own risk.  It's also my first time using Docker so there's a good chance the entire configuration is completely insecure and will lead to your server being pwned and you being killed by a dwarf.  You have been warned. 
