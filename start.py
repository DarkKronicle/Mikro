import asyncio

import bot as bot_global
from bot.util import config
from bot.mikro import Mikro
import pathlib


def run_bot():
    bot_global.config = config.Config(pathlib.Path('config.toml'))
    bot = Mikro()
    bot.run()


if __name__ == '__main__':
    run_bot()
