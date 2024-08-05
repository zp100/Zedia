import discord
import os
from zedia_bot.ZediaBot import ZediaBot


def main():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = ZediaBot(intents=intents)

    token = os.environ['ZEDIA_TOKEN']
    bot.run(token)


if __name__ == '__main__':
    main()
