import Badlands
import os
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = discord.Object(id=1486148994403930274)


class BadlandsBot(discord.Client):

    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=GUILD)
        await self.tree.sync(guild=GUILD)

        self.add_view(Badlands.ItemMarketView())


bot = BadlandsBot()


@bot.tree.command(
    name="createitempost",
    description="Create the item market listing post."
)
async def create_item_post(interaction: discord.Interaction):

    forumItemMarket = bot.get_channel(1550648832784736366)

    await forumItemMarket.create_thread(
        name="𝕃𝕚𝕤𝕥 𝕒𝕟 𝕀𝕥𝕖𝕞",
        embed=Badlands.embedItemMarketListing,
        view=Badlands.ItemMarketView()
    )

    await interaction.response.send_message(
        "Item market post created!",
        ephemeral=True
    )


bot.run(TOKEN)