""" Twitter Bot to play Colossal Cave Adventure! """

import logging
import os
import re
import sqlite3
import sys
import time
from io import BytesIO
from typing import List

import adventure
import tweepy
from adventure.game import Game

logging.getLogger().setLevel(logging.INFO)

# where to store the bot data (sqlite database)
DATABASE_NAME = "advent.sqlite"

# how many results to fetch at once
TWITTER_MAX_RESULTS = 20

TWITTER_MAX_TWEET_LEN = 280

# ID of the last tweet seen -- only used for testing, once operational, this is stored in the database
START_TWEET_ID = 1389744120311160838

# How long (in seconds) to sleep between handling mentions, don't exceed 180 / 15 calls per minute to stay within twitter API application rate limits
TIME_TO_SLEEP = 10

def split_tweet(text: str, max_length=None, auto_number=False) -> List[str]:
    """ split long tweet into series of shorter tweets; will raise ValueError if 
        any word in tweet is longer than max_length """

    if not max_length:
        max_length = TWITTER_MAX_TWEET_LEN

    if len(text) <= max_length:
        return [text]

    if auto_number:
        # adjust for ' xx/yy' numbering
        max_length = max_length - 6

    words = re.findall(r"(\w+\W?[^\w]*)", text)
    if any(len(w) > max_length for w in words):
        raise ValueError(f"tweet contains a word that exceeds max length")

    tweets = []
    tweet = ""
    for word in words:
        if len(tweet + word) < max_length:
            tweet += word
        else:
            tweets.append(tweet)
            tweet = word
    if tweet:
        tweets.append(tweet)

    if auto_number:
        num_tweets = len(tweets)
        for x in range(num_tweets):
            tweets[x] = f"{x+1}/{num_tweets} {tweets[x]}"

    return tweets


class AdventureSaveError(Exception):
    pass


class AdventureDatabaseNotOpen(Exception):
    pass


class TwitterAuthenticationError(Exception):
    pass


class AdventureGame:
    """ Play Adventure, encapsulates the adventure.game.Game object """

    def __init__(self, save_data=None):
        self.result = ""
        self.load_game(save_data) if save_data else self.new_game()

    def new_game(self):
        self.game = Game()
        adventure.load_advent_dat(self.game)
        self.game.start()
        self.do_command(["no"])
        return self.game

    def load_game(self, save_data):
        self.game = Game.resume(save_data)
        self.result = ""

    def do_command(self, words: List[str]) -> str:
        self.result = self.game.do_command(words).strip()
        return self.result

    def do_command_str(self, command_str: str) -> str:
        # TODO: strip out hash tags
        command = command_str.lower().strip()
        commands = command.split()
        return self.do_command(commands)

    def save_game(self) -> memoryview:
        save_data = BytesIO()
        result = self.game.do_command(["save", save_data])
        if not result.startswith("GAME SAVED"):
            raise AdventureSaveError(f"Error saving game")
        return save_data.getbuffer()


class AdventureDB:
    """ Store game data in sqlite database """

    def __init__(self, dbname):
        self.database_name = dbname
        self.open_database()

    def open_database(self):
        logging.info(f"Opening database {self.database_name}")
        self.db = sqlite3.connect(self.database_name)
        self._create_tables()

    def close(self):
        self.db.close()

    def save_game(self, game, tweet_ids, reply_id, text, screen_name=None):
        c = self.db.cursor()
        save_data = game.save_game()
        screen_name = screen_name or ""
        c.execute(
            """
            INSERT INTO game_data(save_data) VALUES (?);
            """,
            (save_data,),
        )
        game_id = c.lastrowid

        # can have more than one tweet per game as long tweets are split
        records = [
            (tweet_id, reply_id, screen_name, text, game_id) for tweet_id in tweet_ids
        ]
        for record in records:
            c.execute(
                """
                INSERT INTO games(tweet_id, in_reply_to_id, screen_name, text, game_id) VALUES(?, ?, ?, ?, ?);
                """,
                record,
            )
        self.db.commit()

        logging.info(f"Saved game: {tweet_ids}, {text}")

    def load_game(self, tweet_id):
        c = self.db.cursor()
        c.execute(
            """
            SELECT game_data.save_data 
            FROM game_data 
            JOIN games ON games.game_id = game_data.id
            WHERE games.tweet_id = ?
            """,
            (tweet_id,),
        )

        results = c.fetchone()

        if not results:
            return None

        save_data = BytesIO(results[0])
        game = AdventureGame(save_data)
        logging.info(game)
        return game

    def have_replied(self, tweet_id):
        if not self.db:
            raise AdventureDatabaseNotOpen("database doesn't appear to be open")

        c = self.db.cursor()
        c.execute("SELECT * FROM games WHERE in_reply_to_id = ?", (tweet_id,))
        result = c.fetchone()
        return bool(result)

    def load_state(self):
        if not self.db:
            raise AdventureDatabaseNotOpen("database doesn't appear to be open")

        logging.info(f"Loading state")
        c = self.db.cursor()
        c.execute("SELECT * from state ORDER BY rowid DESC LIMIT 1;")
        result = c.fetchone()
        if not result:
            return None

        colnames = c.description
        state = {k[0]: v for k, v in zip(colnames, result)}
        # state["last_seen_mention_id"] = int(state["last_seen_mention_id"])
        logging.info(f"Loaded state {state}")
        return state

    def save_state(self, state):
        if not self.db:
            raise AdventureDatabaseNotOpen("database doesn't appear to be open")

        logging.info(f"Saving state: {state}")
        c = self.db.cursor()
        c.execute(
            "INSERT INTO state(last_seen_mention_id, date) VALUES(?, ?);",
            (state["last_seen_mention_id"], time.time()),
        )
        self.db.commit()

    def _create_tables(self):
        if not self.db:
            raise AdventureDatabaseNotOpen("database doesn't appear to be open")

        logging.info("Creating tables")
        sql_commands = [
            """
            CREATE TABLE IF NOT EXISTS games (
                tweet_id INTEGER NOT NULL,
                in_reply_to_id INTEGER,
                screen_name TEXT,
                text TEXT NOT NULL,
                game_id INTEGER NOT NULL
            );""",
            """
            CREATE TABLE IF NOT EXISTS game_data (
                id INTEGER PRIMARY KEY,
                save_data BLOB NOT NULL
            );""",
            """
            CREATE TABLE IF NOT EXISTS state (
                last_seen_mention_id INTEGER NOT NULL,
                date REAL NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS 
                idx_tweet_id on games (tweet_id); 
            """,
            """
            CREATE INDEX IF NOT EXISTS 
                idx_reply_id on games (in_reply_to_id); 
            """,
        ]

        c = self.db.cursor()
        for command in sql_commands:
            c.execute(command)
        self.db.commit()

    def __del__(self):
        if self.db:
            self.db.close()


class AdventureBot:
    def __init__(self):
        logging.info(f"AdventureBot init")

        self._api_key = os.environ["COLOSSAL_CAVE_API_KEY"]
        self._api_secret = os.environ["COLOSSAL_CAVE_API_SECRET"]
        self._access_token = os.environ["COLOSSAL_CAVE_ACCESS_TOKEN"]
        self._access_secret = os.environ["COLOSSAL_CAVE_ACCESS_TOKEN_SECRET"]

        # get twitter API instance
        auth = tweepy.OAuthHandler(self._api_key, self._api_secret)
        auth.set_access_token(self._access_token, self._access_secret)
        self._api = tweepy.API(auth, wait_on_rate_limit=True)

        self.max_results = TWITTER_MAX_RESULTS

        try:
            self._api.verify_credentials()
            logging.info("Twitter authentication OK")
        except:
            raise TwitterAuthenticationError("Error during twitter authentication")

        self.db = AdventureDB(DATABASE_NAME)
        self.state = self.db.load_state()
        logging.info(f"self.state after loading {self.state}")
        self.state = self.state or {
            "last_seen_mention_id": START_TWEET_ID,
            "date": time.time(),
        }

    def handle_mentions(self):
        logging.info(f"Retrieving mentions")
        since_id = self.state["last_seen_mention_id"]
        logging.info(f"since_id: {since_id}")
        for tweet in tweepy.Cursor(
            self._api.search,
            q=f"@{self._api.me().screen_name} -filter:retweets",
            tweet_mode="extended",
            since_id=since_id,
            count=self.max_results,
        ).items():
            logging.info(
                f"tweet.id={tweet.id}, {since_id > tweet.id} {since_id - tweet.id}"
            )
            since_id = max(tweet.id, since_id)
            self.state["last_seen_mention_id"] = since_id
            logging.info(f"since_id: {since_id}")

            if self.db.have_replied(tweet.id):
                logging.info(f"Have already replied to tweet {tweet.id}")
                continue

            if tweet.display_text_range:
                start, stop = tweet.display_text_range
                text = tweet.full_text[start:stop]
                logging.info(f"start = {start}")
            else:
                text = tweet.full_text

            game = None
            if tweet.in_reply_to_status_id is not None:
                logging.info(
                    f"in_reply_to_status_id: {tweet.in_reply_to_status_id}, id: {tweet.id}, user: {tweet.user.screen_name}"
                )
                logging.info(f"full_text: {tweet.full_text}, {text}")
                game = self.db.load_game(tweet.in_reply_to_status_id)
            if game:
                logging.info(f"Loaded game from database, playing move")
                self.play_move(tweet, text, game)
            else:
                # not a reply or didn't find game
                logging.info(f"New game with {tweet.user.screen_name}")
                self.new_game(tweet.id, screen_name=tweet.user.screen_name)

        logging.info(f"since_id: {since_id}")
        self.db.save_state(self.state)
        return since_id

    def play_move(self, tweet, command, game):
        result = game.do_command_str(command)
        logging.info(f"play_move result = '{result}'")
        tweets_to_send = split_tweet(result, auto_number=True)
        status_ids = []
        for status in tweets_to_send:
            reply_tweet = self._api.update_status(
                status=status,
                in_reply_to_status_id=tweet.id,
                auto_populate_reply_metadata=True,
            )
            status_ids.append(reply_tweet.id)
        self.db.save_game(
            game, status_ids, tweet.id, result, screen_name=tweet.user.screen_name
        )

    def new_game(self, reply_id=None, screen_name=None):
        game = AdventureGame()
        result = game.result
        logging.info(f"result='{result}'")
        tweet = None
        if reply_id:
            logging.info(f"Responding to id {reply_id}")
            try:
                tweet = self._api.update_status(
                    status=result,
                    in_reply_to_status_id=reply_id,
                    auto_populate_reply_metadata=True,
                )
            except tweepy.error.TweepError as e:
                logging.info(f"tweepy error: {e}")
        else:
            try:
                tweet = self._api.update_status(status=result)
            except tweepy.error.TweepError as e:
                logging.info(f"tweepy error: {e}")
        if tweet:
            self.db.save_game(
                game, [tweet.id], reply_id or 0, result, screen_name=screen_name
            )

    def run(self):
        while True:
            self.handle_mentions()
            limits = self._api.rate_limit_status()
            logging.info(limits["resources"]["application"])
            logging.info(f"Sleeping for {TIME_TO_SLEEP} seconds")
            time.sleep(TIME_TO_SLEEP)

    def __del__(self):
        if self.db:
            self.db.save_state(self.state)
            logging.info(f"Closing database {self.db}")
            self.db.close()


if __name__ == "__main__":
    bot = AdventureBot()
    bot.run()
