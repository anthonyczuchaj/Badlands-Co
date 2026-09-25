import discord
import re
import json
import os
import uuid
import asyncio
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path


# The forum channel where completed marketplace posts are created.
ITEM_MARKET_FORUM_ID = 1550648832784736366


# Persistent marketplace data.
MARKETPLACE_FILE = "marketplace.json"


def load_marketplace():
    if not os.path.exists(MARKETPLACE_FILE):
        return {
            "auctions": {},
            "sales": {},
            "pending_orders": {}
        }

    try:
        with open(MARKETPLACE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("auctions", {})
        data.setdefault("sales", {})
        data.setdefault("pending_orders", {})
        return data

    except (json.JSONDecodeError, OSError):
        # Do not destroy the file if it cannot be read.
        return {
            "auctions": {},
            "sales": {},
            "pending_orders": {}
        }


def save_marketplace(data):
    # Write to a temporary file first so a crash during a write
    # does not leave marketplace.json half-written.
    temp_file = MARKETPLACE_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    os.replace(temp_file, MARKETPLACE_FILE)


def save_auction(auction_id, auction_data):
    marketplace = load_marketplace()
    marketplace["auctions"][str(auction_id)] = auction_data
    save_marketplace(marketplace)


def save_sale(sale_id, sale_data):
    marketplace = load_marketplace()
    marketplace["sales"][str(sale_id)] = sale_data
    save_marketplace(marketplace)


def delete_auction(auction_id):
    marketplace = load_marketplace()
    marketplace["auctions"].pop(str(auction_id), None)
    save_marketplace(marketplace)


def delete_sale(sale_id):
    marketplace = load_marketplace()
    marketplace["sales"].pop(str(sale_id), None)
    save_marketplace(marketplace)


def save_pending_order(order_id, order_data):
    marketplace = load_marketplace()
    marketplace["pending_orders"][str(order_id)] = order_data
    save_marketplace(marketplace)


def delete_pending_order(order_id):
    marketplace = load_marketplace()
    marketplace["pending_orders"].pop(str(order_id), None)
    save_marketplace(marketplace)


async def get_user_for_listing(client, user_id):
    user = client.get_user(int(user_id))

    if user is None:
        try:
            user = await client.fetch_user(int(user_id))
        except discord.NotFound:
            return None

    return user


def auction_from_json(data):
    data = dict(data)
    data["end_time"] = datetime.fromisoformat(data["end_time"])
    return data


def sale_from_json(data):
    return dict(data)


async def restore_marketplace_views(bot):
    """
    Re-register every active auction/sale button after a bot restart.

    The listing state lives in marketplace.json, so the Python objects
    from before the restart do not need to survive.
    """
    marketplace = load_marketplace()

    restored = 0

    for auction_id, raw_data in marketplace["auctions"].items():
        auction_data = auction_from_json(raw_data)

        # Leave expired auctions stored so their post can still show
        # the final state. They simply won't accept new bids.
        view = AuctionBidView(auction_id)

        try:
            bot.add_view(
                view,
                message_id=int(auction_id)
            )
            restored += 1
        except (ValueError, TypeError):
            pass

    for sale_id, raw_data in marketplace["sales"].items():
        view = SaleBuyView(sale_id)

        try:
            bot.add_view(
                view,
                message_id=int(sale_id)
            )
            restored += 1
        except (ValueError, TypeError):
            pass

    for order_id, raw_data in marketplace["pending_orders"].items():
        message_id = raw_data.get("order_message_id")
        if message_id is None:
            continue
        try:
            bot.add_view(OrderApprovalView(order_id), message_id=int(message_id))
            restored += 1
        except (ValueError, TypeError):
            pass

    return restored


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

        if not starting_bid.isdigit() or int(starting_bid) < 500:
            await interaction.response.send_message(
                "❌ Starting bid must be a whole number of at least **$500**.",
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
            "highest_bid": int(starting_bid),
            "highest_bidder_id": None,
            "duration": duration,
            "end_time": end_time.isoformat(),
            "description": description,
            "seller_id": interaction.user.id,
            "image_url": None
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
            "description": description,
            "seller_id": interaction.user.id,
            "image_url": None
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
        value=f"${data['starting_bid']:,}",
        inline=True
    )

    highest_bid = data.get("highest_bid", data["starting_bid"])
    highest_bidder = data.get("highest_bidder")
    highest_bidder_id = data.get("highest_bidder_id")

    if highest_bidder is None and highest_bidder_id is not None:
        highest_bidder = f"<@{highest_bidder_id}>"

    # JSON stores the timestamp as text.
    end_time = data["end_time"]
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    if highest_bidder:
        highest_bid_text = f"${highest_bid:,}\nby {highest_bidder}"
    else:
        highest_bid_text = f"${highest_bid:,}\nNo bids yet"

    embed.add_field(
        name="🏆 Current Highest Bid",
        value=highest_bid_text,
        inline=False
    )

    embed.add_field(
        name="⏱️ Time Remaining",
        value=f"<t:{int(end_time.timestamp())}:R>",
        inline=True
    )

    if data.get("image_url"):
        embed.set_image(url=data["image_url"])

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
        value=f"${data['price']:,}",
        inline=True
    )

    if data.get("image_url"):
        embed.set_image(url=data["image_url"])

    embed.set_footer(
        text=f"Listed by {user.display_name}"
    )

    return embed


############################################################
# AUCTION BIDDING
############################################################

class BidModal(discord.ui.Modal, title="Place a Bid"):

    bid_amount = discord.ui.TextInput(
        label="Bid Amount",
        placeholder="Enter your total bid (must be higher than the current bid)",
        required=True,
        max_length=10
    )

    def __init__(self, auction_id):
        super().__init__()
        self.auction_id = str(auction_id)

    async def on_submit(self, interaction: discord.Interaction):

        marketplace = load_marketplace()
        raw_data = marketplace["auctions"].get(self.auction_id)

        if raw_data is None:
            await interaction.response.send_message(
                "❌ This auction no longer exists.",
                ephemeral=True
            )
            return

        auction_data = auction_from_json(raw_data)

        if interaction.user.id == int(auction_data["seller_id"]):
            await interaction.response.send_message(
                "❌ You cannot bid on your own auction.",
                ephemeral=True
            )
            return

        if datetime.now(timezone.utc) >= auction_data["end_time"]:
            await interaction.response.send_message(
                "❌ This auction has ended.",
                ephemeral=True
            )
            return

        bid_text = self.bid_amount.value.strip().replace(",", "")

        if not bid_text.isdigit():
            await interaction.response.send_message(
                "❌ Your bid must be a whole number.",
                ephemeral=True
            )
            return

        bid_amount = int(bid_text)

        current_bid = auction_data.get(
            "highest_bid",
            auction_data["starting_bid"]
        )

        # The entered amount is the TOTAL bid.
        # Example: current bid $9,000 + entering $10,001 = $10,001 total.
        if bid_amount <= current_bid:
            await interaction.response.send_message(
                f"❌ Your total bid must be higher than the current bid of **${current_bid:,}**.",
                ephemeral=True
            )
            return

        new_bid = bid_amount

        auction_data["highest_bid"] = new_bid
        auction_data["highest_bidder_id"] = interaction.user.id

        # Convert back to JSON-safe form before saving.
        raw_data["highest_bid"] = new_bid
        raw_data["highest_bidder_id"] = interaction.user.id
        save_marketplace(marketplace)

        seller = await get_user_for_listing(
            interaction.client,
            auction_data["seller_id"]
        )

        if seller is None:
            await interaction.response.send_message(
                "❌ The auction seller could not be found.",
                ephemeral=True
            )
            return

        await interaction.message.edit(
            embed=createAuctionEmbed(
                {
                    **auction_data,
                    "highest_bidder": interaction.user.mention
                },
                seller
            ),
            view=AuctionBidView(self.auction_id)
        )

        await interaction.response.send_message(
            f"✅ Your total bid is now **${new_bid:,}**!",
            ephemeral=True
        )


class AuctionBidView(discord.ui.View):

    def __init__(self, auction_id):
        super().__init__(timeout=None)
        self.auction_id = str(auction_id)

    @discord.ui.button(
        label="💰 Place Bid",
        style=discord.ButtonStyle.success,
        custom_id="badlands_place_bid",
        row=0
    )
    async def place_bid(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        raw_data = marketplace["auctions"].get(self.auction_id)

        if raw_data is None:
            await interaction.response.send_message("❌ This auction no longer exists.", ephemeral=True)
            return

        seller_id = int(raw_data["seller_id"])
        if interaction.user.id == seller_id:
            await interaction.response.send_message("❌ You cannot bid on your own auction.", ephemeral=True)
            return

        end_time = datetime.fromisoformat(raw_data["end_time"])
        if datetime.now(timezone.utc) >= end_time:
            await interaction.response.send_message("❌ This auction has ended.", ephemeral=True)
            return

        await interaction.response.send_modal(BidModal(self.auction_id))

    @discord.ui.button(
        label="⏱️ Extend Duration",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_extend_auction",
        row=0
    )
    async def extend_duration(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        auction = marketplace["auctions"].get(self.auction_id)

        if auction is None:
            await interaction.response.send_message("❌ This auction no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(auction["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this auction can edit it.", ephemeral=True)
            return

        await interaction.response.send_modal(
            ListingValueModal(
                self.auction_id,
                "auction",
                "duration",
                "Extend Auction Duration",
                "Additional Time",
                "Example: 30m, 2h, 1d"
            )
        )

    @discord.ui.button(
        label="🖼️ Add Image",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_auction_image",
        row=0
    )
    async def add_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        auction = marketplace["auctions"].get(self.auction_id)

        if auction is None:
            await interaction.response.send_message("❌ This auction no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(auction["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this auction can edit it.", ephemeral=True)
            return

        await wait_for_listing_image(interaction, self.auction_id, "auction")

    @discord.ui.button(
        label="📦 Change Quantity",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_auction_quantity",
        row=0
    )
    async def change_quantity(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        auction = marketplace["auctions"].get(self.auction_id)

        if auction is None:
            await interaction.response.send_message("❌ This auction no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(auction["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this auction can edit it.", ephemeral=True)
            return

        await interaction.response.send_modal(
            ListingValueModal(
                self.auction_id,
                "auction",
                "quantity",
                "Change Auction Quantity",
                "Quantity",
                "Example: 25"
            )
        )

    @discord.ui.button(
        label="📝 Change Description",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_auction_description",
        row=1
    )
    async def change_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        auction = marketplace["auctions"].get(self.auction_id)

        if auction is None:
            await interaction.response.send_message("❌ This auction no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(auction["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this auction can edit it.", ephemeral=True)
            return

        await interaction.response.send_modal(DescriptionModal(self.auction_id, "auction"))

    @discord.ui.button(
        label="❌ Cancel Auction",
        style=discord.ButtonStyle.danger,
        custom_id="badlands_cancel_auction",
        row=1
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        auction = marketplace["auctions"].get(self.auction_id)

        if auction is None:
            await interaction.response.send_message("❌ This auction no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(auction["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this auction can cancel it.", ephemeral=True)
            return

        marketplace["auctions"].pop(self.auction_id, None)
        save_marketplace(marketplace)

        await interaction.response.edit_message(
            content="❌ **This auction has been cancelled.**",
            embed=None,
            view=None
        )


############################################################
# SALE BUYING
############################################################

class BuyModal(discord.ui.Modal, title="Buy Item"):

    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter the quantity you want to buy",
        required=True,
        max_length=10
    )

    def __init__(self, sale_id):
        super().__init__()
        self.sale_id = str(sale_id)

    async def on_submit(self, interaction: discord.Interaction):
        marketplace = load_marketplace()
        sale_data = marketplace["sales"].get(self.sale_id)

        if sale_data is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return

        if interaction.user.id == int(sale_data["seller_id"]):
            await interaction.response.send_message("❌ You cannot buy your own listing.", ephemeral=True)
            return

        quantity_text = self.quantity.value.strip().replace(",", "")
        if not quantity_text.isdigit():
            await interaction.response.send_message("❌ Quantity must be a whole number.", ephemeral=True)
            return

        quantity = int(quantity_text)
        if quantity <= 0:
            await interaction.response.send_message("❌ Quantity must be greater than **0**.", ephemeral=True)
            return

        available = int(sale_data["quantity"])
        if quantity > available:
            await interaction.response.send_message(f"❌ There are only **{available}** available.", ephemeral=True)
            return

        total = quantity * int(sale_data["price"])
        order_id = uuid.uuid4().hex
        order_data = {
            "sale_id": self.sale_id,
            "buyer_id": interaction.user.id,
            "seller_id": int(sale_data["seller_id"]),
            "item_name": sale_data["item_name"],
            "quantity": quantity,
            "price_each": int(sale_data["price"]),
            "total": total,
            "status": "pending",
            "order_message_id": None
        }

        view = OrderApprovalView(order_id)
        await interaction.response.send_message(
            content=(
                f"🛒 **Purchase Request**\n"
                f"👤 Buyer: {interaction.user.mention}\n"
                f"📦 Item: **{quantity} x {sale_data['item_name']}**\n"
                f"💰 Total: **${total:,}**\n\n"
                f"<@{sale_data['seller_id']}> please **Accept** or **Deny** this order."
            ),
            view=view
        )

        order_message = await interaction.original_response()
        order_data["order_message_id"] = order_message.id
        save_pending_order(order_id, order_data)
        interaction.client.add_view(OrderApprovalView(order_id), message_id=order_message.id)


class OrderApprovalView(discord.ui.View):

    def __init__(self, order_id):
        super().__init__(timeout=None)
        self.order_id = str(order_id)

    @discord.ui.button(label="✅ Accept Order", style=discord.ButtonStyle.success, custom_id="badlands_accept_order")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        order = marketplace["pending_orders"].get(self.order_id)

        if order is None:
            await interaction.response.send_message("❌ This order no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(order["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can accept the order.", ephemeral=True)
            return

        sale_data = marketplace["sales"].get(str(order["sale_id"]))
        if sale_data is None:
            await interaction.response.edit_message(content="❌ **Order denied.** The listing no longer exists.", view=None)
            delete_pending_order(self.order_id)
            return

        quantity = int(order["quantity"])
        available = int(sale_data["quantity"])
        if quantity > available:
            await interaction.response.edit_message(content=f"❌ **Order denied.** Only **{available}** remain.", view=None)
            delete_pending_order(self.order_id)
            return

        sale_data["quantity"] = available - quantity
        marketplace["sales"][str(order["sale_id"])] = sale_data
        save_marketplace(marketplace)

        seller = await get_user_for_listing(interaction.client, order["seller_id"])
        if seller is not None:
            try:
                sale_message = await interaction.channel.fetch_message(int(order["sale_id"]))
                if sale_data["quantity"] <= 0:
                    new_embed = discord.Embed(title=f"🛒 {sale_data['item_name']}", description=sale_data["description"] or "No description provided.", color=discord.Color.dark_grey())
                    new_embed.add_field(name="📦 Quantity", value="SOLD OUT", inline=True)
                    new_embed.add_field(name="💰 Price Per Item", value=f"${sale_data['price']:,} each", inline=True)
                    new_embed.set_footer(text=f"Listed by {seller.display_name}")
                    await sale_message.edit(embed=new_embed, view=None)
                    marketplace = load_marketplace()
                    marketplace["sales"].pop(str(order["sale_id"]), None)
                    save_marketplace(marketplace)
                else:
                    await sale_message.edit(embed=createSaleEmbed(sale_data, seller), view=SaleBuyView(str(order["sale_id"])))
            except discord.HTTPException:
                pass

        await interaction.response.edit_message(
            content=(f"✅ **Order Accepted!**\n" f"👤 Buyer: <@{order['buyer_id']}>\n" f"📦 {order['quantity']} x {order['item_name']}\n" f"💰 Payment Total: **${order['total']:,}**"),
            view=None
        )
        delete_pending_order(self.order_id)

    @discord.ui.button(label="❌ Deny Order", style=discord.ButtonStyle.danger, custom_id="badlands_deny_order")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        order = marketplace["pending_orders"].get(self.order_id)
        if order is None:
            await interaction.response.send_message("❌ This order no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(order["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can deny the order.", ephemeral=True)
            return

        await interaction.response.edit_message(
            content=f"❌ **Order Denied.**\n👤 Buyer: <@{order['buyer_id']}>\n📦 {order['quantity']} x {order['item_name']}",
            view=None
        )
        delete_pending_order(self.order_id)


class SaleBuyView(discord.ui.View):

    def __init__(self, sale_id):
        super().__init__(timeout=None)
        self.sale_id = str(sale_id)

    @discord.ui.button(
        label="🛒 Buy",
        style=discord.ButtonStyle.success,
        custom_id="badlands_buy_item",
        row=0
    )
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        sale_data = marketplace["sales"].get(self.sale_id)

        if sale_data is None:
            await interaction.response.send_message("❌ This item is sold out or the listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id == int(sale_data["seller_id"]):
            await interaction.response.send_message("❌ You cannot buy your own listing.", ephemeral=True)
            return
        if int(sale_data["quantity"]) <= 0:
            await interaction.response.send_message("❌ This item is sold out.", ephemeral=True)
            return

        await interaction.response.send_modal(BuyModal(self.sale_id))

    @discord.ui.button(
        label="🖼️ Add Image",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_sale_image",
        row=0
    )
    async def add_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        sale = marketplace["sales"].get(self.sale_id)
        if sale is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(sale["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can edit it.", ephemeral=True)
            return
        await wait_for_listing_image(interaction, self.sale_id, "sale")

    @discord.ui.button(
        label="📦 Change Quantity",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_sale_quantity",
        row=0
    )
    async def change_quantity(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        sale = marketplace["sales"].get(self.sale_id)
        if sale is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(sale["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can edit it.", ephemeral=True)
            return
        await interaction.response.send_modal(
            ListingValueModal(self.sale_id, "sale", "quantity", "Change Quantity", "Quantity", "Example: 25")
        )

    @discord.ui.button(
        label="💰 Change Price",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_sale_price",
        row=0
    )
    async def change_price(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        sale = marketplace["sales"].get(self.sale_id)
        if sale is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(sale["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can edit it.", ephemeral=True)
            return
        await interaction.response.send_modal(
            ListingValueModal(self.sale_id, "sale", "price", "Change Sale Price", "Sale Price", "Enter the new price")
        )

    @discord.ui.button(
        label="📝 Change Description",
        style=discord.ButtonStyle.secondary,
        custom_id="badlands_sale_description",
        row=1
    )
    async def change_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        sale = marketplace["sales"].get(self.sale_id)
        if sale is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(sale["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can edit it.", ephemeral=True)
            return
        await interaction.response.send_modal(DescriptionModal(self.sale_id, "sale"))

    @discord.ui.button(
        label="❌ Cancel Listing",
        style=discord.ButtonStyle.danger,
        custom_id="badlands_cancel_sale",
        row=1
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketplace = load_marketplace()
        sale = marketplace["sales"].get(self.sale_id)
        if sale is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(sale["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can cancel it.", ephemeral=True)
            return

        marketplace["sales"].pop(self.sale_id, None)
        save_marketplace(marketplace)
        await interaction.response.edit_message(
            content="❌ **This listing has been cancelled.**",
            embed=None,
            view=None
        )


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
# LISTING EDITING
############################################################

class ListingValueModal(discord.ui.Modal):
    def __init__(self, listing_id, listing_type, field_name, title, label, placeholder):
        super().__init__(title=title)
        self.listing_id = str(listing_id)
        self.listing_type = listing_type
        self.field_name = field_name
        self.value_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            max_length=20
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        marketplace = load_marketplace()
        collection = "auctions" if self.listing_type == "auction" else "sales"
        data = marketplace[collection].get(self.listing_id)

        if data is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(data["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can edit it.", ephemeral=True)
            return

        value = self.value_input.value.strip().replace(",", "")

        if self.field_name in ("quantity", "price", "starting_bid"):
            if not value.isdigit() or int(value) <= 0:
                await interaction.response.send_message("❌ Enter a whole number greater than 0.", ephemeral=True)
                return
            number = int(value)

            if self.field_name == "starting_bid":
                if data.get("highest_bidder_id") is not None:
                    await interaction.response.send_message(
                        "❌ You cannot change the starting bid after the auction has received a bid.",
                        ephemeral=True
                    )
                    return
                if number < 500:
                    await interaction.response.send_message("❌ Starting bid must be at least $500.", ephemeral=True)
                    return
                data["starting_bid"] = number
                data["highest_bid"] = number
            else:
                data[self.field_name] = number

        elif self.field_name == "duration":
            additional_time = parse_duration(value)
            if additional_time is None:
                await interaction.response.send_message(
                    "❌ Invalid duration. Use formats like `30m`, `1h`, `1d`, or `1w`.",
                    ephemeral=True
                )
                return

            # Extend from the current end time, rather than resetting the auction.
            current_end = datetime.fromisoformat(data["end_time"])
            amount = additional_time - datetime.now(timezone.utc)
            data["duration"] = value
            data["end_time"] = (current_end + amount).isoformat()

        save_marketplace(marketplace)
        await refresh_listing_message(interaction.client, self.listing_id, self.listing_type)
        await interaction.response.send_message("✅ Listing updated.", ephemeral=True)


class DescriptionModal(discord.ui.Modal):
    def __init__(self, listing_id, listing_type):
        super().__init__(title="Change Description")
        self.listing_id = str(listing_id)
        self.listing_type = listing_type
        self.description = discord.ui.TextInput(
            label="Description",
            placeholder="Enter the new description...",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        marketplace = load_marketplace()
        collection = "auctions" if self.listing_type == "auction" else "sales"
        data = marketplace[collection].get(self.listing_id)

        if data is None:
            await interaction.response.send_message("❌ This listing no longer exists.", ephemeral=True)
            return
        if interaction.user.id != int(data["seller_id"]):
            await interaction.response.send_message("❌ Only the person who created this listing can edit it.", ephemeral=True)
            return

        data["description"] = self.description.value.strip()
        save_marketplace(marketplace)
        await refresh_listing_message(interaction.client, self.listing_id, self.listing_type)
        await interaction.response.send_message("✅ Description updated.", ephemeral=True)


def is_image_attachment(attachment):
    """Return True when a Discord attachment looks like an image."""
    content_type = (getattr(attachment, "content_type", None) or "").lower()
    if content_type.startswith("image/"):
        return True

    filename = (getattr(attachment, "filename", "") or "").lower()
    return filename.endswith((
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"
    ))


async def wait_for_listing_image(
    interaction: discord.Interaction,
    listing_id,
    listing_type
):
    """
    Ask the seller to reply to the bot's image-upload prompt.

    The seller's reply must contain an image attachment.
    The image is copied onto the permanent marketplace listing,
    then the seller's reply is deleted.
    """

    marketplace = load_marketplace()
    collection = "auctions" if listing_type == "auction" else "sales"

    data = marketplace[collection].get(str(listing_id))

    if data is None:
        await interaction.response.send_message(
            "❌ This listing no longer exists.",
            ephemeral=True
        )
        return

    if interaction.user.id != int(data["seller_id"]):
        await interaction.response.send_message(
            "❌ Only the person who created this listing can add an image.",
            ephemeral=True
        )
        return

    if interaction.channel is None:
        await interaction.response.send_message(
            "❌ I couldn't access the listing thread.",
            ephemeral=True
        )
        return

    channel_id = interaction.channel.id
    seller_id = interaction.user.id

    # --------------------------------------------------------
    # SEND A NORMAL, VISIBLE MESSAGE
    # --------------------------------------------------------

    await interaction.response.send_message(
        "📸 **Reply to THIS message with your screenshot.**\n\n"
        "Attach your image to the reply and send it.\n"
        "I'll automatically add the image to the listing and "
        "delete your upload message.\n\n"
        "⏱️ You have **2 minutes**."
    )

    # Get the actual bot message we just sent.
    prompt_message = await interaction.original_response()

    prompt_message_id = prompt_message.id

    # --------------------------------------------------------
    # WAIT FOR A REPLY TO THAT SPECIFIC BOT MESSAGE
    # --------------------------------------------------------

    def check(message: discord.Message):

        # Must be in the same listing thread.
        if message.channel.id != channel_id:
            return False

        # Must be the seller.
        if message.author.id != seller_id:
            return False

        # Must be a reply.
        reference = message.reference

        if reference is None:
            return False

        # IMPORTANT:
        # The reply must be to the bot's upload prompt,
        # NOT the original auction message.
        if reference.message_id != prompt_message_id:
            return False

        # Must contain an image.
        return any(
            is_image_attachment(attachment)
            for attachment in message.attachments
        )

    try:
        upload_message = await interaction.client.wait_for(
            "message",
            timeout=120,
            check=check
        )

    except asyncio.TimeoutError:

        try:
            await prompt_message.edit(
                content=(
                    "⏱️ **Image upload timed out.**\n\n"
                    "Press **🖼️ Add Image** again when you're ready."
                )
            )
        except discord.HTTPException:
            pass

        return

    # --------------------------------------------------------
    # GET THE IMAGE
    # --------------------------------------------------------

    attachment = next(
        (
            attachment
            for attachment in upload_message.attachments
            if is_image_attachment(attachment)
        ),
        None
    )

    if attachment is None:
        return

    try:

        # Read the image BEFORE deleting the user's message.
        image_bytes = await attachment.read()

        filename = attachment.filename or "screenshot.png"

        extension = os.path.splitext(filename)[1].lower()

        if extension not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp"
        }:
            extension = ".png"

        permanent_filename = (
            f"badlands_listing_{listing_id}{extension}"
        )

        image_file = discord.File(
            io.BytesIO(image_bytes),
            filename=permanent_filename
        )

        # ----------------------------------------------------
        # GET SELLER
        # ----------------------------------------------------

        seller = await get_user_for_listing(
            interaction.client,
            data["seller_id"]
        )

        if seller is None:
            await interaction.followup.send(
                "❌ I couldn't find the listing owner.",
                ephemeral=True
            )
            return

        # ----------------------------------------------------
        # GET THE ORIGINAL MARKETPLACE POST
        # ----------------------------------------------------

        thread = interaction.channel

        starter_message = await thread.fetch_message(
            int(listing_id)
        )

        # ----------------------------------------------------
        # UPDATE THE MARKETPLACE LISTING
        # ----------------------------------------------------

        data["image_url"] = (
            f"attachment://{permanent_filename}"
        )

        if listing_type == "auction":
            embed = createAuctionEmbed(
                data,
                seller
            )

            view = AuctionBidView(
                str(listing_id)
            )

        else:
            embed = createSaleEmbed(
                data,
                seller
            )

            view = SaleBuyView(
                str(listing_id)
            )

        updated_message = await starter_message.edit(
            embed=embed,
            view=view,
            attachments=[image_file]
        )

        # ----------------------------------------------------
        # SAVE THE REAL DISCORD CDN URL
        # ----------------------------------------------------

        if updated_message.attachments:

            data["image_url"] = (
                updated_message.attachments[0].url
            )

            data["image_filename"] = (
                updated_message.attachments[0].filename
            )

        else:

            data["image_url"] = None

            data.pop(
                "image_filename",
                None
            )

        save_marketplace(marketplace)

        # ----------------------------------------------------
        # DELETE THE SELLER'S REPLY
        # ----------------------------------------------------

        try:
            await upload_message.delete()

        except discord.HTTPException:
            pass

        # ----------------------------------------------------
        # DELETE THE BOT'S PROMPT TOO
        # ----------------------------------------------------

        try:
            await prompt_message.delete()

        except discord.HTTPException:
            pass

        # ----------------------------------------------------
        # CONFIRM TO SELLER
        # ----------------------------------------------------

        await interaction.followup.send(
            "✅ **Screenshot added to the listing!**\n"
            "Your upload reply was deleted.",
            ephemeral=True
        )

    except (discord.HTTPException, discord.NotFound) as exc:

        print(
            f"Badlands image upload error: {exc}"
        )

        await interaction.followup.send(
            "❌ I couldn't add that screenshot to the listing. "
            "Please try again.",
            ephemeral=True
        )



async def refresh_listing_message(client, listing_id, listing_type):
    marketplace = load_marketplace()
    collection = "auctions" if listing_type == "auction" else "sales"
    data = marketplace[collection].get(str(listing_id))
    if data is None:
        return

    seller = await get_user_for_listing(client, data["seller_id"])
    if seller is None:
        return

    try:
        thread = client.get_channel(int(listing_id))
        if thread is None:
            thread = await client.fetch_channel(int(listing_id))
        starter_message = await thread.fetch_message(int(listing_id))
        view = AuctionBidView(str(listing_id)) if listing_type == "auction" else SaleBuyView(str(listing_id))
        embed = createAuctionEmbed(data, seller) if listing_type == "auction" else createSaleEmbed(data, seller)
        await starter_message.edit(embed=embed, view=view)
    except discord.HTTPException:
        pass


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

        result = await forum.create_thread(
            name=f"Auction - {self.auction_data['item_name']}",
            content=self.user.mention,
            embed=embed,
            applied_tags=[tag],
            view=AuctionBidView("__temporary__")
        )

        thread = getattr(result, "thread", result)

        # Forum starter message ID is the same as the thread ID.
        auction_id = str(thread.id)

        self.auction_data["end_time"] = (
            self.auction_data["end_time"]
            if isinstance(self.auction_data["end_time"], str)
            else self.auction_data["end_time"].isoformat()
        )
        self.auction_data["seller_id"] = self.user.id

        save_auction(auction_id, self.auction_data)

        # Replace the temporary view with the real persistent one.
        persistent_view = AuctionBidView(auction_id)
        interaction.client.add_view(
            persistent_view,
            message_id=thread.id
        )

        try:
            starter_message = getattr(result, "message", None)

            if starter_message is None:
                starter_message = await thread.fetch_message(thread.id)

            await starter_message.edit(
                view=persistent_view
            )
        except discord.HTTPException:
            pass

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

        tag = get_forum_tag(forum, "For Sale")

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

        result = await forum.create_thread(
            name=f"Sale - {self.sale_data['item_name']}",
            content=self.user.mention,
            embed=embed,
            applied_tags=[tag],
            view=SaleBuyView("__temporary__")
        )

        thread = getattr(result, "thread", result)

        # Forum starter message ID is the same as the thread ID.
        sale_id = str(thread.id)

        self.sale_data["seller_id"] = self.user.id
        save_sale(sale_id, self.sale_data)

        # Replace the temporary view with the real persistent one.
        persistent_view = SaleBuyView(sale_id)
        interaction.client.add_view(
            persistent_view,
            message_id=thread.id
        )

        try:
            starter_message = getattr(result, "message", None)

            if starter_message is None:
                starter_message = await thread.fetch_message(thread.id)

            await starter_message.edit(
                view=persistent_view
            )
        except discord.HTTPException:
            pass

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
