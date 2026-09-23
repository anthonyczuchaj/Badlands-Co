import Badlands
import os
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

class BadlandsBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=1486148994403930274)
        await self.tree.sync(guild=guild)
        print("Commands synced!")

bot = BadlandsBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="createitempost",description="Meant to be used only by admins to create the item market listing post!")
async def create_item_post(interaction: discord.Interaction):
    forumItemMarket = bot.get_channel(1550648832784736366)
    if forumItemMarket:
        await forumItemMarket.create_thread(
            name="==-->List an Item<--==", 
            embed=Badlands.embedItemMarketListing
            )

bot.run(TOKEN)
