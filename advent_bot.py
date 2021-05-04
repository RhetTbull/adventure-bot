""" Twitter Bot to play Colossal Cave Adventure! """

import logging
import os
import sqlite3
import sys
import time
from io import BytesIO

import adventure
import tweepy
from adventure import load_advent_dat
from adventure.game import Game

logging.getLogger().setLevel(logging.INFO)

DATABASE_NAME = "advent.sqlite"
TWITTER_MAX_RESULTS = 20

# TODO: move all game stuff to it's own Game class (that encapsulates an adventure.game.Game object)


class AdventureDB:
    """ Store game data """

    def __init__(self, dbname):
        self.database_name = dbname
        self.open_database()

    def open_database(self):
        logging.info(f"Opening database {self.database_name}")
        self.db = sqlite3.connect(self.database_name)
        self._create_tables()

    def close(self):
        self.db.close()

    def save_game(self, game, tweet_id, reply_id, text, screen_name=None):
        c = self.db.cursor()
        save_data = BytesIO()
        result = game.do_command(["save", save_data])
        if not result.startswith("GAME SAVED"):
            raise ValueError(f"Error saving game")

        screen_name = screen_name or ""
        c.execute(
            "INSERT OR REPLACE INTO games(tweet_id, in_reply_to_id, screen_name, text, game_data) values (?, ?, ?, ?, ?);",
            (str(tweet_id), str(reply_id), screen_name, text, save_data.getbuffer()),
        )
        self.db.commit()
        logging.info(f"Saved game: {tweet_id}, {text}")

    def load_game(self, tweet_id):
        c = self.db.cursor()
        c.execute("SELECT game_data FROM games WHERE tweet_id = ?", (tweet_id,))
        results = c.fetchone()

        if not results:
            return None

        save_data = BytesIO(results[0])
        game = Game.resume(save_data)
        logging.info(game)
        return game

    def have_replied(self, tweet_id):
        if not self.db:
            raise ValueError("database doesn't appear to be open")

        c = self.db.cursor()
        c.execute("SELECT * FROM games WHERE in_reply_to_id = ?", (str(tweet_id),))
        result = c.fetchone()
        return bool(result)

    def load_state(self):
        if not self.db:
            raise ValueError("database doesn't appear to be open")

        logging.info(f"Loading state")
        c = self.db.cursor()
        c.execute("SELECT * from state ORDER BY rowid DESC LIMIT 1;")
        result = c.fetchone()
        if not result:
            return None

        colnames = c.description
        state = {k[0]: v for k, v in zip(colnames, result)}
        state["last_seen_mention_id"] = int(state["last_seen_mention_id"])
        logging.info(f"Loaded state {state}")
        return state

    def save_state(self, state):
        if not self.db:
            raise ValueError("database doesn't appear to be open")

        logging.info(f"Saving state: {state}")
        c = self.db.cursor()
        c.execute(
            "INSERT INTO state(last_seen_mention_id, date) values (?, ?);",
            (str(state["last_seen_mention_id"]), time.time()),
        )
        self.db.commit()

    def _create_tables(self):
        if not self.db:
            raise ValueError("database doesn't appear to be open")

        logging.info("Creating tables")
        sql_commands = [
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                tweet_id TEXT NOT NULL,
                in_reply_to_id TEXT,
                screen_name TEXT,
                text TEXT NOT NULL,
                game_data BLOB NOT NULL
            );""",
            """
            CREATE TABLE IF NOT EXISTS state (
                id INTEGER PRIMARY KEY,
                last_seen_mention_id TEXT NOT NULL,
                date REAL NOT NULL
            );
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS 
                idx_tweet_id on games (tweet_id); 
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS 
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
            raise ValueError("Error during twitter authentication")

        self.db = AdventureDB(DATABASE_NAME)
        self.state = self.db.load_state()
        logging.info(f"self.state after loading {self.state}")
        self.state = self.state or {
            "last_seen_mention_id": 1389208292186988545,
            "date": time.time(),
        }

    def get_mentions(self):
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

            if self.have_replied(tweet.id):
                logging.info(f"Have already replied to tweet {tweet.id}")
                continue

            if tweet.display_text_range:
                start, stop = tweet.display_text_range
                text = tweet.full_text[start:stop]
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

    def play_move(self, tweet, text, game):
        result = self.do_command(text, game)
        logging.info(f"play_move result = '{result}'")
        reply_tweet = self._api.update_status(
            status=result,
            in_reply_to_status_id=tweet.id,
            auto_populate_reply_metadata=True,
        )
        self.db.save_game(
            game, reply_tweet.id, tweet.id, result, screen_name=tweet.user.screen_name
        )

    def do_command(self, text, game):
        command = text.lower().strip()
        commands = command.split()
        result = game.do_command(commands)
        result = result.strip()
        logging.info(f"result of do_command = {result}")
        return result

    def new_game(self, id_=None, screen_name=None):
        game = Game()
        load_advent_dat(game)
        game.start()
        # no instructions
        result = game.do_command(["no"])
        result = result.strip()
        logging.info(f"result='{result}'")
        tweet = None
        if id_:
            logging.info(f"Responding to id {id_}")
            try:
                tweet = self._api.update_status(
                    status=result,
                    in_reply_to_status_id=id_,
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
            self.db.save_game(game, tweet.id, id_ or 0, result, screen_name=screen_name)

    def __del__(self):
        if self.db:
            self.db.save_state(self.state)
            logging.info(f"Closing database {self.db}")
            self.db.close()


if __name__ == "__main__":
    bot = AdventureBot()
    bot.get_mentions()
