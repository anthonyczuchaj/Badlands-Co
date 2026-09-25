import ItemMarket
import LandMarket
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

        self.add_view(ItemMarket.ItemMarketView())
        self.add_view(LandMarket.LandMarketView())

        restored = await ItemMarket.restore_marketplace_views(self)

        print(f"Restored {restored} marketplace views.")


bot = BadlandsBot()


@bot.tree.command(
    name="createitempost",
    description="Create the item market listing post."
)
async def create_item_post(interaction: discord.Interaction):

    forumItemMarket = bot.get_channel(
        1550648832784736366
    )

    await forumItemMarket.create_thread(
        name="𝕃𝕚𝕤𝕥 𝕒𝕟 𝕀𝕥𝕖𝕞",
        embed=ItemMarket.embedItemMarketListing,
        view=ItemMarket.ItemMarketView()
    )

    await interaction.response.send_message(
        "Item market post created!",
        ephemeral=True
    )


@bot.tree.command(
    name="createlandpost",
    description="Create the land auction marketplace post."
)
async def create_land_post(interaction: discord.Interaction):

    forum = bot.get_channel(
        LandMarket.LAND_MARKET_FORUM_ID
    )

    if forum is None or not isinstance(
        forum,
        discord.ForumChannel
    ):
        await interaction.response.send_message(
            "❌ The land market forum could not be found.",
            ephemeral=True
        )
        return

    await forum.create_thread(
        name="𝕃𝕚𝕤𝕥 𝕒 𝕃𝕒𝕟𝕕",
        embed=LandMarket.embedLandMarketListing,
        view=LandMarket.LandMarketView()
    )

    await interaction.response.send_message(
        "🏞️ Land marketplace post created!",
        ephemeral=True
    )


bot.run(TOKEN)