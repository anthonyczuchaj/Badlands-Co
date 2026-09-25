import discord
import re
from datetime import datetime, timedelta, timezone


# The forum channel where completed marketplace posts are created.
ITEM_MARKET_FORUM_ID = 1550648832784736366


def parse_duration(duration):
    match = re.fullmatch(r"(\d+)([mhdw])", duration.lower().strip())

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    units = {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount)
    }

    return datetime.now(timezone.utc) + units[unit]


############################################################
# ITEM MARKET MENU
############################################################

embedItemMarketListing = discord.Embed(
    title="𝕃𝕚𝕤𝕥 𝕒𝕟 𝕀𝕥𝕖𝕞",
    description=(
        "Take this opportunity to list an item, either for sale or for auction. "
        "Any money you make is yours to keep and yours to earn!"
    ),
    color=discord.Color.gold()
)

embedItemMarketListing.add_field(
    name="Auction🔨",
    value=(
        "Put your item up for auction and let other players compete for it.\n\n"
        "**You'll need:**\n"
        "• Item being sold\n"
        "• Starting bid\n"
        "• Auction duration\n"
        "• Quantity\n\n"
        "The bidder with the highest bid at the end of an auction is the winner!"
    ),
    inline=False
)

embedItemMarketListing.add_field(
    name="Sale💰",
    value=(
        "List an item at a fixed price. Other players can purchase it "
        "immediately at the price you set.\n\n"
        "**You'll need:**\n"
        "• Item being sold\n"
        "• Sale price\n"
        "• Quantity"
    ),
    inline=False
)

embedItemMarketListing.set_footer(
    text="Choose an option below to get started."
)

embedItemMarketListing.set_image(
    url="https://raw.githubusercontent.com/anthonyczuchaj/Badlands-Co/refs/heads/main/Bot/IMG/Banner.png"
)


############################################################
# AUCTION MODAL
############################################################

class AuctionModal(discord.ui.Modal, title="Create an Auction"):

    item_name = discord.ui.TextInput(
        label="Item Name",
        placeholder="Example: Diamond Pickaxe",
        required=True,
        min_length=2,
        max_length=100
    )

    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="Example: 1",
        required=True,
        max_length=10
    )

    starting_bid = discord.ui.TextInput(
        label="Starting Bid",
        placeholder="Example: 500",
        required=True,
        max_length=20
    )

    duration = discord.ui.TextInput(
        label="Auction Duration",
        placeholder="Example: 1m, 1h, 1d, 1w",
        required=True,
        max_length=10
    )

    description = discord.ui.TextInput(
        label="Description",
        placeholder="Describe the item...",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):

        item_name = self.item_name.value.strip()
        quantity = self.quantity.value.strip()
        starting_bid = self.starting_bid.value.strip()
        duration = self.duration.value.strip()
        description = self.description.value.strip()

        end_time = parse_duration(duration)

        if end_time is None:
            await interaction.response.send_message(
                "❌ Invalid duration. Use formats like `1m`, `1h`, `1d`, or `1w`.",
                ephemeral=True
            )
            return

        if not quantity.isdigit() or int(quantity) <= 0:
            await interaction.response.send_message(
                "❌ Quantity must be a whole number greater than 0.",
                ephemeral=True
            )
            return

        if not starting_bid.isdigit() or int(starting_bid) <= 0:
            await interaction.response.send_message(
                "❌ Starting bid must be a whole number greater than $0.",
                ephemeral=True
            )
            return

        if not duration:
            await interaction.response.send_message(
                "❌ Please enter an auction duration.",
                ephemeral=True
            )
            return

        auction_data = {
            "item_name": item_name,
            "quantity": int(quantity),
            "starting_bid": int(starting_bid),
            "duration": duration,
            "end_time": end_time,
            "description": description
        }

        view = AuctionConfirmationView(auction_data, interaction.user)

        await interaction.response.send_message(
            embed=createAuctionEmbed(auction_data, interaction.user),
            view=view,
            ephemeral=True
        )


############################################################
# SALE MODAL
############################################################

class SaleModal(discord.ui.Modal, title="Sell an Item"):

    item_name = discord.ui.TextInput(
        label="Item Name",
        placeholder="Example: Diamond Pickaxe",
        required=True,
        min_length=2,
        max_length=100
    )

    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="Example: 1",
        required=True,
        max_length=10
    )

    price = discord.ui.TextInput(
        label="Sale Price",
        placeholder="Example: 2500",
        required=True,
        max_length=20
    )

    description = discord.ui.TextInput(
        label="Description",
        placeholder="Describe the item...",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):

        item_name = self.item_name.value.strip()
        quantity = self.quantity.value.strip()
        price = self.price.value.strip()
        description = self.description.value.strip()

        if not quantity.isdigit() or int(quantity) <= 0:
            await interaction.response.send_message(
                "❌ Quantity must be a whole number greater than 0.",
                ephemeral=True
            )
            return

        if not price.isdigit() or int(price) <= 0:
            await interaction.response.send_message(
                "❌ Sale price must be a whole number greater than $0.",
                ephemeral=True
            )
            return

        sale_data = {
            "item_name": item_name,
            "quantity": int(quantity),
            "price": int(price),
            "description": description
        }

        view = SaleConfirmationView(sale_data, interaction.user)

        await interaction.response.send_message(
            embed=createSaleEmbed(sale_data, interaction.user),
            view=view,
            ephemeral=True
        )


############################################################
# EMBEDS
############################################################

def createAuctionEmbed(data, user):

    embed = discord.Embed(
        title=f"🔨 {data['item_name']}",
        description=data["description"] or "No description provided.",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="📦 Quantity",
        value=str(data["quantity"]),
        inline=True
    )

    embed.add_field(
        name="💰 Starting Bid",
        value=f"${data['starting_bid']}",
        inline=True
    )

    embed.add_field(
        name="⏱️ Time Remaining",
        value=f"<t:{int(data['end_time'].timestamp())}:R>",
        inline=True
    )

    embed.set_footer(
        text=f"Auction created by {user.display_name}"
    )

    return embed


def createSaleEmbed(data, user):

    embed = discord.Embed(
        title=f"🛒 {data['item_name']}",
        description=data["description"] or "No description provided.",
        color=discord.Color.green()
    )

    embed.add_field(
        name="📦 Quantity",
        value=str(data["quantity"]),
        inline=True
    )

    embed.add_field(
        name="💰 Price",
        value=f"${data['price']}",
        inline=True
    )

    embed.set_footer(
        text=f"Listed by {user.display_name}"
    )

    return embed


############################################################
# FORUM TAG HELPER
############################################################

def get_forum_tag(forum, tag_name):

    return next(
        (
            tag
            for tag in forum.available_tags
            if tag.name.lower() == tag_name.lower()
        ),
        None
    )


############################################################
# AUCTION CONFIRMATION
############################################################

class AuctionConfirmationView(discord.ui.View):

    def __init__(self, auction_data, user):
        super().__init__(timeout=120)
        self.auction_data = auction_data
        self.user = user

    @discord.ui.button(
        label="✅ Submit Auction",
        style=discord.ButtonStyle.success
    )
    async def confirm(self, interaction, button):

        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This isn't your auction.",
                ephemeral=True
            )
            return

        forum = interaction.client.get_channel(ITEM_MARKET_FORUM_ID)

        if forum is None or not isinstance(forum, discord.ForumChannel):
            await interaction.response.send_message(
                "❌ The item market forum could not be found.",
                ephemeral=True
            )
            return

        tag = get_forum_tag(forum, "auction")

        if tag is None:
            await interaction.response.send_message(
                "❌ The `auction` forum tag does not exist.",
                ephemeral=True
            )
            return

        embed = createAuctionEmbed(
            self.auction_data,
            self.user
        )

        await forum.create_thread(
            name=f"Auction - {self.auction_data['item_name']}",
            content=self.user.mention,
            embed=embed,
            applied_tags=[tag]
        )

        await interaction.response.edit_message(
            content="✅ Auction submitted to the marketplace!",
            embed=None,
            view=None
        )

        self.stop()

    @discord.ui.button(
        label="❌ Cancel Auction",
        style=discord.ButtonStyle.danger
    )
    async def cancel(self, interaction, button):

        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This isn't your auction.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="❌ Auction cancelled.",
            embed=None,
            view=None
        )

        self.stop()


############################################################
# SALE CONFIRMATION
############################################################

class SaleConfirmationView(discord.ui.View):

    def __init__(self, sale_data, user):
        super().__init__(timeout=120)
        self.sale_data = sale_data
        self.user = user

    @discord.ui.button(
        label="✅ Submit Listing",
        style=discord.ButtonStyle.success
    )
    async def confirm(self, interaction, button):

        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This isn't your listing.",
                ephemeral=True
            )
            return

        forum = interaction.client.get_channel(ITEM_MARKET_FORUM_ID)

        if forum is None or not isinstance(forum, discord.ForumChannel):
            await interaction.response.send_message(
                "❌ The item market forum could not be found.",
                ephemeral=True
            )
            return

        tag = get_forum_tag(forum, "Sell")

        if tag is None:
            await interaction.response.send_message(
                "❌ The `sale` forum tag does not exist.",
                ephemeral=True
            )
            return

        embed = createSaleEmbed(
            self.sale_data,
            self.user
        )

        await forum.create_thread(
            name=f"Sale - {self.sale_data['item_name']}",
            content=self.user.mention,
            embed=embed,
            applied_tags=[tag]
        )

        await interaction.response.edit_message(
            content="✅ Item listed in the marketplace!",
            embed=None,
            view=None
        )

        self.stop()

    @discord.ui.button(
        label="❌ Cancel Listing",
        style=discord.ButtonStyle.danger
    )
    async def cancel(self, interaction, button):

        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This isn't your listing.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="❌ Listing cancelled.",
            embed=None,
            view=None
        )

        self.stop()


############################################################
# ITEM MARKET BUTTONS
############################################################

class ItemMarketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🏷️Create an 𝐀𝐮𝐜𝐭𝐢𝐨𝐧",
        style=discord.ButtonStyle.primary,
        custom_id="badlands_create_auction"
    )
    async def auction(self, interaction, button):

        await interaction.response.send_modal(
            AuctionModal()
        )

    @discord.ui.button(
        label="🛒𝐒𝐞𝐥𝐥 an Item",
        style=discord.ButtonStyle.primary,
        custom_id="badlands_sell_item"
    )
    async def sell(self, interaction, button):

        await interaction.response.send_modal(
            SaleModal()
        )
