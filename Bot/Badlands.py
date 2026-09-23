import discord
embedItemMarketListing = discord.Embed(
    title="List an Item",
    description="Take this oppurtunity to list an item, either for sale, or for auction. Any money you make is yours to keep, and yours to earn!",
    color=discord.Color.gold()
    )
embedItemMarketListing.set_image(url="/IMG/Banner.png")

embedItemSell = discord.Embed(
    title="Sell An Item!",
)
embedItemAuction = ""

class ItemMarketView(discord.ui.View):
    
    @discord.ui.button(label="Sell an Item",style=discord.ButtonStyle.primary)
    async def sell(self,interaction: discord.Interaction, button: discord.ui.button):
        await interaction.response.send_message("Sell an Item Clicked!", ephemeral=True)
    @discord.ui.button(label="Auction an Item",style=discord.ButtonStyle.primary)
    async def auction(self, interaction: discord.Interaction, button:discord.ui.button):
        await interaction.response.send_message("Auction an Item Clicked!", ephemeral=False)
    