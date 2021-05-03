import logging
import os
import sqlite3
import sys
from io import BytesIO

import adventure
import tweepy
from adventure import load_advent_dat
from adventure.game import Game

logging.getLogger().setLevel(logging.INFO)

DATABASE_NAME = "advent.sqlite"
TWITTER_MAX_RESULTS = 10


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

        self.database_name = DATABASE_NAME
        self.state = {"mention_id": 1389032149605486594}

        self.max_results = TWITTER_MAX_RESULTS

        try:
            self._api.verify_credentials()
            logging.info("Twitter authentication OK")
        except:
            raise ValueError("Error during twitter authentication")

        self.open_database()

    def get_mentions(self):
        logging.info(f"Retrieving mentions")
        since_id = self.state["mention_id"]
        for tweet in tweepy.Cursor(
            self._api.search,
            q=f"@{self._api.me().screen_name} -filter:retweets",
            tweet_mode="extended",
            since_id=since_id,
            count=self.max_results,
        ).items():
            since_id = max(tweet.id, since_id)
            if tweet.display_text_range:
                start, stop = tweet.display_text_range
                text = tweet.full_text[start:stop]
            else:
                text = tweet.full_text

            if tweet.in_reply_to_status_id is not None:
                logging.info(
                    f"in_reply_to_status_id: {tweet.in_reply_to_status_id}, id: {tweet.id}, user: {tweet.user.screen_name}"
                )
                logging.info(f"full_text: {tweet.full_text}, {text}")
            else:
                # not a reply
                logging.info(f"New game with {tweet.user.screen_name}")
                self.new_game(tweet.id, screen_name=tweet.user.screen_name)

        self.state["mention_id"] = since_id
        logging.info(f"since_id: {since_id}")
        return since_id

    def open_database(self):
        logging.info(f"Opening database {self.database_name}")
        self.db = sqlite3.connect(self.database_name)
        self._create_tables()

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
            self.save_game(game, tweet.id, result, screen_name=screen_name)
            # self.save_game(game, id_, result)

    def save_game(self, game, id_, text, screen_name=None):
        c = self.db.cursor()
        save_data = BytesIO()
        result = game.do_command(["save", save_data])
        if not result.startswith("GAME SAVED"):
            raise ValueError(f"Error saving game")

        screen_name = screen_name or ""
        c.execute(
            "INSERT INTO games(tweet_id, screen_name, text, game_data) values (?, ?, ?, ?);",
            (str(id_), screen_name, text, save_data.getbuffer()),
        )
        self.db.commit()
        logging.info(f"Saved game: {id_}, {text}")

    def _create_tables(self):
        if not self.db:
            raise ValueError("database doesn't appear to be open")

        logging.info("Creating tables")
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                tweet_id TEXT NOT NULL,
                screen_name TEXT,
                text TEXT NOT NULL,
                game_data BLOB NOT NULL
            );"""
        )

    def __del__(self):
        if self.db:
            logging.info(f"Closing database {self.db}")
            self.db.close()


if __name__ == "__main__":
    bot = AdventureBot()
    bot.get_mentions()
