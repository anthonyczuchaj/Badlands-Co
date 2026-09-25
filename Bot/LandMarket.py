import discord
import asyncio
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone

LAND_MARKET_FORUM_ID = 1550648522720808961
LAND_MARKET_FILE = "land_marketplace.json"
LAND_MARKET_EXPIRY_TASK = None

def load_land_market():
    if not os.path.exists(LAND_MARKET_FILE):
        return {"auctions": {}, "sales": {}, "offers": {}}

    try:
        with open(LAND_MARKET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("auctions", {})
        data.setdefault("sales", {})
        data.setdefault("offers", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"auctions": {}, "sales": {}, "offers": {}}

def save_land_market(data):
    temp = f"{LAND_MARKET_FILE}.tmp"

    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    os.replace(temp, LAND_MARKET_FILE)

def parse_duration(duration):
    match = re.fullmatch(r"(\d+)([mhdw])", duration.lower().strip())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    return datetime.now(timezone.utc) + {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount)
    }[unit]

def duration_text(duration):
    match = re.fullmatch(r"(\d+)([mhdw])", duration.lower().strip())
    if not match:
        return duration

    amount = int(match.group(1))
    names = {
        "m": "Minute" if amount == 1 else "Minutes",
        "h": "Hour" if amount == 1 else "Hours",
        "d": "Day" if amount == 1 else "Days",
        "w": "Week" if amount == 1 else "Weeks"
    }

    return f"{amount} {names[match.group(2)]}"

async def get_user(client, user_id):
    user = client.get_user(int(user_id))

    if user is None:
        try:
            user = await client.fetch_user(int(user_id))
        except discord.HTTPException:
            return None

    return user

def get_field(embed, name):
    return next(
        (field.value for field in embed.fields if field.name == name),
        None
    )

def clean_price(value):
    if not value:
        return None

    return value.replace("$", "").replace(",", "").strip()

def money(value):
    return f"${int(value):,}"

def create_auction_data(embed, seller):
    duration = get_field(embed, "⏱️ Auction Duration") or ""
    duration_match = re.search(r"<t:(\d+):R>", duration)

    return {
        "seller_id": seller.id,
        "claim_name": get_field(embed, "🏞️ Claim Name") or "Land",
        "chunks": get_field(embed, "🗺️ Chunks") or "0",
        "starting_price": clean_price(get_field(embed, "💰 Starting Price")) or "0",
        "bin_price": clean_price(get_field(embed, "⚡ BIN Price"))
            if get_field(embed, "⚡ BIN Price") != "None" else None,
        "duration": duration,
        "end_time": int(duration_match.group(1)) if duration_match else None,
        "status": "ACTIVE",
        "current_bid": None,
        "current_bidder_id": None,
        "image_url": None
    }

def create_sale_data(embed, seller):
    return {
        "seller_id": seller.id,
        "claim_name": get_field(embed, "🏞️ Claim Name") or "Land",
        "chunks": get_field(embed, "🗺️ Chunks") or "0",
        "price": clean_price(get_field(embed, "💰 Price")) or "0",
        "image_url": None,
        "end_time": None,
        "status": "ACTIVE"
    }

def create_auction_embed(data, seller=None):
    embed = discord.Embed(
        title="🔨 Land Auction",
        color=discord.Color.blue()
    )

    if data.get("image_url"):
        embed.set_image(url=data["image_url"])

    current_bid = data.get("current_bid")
    bidder_id = data.get("current_bidder_id")

    if current_bid is None:
        current_bid_value = "No bids yet"
        bidder_value = "No bidder yet"
    else:
        current_bid_value = money(current_bid)
        bidder_value = f"<@{bidder_id}>" if bidder_id else "Unknown"

    if data.get("description"):
        embed.description = data["description"]

    embed.add_field(
        name="🏞️ Claim Name",
        value=data.get("claim_name", "Unknown"),
        inline=False
    )
    embed.add_field(
        name="🗺️ Chunks",
        value=str(data.get("chunks", "0")),
        inline=True
    )
    embed.add_field(
        name="💰 Starting Price",
        value=money(data.get("starting_price", 0)),
        inline=True
    )
    embed.add_field(
        name="⚡ BIN Price",
        value=money(data["bin_price"]) if data.get("bin_price") else "None",
        inline=True
    )
    embed.add_field(
        name="🏆 Current Highest Bid",
        value=current_bid_value,
        inline=True
    )
    embed.add_field(
        name="👤 Current Bidder",
        value=bidder_value,
        inline=True
    )

    if data.get("status") in ("ENDED", "SOLD"):
        embed.add_field(
            name="⏱️ Duration",
            value=data["status"],
            inline=False
        )

    if seller:
        embed.set_footer(text=f"Seller: {seller.display_name}")

    return embed

def create_sale_embed(data, seller=None):
    embed = discord.Embed(
        title="🏦 Land For Sale",
        color=discord.Color.green()
    )

    if data.get("image_url"):
        embed.set_image(url=data["image_url"])

    embed.add_field(
        name="🏞️ Claim Name",
        value=data.get("claim_name", "Unknown"),
        inline=False
    )
    embed.add_field(
        name="🗺️ Chunks",
        value=str(data.get("chunks", "0")),
        inline=True
    )
    embed.add_field(
        name="💰 Price",
        value=money(data.get("price", 0)),
        inline=True
    )

    if data.get("status") in ("ENDED", "SOLD"):
        embed.add_field(
            name="⏱️ Duration",
            value=data["status"],
            inline=False
        )

    if seller:
        embed.set_footer(text=f"Seller: {seller.display_name}")

    return embed

def auction_header(seller, auction):
    status = auction.get("status", "ACTIVE")
    end_time = auction.get("end_time")

    if status in ("ENDED", "SOLD"):
        duration = status
    elif end_time and end_time <= int(datetime.now(timezone.utc).timestamp()):
        duration = "ENDED"
    else:
        duration = f"Duration: <t:{end_time}:R>" if end_time else "Duration: Unknown"

    return (
        f"{seller.mention if seller else ''}\n"
        f"🏷️ **{auction.get('claim_name', 'Land')}**\n"
        f"⏱️ **{duration}**"
    )

def sale_header(seller, sale):
    status = sale.get("status", "ACTIVE")
    end_time = sale.get("end_time")

    if status in ("ENDED", "SOLD"):
        duration = status
    elif end_time and end_time <= int(datetime.now(timezone.utc).timestamp()):
        duration = "ENDED"
    else:
        duration = f"Duration: <t:{end_time}:R>" if end_time else "Duration: Unknown"

    return (
        f"{seller.mention if seller else ''}\n"
        f"🏷️ **{sale.get('claim_name', 'Land')}**\n"
        f"⏱️ **{duration}**"
    )


async def get_land_thread(bot, listing_id):
    thread = bot.get_channel(int(listing_id))

    if thread is None:
        try:
            thread = await bot.fetch_channel(int(listing_id))
        except discord.HTTPException:
            return None

    return thread if isinstance(thread, discord.Thread) else None

async def ensure_land_thread_open(thread):
    if isinstance(thread, discord.Thread) and thread.archived:
        try:
            await thread.edit(archived=False)
        except discord.HTTPException:
            return False

    return True


async def end_expired_auction(bot, listing_id):
    data = load_land_market()
    auction = data["auctions"].get(str(listing_id))

    if not auction or auction.get("status") in ("ENDED", "SOLD"):
        return False

    end_time = auction.get("end_time")
    if not end_time or end_time > int(datetime.now(timezone.utc).timestamp()):
        return False

    auction["status"] = "ENDED"
    auction["duration"] = "ENDED"
    auction["end_time"] = None

    # Any pending offers are no longer valid once the listing expires.
    for offer_id, offer in list(data["offers"].items()):
        if str(offer.get("listing_id")) == str(listing_id):
            data["offers"].pop(offer_id, None)

    save_land_market(data)

    thread = await get_land_thread(bot, listing_id)
    if thread is None:
        return True

    seller = await get_user(bot, auction["seller_id"])

    try:
        if not await ensure_land_thread_open(thread):
            return True

        message = await thread.fetch_message(thread.id)
        await message.edit(
            content=auction_header(seller, auction),
            embed=create_auction_embed(auction, seller),
            view=None
        )

        await thread.send(
            "⏰ **Auction ended.**\n"
            "Bidding is now closed."
        )

        try:
            await thread.edit(archived=True)
        except discord.HTTPException:
            pass
    except discord.HTTPException as e:
        print(f"Failed to close expired auction {listing_id}: {e}")

    return True


async def end_expired_sale(bot, listing_id):
    data = load_land_market()
    sale = data["sales"].get(str(listing_id))

    if not sale or sale.get("status") in ("ENDED", "SOLD"):
        return False

    end_time = sale.get("end_time")
    if not end_time or end_time > int(datetime.now(timezone.utc).timestamp()):
        return False

    sale["status"] = "ENDED"
    sale["duration"] = "ENDED"
    sale["end_time"] = None

    # Any pending offers are no longer valid once the listing expires.
    for offer_id, offer in list(data["offers"].items()):
        if str(offer.get("listing_id")) == str(listing_id):
            data["offers"].pop(offer_id, None)

    save_land_market(data)

    thread = await get_land_thread(bot, listing_id)
    if thread is None:
        return True

    seller = await get_user(bot, sale["seller_id"])

    try:
        if not await ensure_land_thread_open(thread):
            return True

        message = await thread.fetch_message(thread.id)
        await message.edit(
            content=sale_header(seller, sale),
            embed=create_sale_embed(sale, seller),
            view=None
        )

        await thread.send(
            "⏰ **Land sale ended.**\n"
            "No purchase was completed before the listing expired."
        )

        try:
            await thread.edit(archived=True)
        except discord.HTTPException:
            pass

    except discord.HTTPException as e:
        print(f"Failed to close expired land sale {listing_id}: {e}")

    return True


async def land_market_expiry_loop(bot):
    """Keep active marketplace countdowns synchronized with their terminal state."""
    while not bot.is_closed():
        try:
            data = load_land_market()
            now = int(datetime.now(timezone.utc).timestamp())

            for listing_id, auction in list(data["auctions"].items()):
                if (
                    auction.get("status", "ACTIVE") == "ACTIVE"
                    and auction.get("end_time")
                    and auction["end_time"] <= now
                ):
                    await end_expired_auction(bot, listing_id)

            for listing_id, sale in list(data["sales"].items()):
                if (
                    sale.get("status", "ACTIVE") == "ACTIVE"
                    and sale.get("end_time")
                    and sale["end_time"] <= now
                ):
                    await end_expired_sale(bot, listing_id)

        except Exception as e:
            print(f"Land market expiry loop error: {e}")

        await asyncio.sleep(30)


def start_land_market_expiry_task(bot):
    global LAND_MARKET_EXPIRY_TASK

    if LAND_MARKET_EXPIRY_TASK is None or LAND_MARKET_EXPIRY_TASK.done():
        LAND_MARKET_EXPIRY_TASK = asyncio.create_task(land_market_expiry_loop(bot))



embedLandMarketListing = discord.Embed(
    title="𝕃𝕚𝕤𝕥 𝕒 𝕃𝕒𝕟𝕕",
    description=(
        "Take this opportunity to list your land, either for sale or for auction. "
        "Any money you make is yours to keep and yours to earn!"
    ),
    color=discord.Color.gold()
)

embedLandMarketListing.add_field(
    name="Auction 🏷️",
    value=(
        "Put your land up for auction and let other players compete for it.\n\n"
        "**You'll need:**\n"
        "• Claim name\n"
        "• Land size (chunks)\n"
        "• Starting bid\n"
        "• BIN price *(optional)*\n"
        "• Auction duration\n\n"
        "The bidder with the highest bid at the end of an auction is the winner!"
    ),
    inline=False
)

embedLandMarketListing.add_field(
    name="Sale 🏦",
    value=(
        "List your land at a fixed price. Other players can purchase it "
        "immediately at the price you set.\n\n"
        "**You'll need:**\n"
        "• Claim name\n"
        "• Land size (chunks)\n"
        "• Sale price"
    ),
    inline=False
)

embedLandMarketListing.set_footer(text="Choose an option below to get started.")
embedLandMarketListing.set_image(
    url="https://raw.githubusercontent.com/anthonyczuchaj/Badlands-Co/refs/heads/main/Bot/IMG/Banner.png"
)

class LandMarketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Auction Land", emoji="🏷️",
        style=discord.ButtonStyle.secondary,
        custom_id="land_market_auction"
    )
    async def auction_land(self, interaction, button):
        await interaction.response.send_modal(LandAuctionModal())

    @discord.ui.button(
        label="Sell Land", emoji="🏦",
        style=discord.ButtonStyle.secondary,
        custom_id="land_market_sell"
    )
    async def sell_land(self, interaction, button):
        await interaction.response.send_modal(LandSellModal())

class LandAuctionModal(discord.ui.Modal, title="🔨 Auction Land"):
    claim_name = discord.ui.TextInput(label="Claim Name", placeholder="Example: Mountain Estate", max_length=100)
    chunks = discord.ui.TextInput(label="Chunks", placeholder="Example: 25", max_length=10)
    bid_price = discord.ui.TextInput(label="Starting Price", placeholder="Example: 50000", max_length=20)
    bin_price = discord.ui.TextInput(label="BIN Price", placeholder="Example: 100000", required=False, max_length=20)
    duration = discord.ui.TextInput(label="Auction Duration", placeholder="Example: 1h, 2d, 1w", max_length=4)

    async def on_submit(self, interaction):
        duration = self.duration.value.lower().strip()
        end_time = parse_duration(duration)

        if end_time is None:
            await interaction.response.send_message(
                "❌ Invalid duration. Use values such as `30m`, `1h`, `2d`, or `1w`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔨 Auction Preview",
            description="Review your auction before creating it.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏱️ Auction Duration",
            value=f"{duration_text(duration)}\n<t:{int(end_time.timestamp())}:R>",
            inline=False
        )
        embed.add_field(name="🏞️ Claim Name", value=self.claim_name.value, inline=False)
        embed.add_field(name="🗺️ Chunks", value=self.chunks.value, inline=True)
        embed.add_field(name="💰 Starting Price", value=f"${self.bid_price.value}", inline=True)
        embed.add_field(name="⚡ BIN Price", value=f"${self.bin_price.value}" if self.bin_price.value.strip() else "None", inline=True)
        embed.set_footer(text=f"Seller: {interaction.user.display_name}")

        await interaction.response.send_message(
            embed=embed,
            view=LandAuctionConfirmationView(embed, interaction.user),
            ephemeral=True
        )

class LandSellModal(discord.ui.Modal, title="🏦 Sell Land"):
    claim_name = discord.ui.TextInput(label="Claim Name", placeholder="Example: Mountain Estate", max_length=100)
    chunks = discord.ui.TextInput(label="Chunks", placeholder="Example: 25", max_length=10)
    price = discord.ui.TextInput(label="Price", placeholder="Example: 100000", max_length=20)

    async def on_submit(self, interaction):
        embed = discord.Embed(
            title="🏦 Land Sale Preview",
            description="Review your land sale before creating it.",
            color=discord.Color.green()
        )
        embed.add_field(name="🏞️ Claim Name", value=self.claim_name.value, inline=False)
        embed.add_field(name="🗺️ Chunks", value=self.chunks.value, inline=True)
        embed.add_field(name="💰 Price", value=f"${self.price.value}", inline=True)
        embed.set_footer(text=f"Seller: {interaction.user.display_name}")

        await interaction.response.send_message(
            embed=embed,
            view=LandSellConfirmationView(embed, interaction.user),
            ephemeral=True
        )

class AmountModal(discord.ui.Modal):
    amount = discord.ui.TextInput(label="Amount", placeholder="Enter an amount", max_length=20)

    def __init__(self, title, callback):
        super().__init__(title=title)
        self.callback_function = callback

    async def on_submit(self, interaction):
        await self.callback_function(interaction, self.amount.value)

class DescriptionModal(discord.ui.Modal, title="📝 Edit Description"):
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Enter the new description...",
        style=discord.TextStyle.paragraph,
        max_length=4000
    )

    def __init__(self, listing_view):
        super().__init__()
        self.listing_view = listing_view

    async def on_submit(self, interaction):
        await self.listing_view.update_description(interaction, self.description.value)

class DurationModal(discord.ui.Modal, title="⏱️ Edit Duration"):
    duration = discord.ui.TextInput(label="Auction Duration", placeholder="Example: 30m, 1h, 2d, 1w", max_length=4)

    def __init__(self, listing_view):
        super().__init__()
        self.listing_view = listing_view

    async def on_submit(self, interaction):
        duration = self.duration.value.lower().strip()
        end_time = parse_duration(duration)

        if end_time is None:
            await interaction.response.send_message(
                "❌ Invalid duration. Use values such as `30m`, `1h`, `2d`, or `1w`.",
                ephemeral=True
            )
            return

        await self.listing_view.update_duration(interaction, duration, end_time)

def is_image_attachment(attachment):
    if attachment.content_type:
        return attachment.content_type.startswith("image/")
    return attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))

async def wait_for_land_listing_image(interaction, listing_id, listing_type):
    thread = interaction.channel

    if isinstance(thread, discord.Thread) and thread.archived:
        try:
            await thread.edit(archived=False)
        except discord.HTTPException:
            await interaction.followup.send("❌ This listing is archived and could not be reopened.", ephemeral=True)
            return

    prompt = await thread.send(
        f"{interaction.user.mention}\n"
        "📸 **Reply to THIS message with your screenshot.**\n\n"
        "Attach your image to the reply and send it.\n"
        "I'll automatically add the image to the listing and delete your upload message.\n\n"
        "⏱️ You have **2 minutes**."
    )

    def check(message):
        return (
            message.channel.id == thread.id
            and message.author.id == interaction.user.id
            and message.reference is not None
            and message.reference.message_id == prompt.id
            and any(is_image_attachment(a) for a in message.attachments)
        )

    try:
        upload_message = await interaction.client.wait_for("message", timeout=120, check=check)
        image = next(a for a in upload_message.attachments if is_image_attachment(a))
        image_bytes = await image.read()

        filename = image.filename
        if "." not in filename:
            filename += ".png"

        image_file = discord.File(io.BytesIO(image_bytes), filename=filename)
        starter_message = await thread.fetch_message(thread.id)

        data = load_land_market()
        collection = data["auctions"] if listing_type == "auction" else data["sales"]

        if str(listing_id) not in collection:
            await interaction.followup.send("❌ This listing is no longer available.", ephemeral=True)
            return

        seller = await get_user(interaction.client, collection[str(listing_id)]["seller_id"])
        embed = (
            create_auction_embed(collection[str(listing_id)], seller)
            if listing_type == "auction"
            else create_sale_embed(collection[str(listing_id)], seller)
        )
        embed.set_image(url=f"attachment://{filename}")

        await starter_message.edit(embed=embed, attachments=[image_file])

        collection[str(listing_id)]["image_url"] = (
            starter_message.attachments[0].url
            if starter_message.attachments else f"attachment://{filename}"
        )
        save_land_market(data)

        try:
            await upload_message.delete()
        except discord.HTTPException:
            pass
        try:
            await prompt.delete()
        except discord.HTTPException:
            pass

        await interaction.followup.send("✅ Your image has been added to the listing.", ephemeral=True)

    except asyncio.TimeoutError:
        try:
            await prompt.delete()
        except discord.HTTPException:
            pass
        await interaction.followup.send("⏱️ Image upload timed out.", ephemeral=True)

    except Exception as e:
        print(f"Land image upload error: {e}")
        try:
            await prompt.delete()
        except discord.HTTPException:
            pass
        await interaction.followup.send("❌ Something went wrong while adding the image.", ephemeral=True)

class LandAuctionView(discord.ui.View):
    def __init__(self, seller_id, listing_id):
        super().__init__(timeout=None)
        self.seller_id = int(seller_id)
        self.listing_id = int(listing_id)

        data = load_land_market()
        auction = data["auctions"].get(str(self.listing_id), {})
        bin_price = auction.get("bin_price")
        current_bid = int(auction.get("current_bid") or 0)

        if not bin_price or current_bid >= int(bin_price):
            self.remove_item(self.buy_now)

    async def owner_only(self, interaction):
        if interaction.user.id != self.seller_id:
            await interaction.response.send_message("❌ Only the original poster can edit this auction.", ephemeral=True)
            return False
        return True

    async def update_description(self, interaction, description):
        if not await self.owner_only(interaction):
            return

        data = load_land_market()
        auction = data["auctions"].get(str(self.listing_id))

        if not auction:
            await interaction.response.send_message("❌ This auction could not be found.", ephemeral=True)
            return

        auction["description"] = description
        save_land_market(data)

        embed = create_auction_embed(auction)
        embed.description = description
        await interaction.response.edit_message(embed=embed, view=self)

    async def update_duration(self, interaction, duration, end_time):
        if not await self.owner_only(interaction):
            return

        data = load_land_market()
        auction = data["auctions"].get(str(self.listing_id))

        if not auction:
            await interaction.response.send_message("❌ This auction could not be found.", ephemeral=True)
            return

        auction["duration"] = duration
        auction["end_time"] = int(end_time.timestamp())
        save_land_market(data)

        message = await interaction.channel.fetch_message(self.listing_id)
        seller = await get_user(interaction.client, auction["seller_id"])
        await message.edit(
            content=auction_header(seller, auction),
            embed=create_auction_embed(auction, seller),
            view=self
        )

        await interaction.response.send_message("✅ Auction duration updated.", ephemeral=True)

    @discord.ui.button(label="Place Bid", emoji="💰", style=discord.ButtonStyle.primary, row=0, custom_id="land_auction_bid")
    async def place_bid(self, interaction, button):
        data = load_land_market()
        auction = data["auctions"].get(str(self.listing_id))

        if not auction:
            await interaction.response.send_message("❌ This auction is no longer available.", ephemeral=True)
            return

        if auction.get("end_time") and auction["end_time"] <= int(datetime.now(timezone.utc).timestamp()):
            await end_expired_auction(interaction.client, self.listing_id)
            await interaction.response.send_message("❌ This auction has ended.", ephemeral=True)
            return

        await interaction.response.send_modal(BidModal(self.listing_id))

    @discord.ui.button(label="Buy It Now", emoji="⚡", style=discord.ButtonStyle.success, row=0, custom_id="land_auction_bin")
    async def buy_now(self, interaction, button):
        data = load_land_market()
        auction = data["auctions"].get(str(self.listing_id))

        if not auction or not auction.get("bin_price"):
            await interaction.response.send_message("❌ This auction does not have a Buy It Now price.", ephemeral=True)
            return

        if auction.get("end_time") and auction["end_time"] <= int(datetime.now(timezone.utc).timestamp()):
            await end_expired_auction(interaction.client, self.listing_id)
            await interaction.response.send_message("❌ This auction has ended.", ephemeral=True)
            return

        seller = await get_user(interaction.client, auction["seller_id"])

        if seller is None:
            await interaction.response.send_message("❌ Could not find the seller.", ephemeral=True)
            return

        view = PurchaseConfirmationView(
            interaction.user,
            seller,
            auction["bin_price"],
            "Buy It Now",
            self.listing_id,
            auction["claim_name"]
        )

        await interaction.response.send_message(
            embed=view.create_embed(),
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Add Image", emoji="🖼️", style=discord.ButtonStyle.secondary, row=0, custom_id="land_auction_image")
    async def image(self, interaction, button):
        if not await self.owner_only(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        await wait_for_land_listing_image(interaction, self.listing_id, "auction")

    @discord.ui.button(label="Edit Price", emoji="💵", style=discord.ButtonStyle.secondary, row=1, custom_id="land_auction_price")
    async def edit_price(self, interaction, button):
        if not await self.owner_only(interaction):
            return

        async def submit(i, amount):
            data = load_land_market()
            auction = data["auctions"].get(str(self.listing_id))

            if not auction:
                await i.response.send_message("❌ This auction could not be found.", ephemeral=True)
                return

            try:
                bin_price = int(clean_price(amount))
            except (TypeError, ValueError):
                await i.response.send_message("❌ Enter a valid whole-number BIN price.", ephemeral=True)
                return

            current_bid = int(auction.get("current_bid") or 0)
            if bin_price <= current_bid:
                await i.response.send_message(
                    f"❌ BIN price must be higher than the current bid of {money(current_bid)}.",
                    ephemeral=True
                )
                return

            auction["bin_price"] = str(bin_price)
            save_land_market(data)

            message = await i.channel.fetch_message(self.listing_id)
            seller = await get_user(i.client, auction["seller_id"])
            await message.edit(
                embed=create_auction_embed(auction, seller),
                view=LandAuctionView(auction["seller_id"], self.listing_id)
            )

            await i.response.send_message(f"✅ BIN price updated to **{money(bin_price)}**.", ephemeral=True)

        await interaction.response.send_modal(AmountModal("💵 Edit BIN Price", submit))

    @discord.ui.button(label="Edit Description", emoji="📝", style=discord.ButtonStyle.secondary, row=1, custom_id="land_auction_description")
    async def edit_description(self, interaction, button):
        if not await self.owner_only(interaction):
            return
        await interaction.response.send_modal(DescriptionModal(self))

    @discord.ui.button(label="Edit Duration", emoji="⏱️", style=discord.ButtonStyle.secondary, row=1, custom_id="land_auction_duration")
    async def edit_duration(self, interaction, button):
        if not await self.owner_only(interaction):
            return
        await interaction.response.send_modal(DurationModal(self))

    @discord.ui.button(label="Cancel Auction", emoji="🛑", style=discord.ButtonStyle.danger, row=2, custom_id="land_auction_cancel")
    async def cancel_auction(self, interaction, button):
        if not await self.owner_only(interaction):
            return

        data = load_land_market()
        auction = data["auctions"].pop(str(self.listing_id), None)

        if not auction:
            await interaction.response.send_message("❌ This auction could not be found.", ephemeral=True)
            return

        save_land_market(data)

        embed = discord.Embed(
            title="🛑 Auction Cancelled",
            description=(
                f"**Auction:** {auction.get('claim_name', 'Land')}\n"
                f"**Seller:** {interaction.user.mention}\n\n"
                "This auction was cancelled by the seller."
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(
            content=interaction.user.mention,
            embed=embed,
            view=None
        )

        if isinstance(interaction.channel, discord.Thread):
            try:
                await interaction.channel.edit(archived=True)
            except discord.HTTPException:
                pass

class BidModal(discord.ui.Modal, title="💰 Place Bid"):
    amount = discord.ui.TextInput(label="Bid Amount", placeholder="Enter your total bid", max_length=20)

    def __init__(self, listing_id):
        super().__init__()
        self.listing_id = listing_id

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = load_land_market()
        auction = data["auctions"].get(str(self.listing_id))

        if not auction:
            await interaction.followup.send("❌ This auction no longer exists.", ephemeral=True)
            return

        if auction.get("end_time") and auction["end_time"] <= int(datetime.now(timezone.utc).timestamp()):
            await end_expired_auction(interaction.client, self.listing_id)
            await interaction.followup.send("❌ This auction has ended.", ephemeral=True)
            return

        try:
            bid = int(clean_price(self.amount.value))
        except (TypeError, ValueError):
            await interaction.followup.send("❌ Enter a valid whole-number bid.", ephemeral=True)
            return

        starting = int(auction["starting_price"])
        current = int(auction["current_bid"] or 0)
        minimum = max(starting, current + 1)

        if bid < minimum:
            await interaction.followup.send(f"❌ Your bid must be at least {money(minimum)}.", ephemeral=True)
            return

        if int(auction["seller_id"]) == interaction.user.id:
            await interaction.followup.send("❌ You cannot bid on your own auction.", ephemeral=True)
            return

        thread = interaction.channel

        if isinstance(thread, discord.Thread) and thread.archived:
            try:
                await thread.edit(archived=False)
            except discord.HTTPException:
                await interaction.followup.send(
                    "❌ This auction is archived and could not be reopened.",
                    ephemeral=True
                )
                return

        auction["current_bid"] = bid
        auction["current_bidder_id"] = interaction.user.id
        save_land_market(data)

        message = await thread.fetch_message(thread.id)
        seller = await get_user(interaction.client, auction["seller_id"])

        await message.edit(
            content=auction_header(seller, auction),
            embed=create_auction_embed(auction, seller),
            view=LandAuctionView(auction["seller_id"], self.listing_id)
        )

        await interaction.followup.send(
            f"✅ Your bid of **{money(bid)}** has been placed.",
            ephemeral=True
        )

class PurchaseConfirmationView(discord.ui.View):
    def __init__(self, buyer, seller, amount, purchase_type, listing_id, claim_name):
        super().__init__(timeout=120)
        self.buyer = buyer
        self.seller = seller
        self.amount = amount
        self.purchase_type = purchase_type
        self.listing_id = listing_id
        self.claim_name = claim_name

    def create_embed(self):
        return discord.Embed(
            title="⚠️ Are You Sure?",
            description=(
                f"🏷️ **Land:** {self.claim_name}\n\n"
                f"**Buyer:** {self.buyer.mention}\n"
                f"**Seller:** {self.seller.mention}\n"
                f"**Price:** {money(self.amount)}\n\n"
                f"Are you sure you want to submit this **{self.purchase_type}**?"
            ),
            color=discord.Color.orange()
        )

    @discord.ui.button(label="Confirm", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message(
                "❌ Only the buyer who started this request can confirm it.",
                ephemeral=True
            )
            return

        data = load_land_market()

        if str(self.listing_id) in data["auctions"]:
            listing_type = "auction"
        elif str(self.listing_id) in data["sales"]:
            listing_type = "sale"
        else:
            await interaction.response.send_message("❌ This listing is no longer available.", ephemeral=True)
            return

        data["offers"][str(interaction.id)] = {
            "listing_id": self.listing_id,
            "listing_type": listing_type,
            "buyer_id": self.buyer.id,
            "seller_id": self.seller.id,
            "amount": self.amount,
            "message_id": None
        }
        save_land_market(data)

        embed = discord.Embed(
            title="🛒 Land Purchase Offer",
            description=(
                f"🏷️ **Land:** {self.claim_name}\n\n"
                f"**Buyer:** {self.buyer.mention}\n"
                f"**Seller:** {self.seller.mention}\n"
                f"**Offer:** {money(self.amount)}\n\n"
                "The seller can accept or decline this offer below."
            ),
            color=discord.Color.blue()
        )

        view = SellerOfferView(
            interaction.id,
            self.buyer,
            self.seller,
            self.amount,
            self.listing_id,
            listing_type
        )

        await interaction.response.send_message(content=self.seller.mention, embed=embed, view=view)

        offer_message = await interaction.original_response()
        data = load_land_market()
        if str(interaction.id) in data["offers"]:
            data["offers"][str(interaction.id)]["message_id"] = offer_message.id
            save_land_market(data)

        await interaction.followup.edit_message(
            interaction.message.id,
            content="✅ Your offer has been sent to the seller.",
            embed=None,
            view=None
        )

    @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("❌ Only the buyer can cancel this request.", ephemeral=True)
            return

        await interaction.response.edit_message(content="❌ Purchase cancelled.", embed=None, view=None)

class SellerOfferView(discord.ui.View):
    def __init__(self, offer_id, buyer, seller, amount, listing_id, listing_type):
        super().__init__(timeout=None)
        self.offer_id = str(offer_id)
        self.buyer = buyer
        self.seller = seller
        self.amount = amount
        self.listing_id = int(listing_id)
        self.listing_type = listing_type

    async def seller_only(self, interaction):
        if interaction.user.id != self.seller.id:
            await interaction.response.send_message("❌ Only the seller can respond to this offer.", ephemeral=True)
            return False
        return True

    def remove_offer(self):
        data = load_land_market()
        data["offers"].pop(self.offer_id, None)
        save_land_market(data)

    async def close_listing(self, bot):
        data = load_land_market()

        auction = data["auctions"].get(str(self.listing_id))
        sale = data["sales"].get(str(self.listing_id))
        listing = auction or sale

        if not listing:
            data["offers"].pop(self.offer_id, None)
            save_land_market(data)
            return

        listing["status"] = "SOLD"
        listing["duration"] = "SOLD"
        listing["end_time"] = None

        # Remove every pending offer for this listing because it is now sold.
        for offer_id, offer in list(data["offers"].items()):
            if str(offer.get("listing_id")) == str(self.listing_id):
                data["offers"].pop(offer_id, None)

        save_land_market(data)

        thread = await get_land_thread(bot, self.listing_id)
        if thread is None:
            return

        seller = await get_user(bot, listing["seller_id"])

        try:
            # The interaction message has already been acknowledged by accept().
            # Keep the thread open long enough to update the original listing.
            if not await ensure_land_thread_open(thread):
                return

            if auction:
                content = auction_header(seller, listing)
                embed = create_auction_embed(listing, seller)
            else:
                content = sale_header(seller, listing)
                embed = create_sale_embed(listing, seller)

            message = await thread.fetch_message(thread.id)
            await message.edit(
                content=content,
                embed=embed,
                view=None
            )

            await thread.send("✅ **Land SOLD!** The sale has been completed.")

            try:
                await thread.edit(archived=True)
            except discord.HTTPException:
                pass

        except discord.HTTPException as e:
            print(f"Failed to finalize sold listing {self.listing_id}: {e}")

    @discord.ui.button(label="Accept", emoji="✅", style=discord.ButtonStyle.success, custom_id="land_offer_accept")
    async def accept(self, interaction, button):
        if not await self.seller_only(interaction):
            return

        thread = interaction.channel

        # Discord can deliver the button interaction while the thread is archived.
        # Re-open it before sending the interaction response.
        if isinstance(thread, discord.Thread):
            if not await ensure_land_thread_open(thread):
                await interaction.response.send_message(
                    "❌ This offer is in an archived thread that could not be reopened.",
                    ephemeral=True
                )
                return

        embed = discord.Embed(
            title="🏞️ Land Sold",
            description=(
                f"🏷️ **Land:** {self.listing_type.title()}\n\n"
                f"**Buyer:** {self.buyer.mention}\n"
                f"**Seller:** {self.seller.mention}\n"
                f"**Sale Price:** {money(self.amount)}\n\n"
                "The seller accepted the offer."
            ),
            color=discord.Color.green()
        )

        # IMPORTANT: acknowledge/edit the clicked interaction BEFORE archiving
        # the thread. This prevents Discord error 50083 (Thread is archived).
        await interaction.response.edit_message(
            content=f"{self.buyer.mention} {self.seller.mention}",
            embed=embed,
            view=None
        )

        try:
            await self.close_listing(interaction.client)
        except Exception as e:
            print(f"Failed to finalize accepted offer {self.offer_id}: {e}")

    @discord.ui.button(label="Decline", emoji="❌", style=discord.ButtonStyle.danger, custom_id="land_offer_decline")
    async def decline(self, interaction, button):
        if not await self.seller_only(interaction):
            return

        self.remove_offer()

        embed = discord.Embed(
            title="❌ Offer Declined",
            description=(
                f"**Buyer:** {self.buyer.mention}\n"
                f"**Seller:** {self.seller.mention}\n"
                f"**Offer:** {money(self.amount)}\n\n"
                "The seller declined the offer."
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(content=self.buyer.mention, embed=embed, view=None)

class LandSaleView(discord.ui.View):
    def __init__(self, seller_id, listing_id):
        super().__init__(timeout=None)
        self.seller_id = int(seller_id)
        self.listing_id = int(listing_id)

    async def owner_only(self, interaction):
        if interaction.user.id != self.seller_id:
            await interaction.response.send_message("❌ Only the original poster can edit this land sale.", ephemeral=True)
            return False
        return True

    async def update_description(self, interaction, description):
        if not await self.owner_only(interaction):
            return

        data = load_land_market()
        sale = data["sales"].get(str(self.listing_id))

        if not sale:
            await interaction.response.send_message("❌ This listing could not be found.", ephemeral=True)
            return

        sale["description"] = description
        save_land_market(data)

        embed = create_sale_embed(sale)
        embed.description = description
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Buy Now", emoji="🛒", style=discord.ButtonStyle.success, row=0, custom_id="land_sale_buy")
    async def buy_now(self, interaction, button):
        data = load_land_market()
        sale = data["sales"].get(str(self.listing_id))

        if not sale:
            await interaction.response.send_message("❌ This listing is no longer available.", ephemeral=True)
            return

        if sale.get("end_time") and sale["end_time"] <= int(datetime.now(timezone.utc).timestamp()):
            await end_expired_sale(interaction.client, self.listing_id)
            await interaction.response.send_message("❌ This land sale has ended.", ephemeral=True)
            return

        seller = await get_user(interaction.client, sale["seller_id"])

        if seller is None:
            await interaction.response.send_message("❌ Could not find the seller.", ephemeral=True)
            return

        view = PurchaseConfirmationView(
            interaction.user,
            seller,
            sale["price"],
            "Buy Now",
            self.listing_id,
            sale["claim_name"]
        )

        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="Counter Offer", emoji="🤝", style=discord.ButtonStyle.primary, row=0, custom_id="land_sale_offer")
    async def counter_offer(self, interaction, button):
        async def submit(i, amount):
            data = load_land_market()
            sale = data["sales"].get(str(self.listing_id))

            if not sale:
                await i.response.send_message("❌ This listing is no longer available.", ephemeral=True)
                return

            if sale.get("end_time") and sale["end_time"] <= int(datetime.now(timezone.utc).timestamp()):
                await end_expired_sale(i.client, self.listing_id)
                await i.response.send_message("❌ This land sale has ended.", ephemeral=True)
                return

            try:
                amount = int(clean_price(amount))
            except (TypeError, ValueError):
                await i.response.send_message("❌ Enter a valid whole-number offer.", ephemeral=True)
                return

            seller = await get_user(i.client, sale["seller_id"])

            if seller is None:
                await i.response.send_message("❌ Could not find the seller.", ephemeral=True)
                return

            offer_id = str(i.id)

            data["offers"][offer_id] = {
                "listing_id": self.listing_id,
                "listing_type": "sale",
                "buyer_id": i.user.id,
                "seller_id": seller.id,
                "amount": amount,
                "message_id": None
            }
            save_land_market(data)

            embed = discord.Embed(
                title="🤝 Land Offer",
                description=(
                    f"**Buyer:** {i.user.mention}\n"
                    f"**Seller:** {seller.mention}\n"
                    f"**Offer:** {money(amount)}\n\n"
                    "The seller can accept or decline this offer below."
                ),
                color=discord.Color.orange()
            )

            await i.response.send_message(
                content=seller.mention,
                embed=embed,
                view=SellerOfferView(offer_id, i.user, seller, amount, self.listing_id, "sale")
            )

        await interaction.response.send_modal(AmountModal("🤝 Counter Offer", submit))

    @discord.ui.button(label="Add Image", emoji="🖼️", style=discord.ButtonStyle.secondary, row=0, custom_id="land_sale_image")
    async def image(self, interaction, button):
        if not await self.owner_only(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        await wait_for_land_listing_image(interaction, self.listing_id, "sale")

    @discord.ui.button(label="Edit Price", emoji="💵", style=discord.ButtonStyle.secondary, row=1, custom_id="land_sale_price")
    async def edit_price(self, interaction, button):
        if not await self.owner_only(interaction):
            return

        async def submit(i, amount):
            data = load_land_market()
            sale = data["sales"].get(str(self.listing_id))

            if not sale:
                await i.response.send_message("❌ This listing could not be found.", ephemeral=True)
                return

            sale["price"] = clean_price(amount)
            save_land_market(data)

            embed = create_sale_embed(sale)
            if sale.get("description"):
                embed.description = sale["description"]

            await i.response.edit_message(embed=embed, view=self)

        await interaction.response.send_modal(AmountModal("💵 Edit Price", submit))

    @discord.ui.button(label="Edit Description", emoji="📝", style=discord.ButtonStyle.secondary, row=1, custom_id="land_sale_description")
    async def edit_description(self, interaction, button):
        if not await self.owner_only(interaction):
            return

        await interaction.response.send_modal(DescriptionModal(self))

class LandAuctionConfirmationView(discord.ui.View):
    def __init__(self, embed, seller):
        super().__init__(timeout=120)
        self.embed = embed
        self.seller = seller

    @discord.ui.button(label="Confirm", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        forum = interaction.client.get_channel(LAND_MARKET_FORUM_ID)

        if forum is None or not isinstance(forum, discord.ForumChannel):
            await interaction.response.send_message("❌ The land market forum could not be found.", ephemeral=True)
            return

        auction_tag = discord.utils.find(lambda tag: tag.name.lower() == "auction", forum.available_tags)

        if auction_tag is None:
            await interaction.response.send_message("❌ The **Auction** forum tag could not be found.", ephemeral=True)
            return

        data = create_auction_data(self.embed, self.seller)

        header = (
            f"{self.seller.mention}\n"
            f"🏷️ **{data['claim_name']}**\n"
            f"⏱️ **Duration:** <t:{data['end_time']}:R>"
        )

        thread = await forum.create_thread(
            name=f"🔨 {data['claim_name']}",
            content=header,
            embed=create_auction_embed(data, self.seller),
            applied_tags=[auction_tag]
        )

        listing_id = thread.thread.id

        data["description"] = None
        data["image_url"] = None

        marketplace = load_land_market()
        marketplace["auctions"][str(listing_id)] = data
        save_land_market(marketplace)

        starter_message = await thread.thread.fetch_message(listing_id)
        await starter_message.edit(view=LandAuctionView(self.seller.id, listing_id))

        await interaction.response.edit_message(
            content=f"✅ Auction created! {thread.thread.mention}",
            view=None
        )

    @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="❌ Auction cancelled.", embed=None, view=None)

class LandSellConfirmationView(discord.ui.View):
    def __init__(self, embed, seller):
        super().__init__(timeout=120)
        self.embed = embed
        self.seller = seller

    @discord.ui.button(label="Confirm", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        forum = interaction.client.get_channel(LAND_MARKET_FORUM_ID)

        if forum is None or not isinstance(forum, discord.ForumChannel):
            await interaction.response.send_message("❌ The land market forum could not be found.", ephemeral=True)
            return

        sale_tag = discord.utils.find(lambda tag: tag.name.lower() == "for sale", forum.available_tags)

        if sale_tag is None:
            await interaction.response.send_message("❌ The **For Sale** forum tag could not be found.", ephemeral=True)
            return

        data = create_sale_data(self.embed, self.seller)

        # Sales use the same relative-duration system as auctions.
        data["end_time"] = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
        data["status"] = "ACTIVE"

        thread = await forum.create_thread(
            name=f"🏦 {data['claim_name']}",
            content=(
                f"{self.seller.mention}\n"
                f"🏷️ **{data['claim_name']}**\n"
                f"⏱️ **Duration:** <t:{data['end_time']}:R>"
            ),
            embed=create_sale_embed(data, self.seller),
            applied_tags=[sale_tag]
        )

        listing_id = thread.thread.id

        data["description"] = None
        data["image_url"] = None

        marketplace = load_land_market()
        marketplace["sales"][str(listing_id)] = data
        save_land_market(marketplace)

        starter_message = await thread.thread.fetch_message(listing_id)
        await starter_message.edit(view=LandSaleView(self.seller.id, listing_id))

        await interaction.response.edit_message(
            content=f"✅ Land sale created! {thread.thread.mention}",
            view=None
        )

    @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="❌ Land sale cancelled.", embed=None, view=None)

async def restore_land_market_views(bot):
    data = load_land_market()
    restored = 0

    for listing_id, auction in list(data["auctions"].items()):
        try:
            auction.setdefault("status", "ACTIVE")

            if auction.get("status") in ("ENDED", "SOLD"):
                continue

            thread = await get_land_thread(bot, listing_id)
            if thread is None:
                continue

            if auction.get("end_time") and auction["end_time"] <= int(datetime.now(timezone.utc).timestamp()):
                await end_expired_auction(bot, listing_id)
                continue

            seller = await get_user(bot, auction["seller_id"])
            if seller is None:
                continue

            bot.add_view(
                LandAuctionView(auction["seller_id"], int(listing_id)),
                message_id=int(listing_id)
            )
            restored += 1
        except Exception as e:
            print(f"Failed to restore land auction {listing_id}: {e}")

    for listing_id, sale in list(data["sales"].items()):
        try:
            sale.setdefault("status", "ACTIVE")

            if sale.get("status") in ("ENDED", "SOLD"):
                continue

            thread = await get_land_thread(bot, listing_id)
            if thread is None:
                continue

            if sale.get("end_time") and sale["end_time"] <= int(datetime.now(timezone.utc).timestamp()):
                await end_expired_sale(bot, listing_id)
                continue

            bot.add_view(
                LandSaleView(sale["seller_id"], int(listing_id)),
                message_id=int(listing_id)
            )
            restored += 1
        except Exception as e:
            print(f"Failed to restore land sale {listing_id}: {e}")

    # Restore pending seller offers. Offers belonging to completed listings
    # are discarded so a SOLD/ENDED listing cannot be purchased again.
    for offer_id, offer in list(data["offers"].items()):
        message_id = offer.get("message_id")
        if not message_id:
            continue

        listing_id = str(offer.get("listing_id"))
        listing = (
            data["auctions"].get(listing_id)
            or data["sales"].get(listing_id)
        )

        if not listing or listing.get("status", "ACTIVE") != "ACTIVE":
            data["offers"].pop(offer_id, None)
            continue

        try:
            seller = await get_user(bot, offer["seller_id"])
            buyer = await get_user(bot, offer["buyer_id"])

            if seller is None or buyer is None:
                continue

            bot.add_view(
                SellerOfferView(
                    offer_id,
                    buyer,
                    seller,
                    offer["amount"],
                    offer["listing_id"],
                    offer["listing_type"]
                ),
                message_id=int(message_id)
            )
        except Exception as e:
            print(f"Failed to restore land offer {offer_id}: {e}")

    save_land_market(data)

    # Keep expiration automatic after startup. Active listings will be checked
    # every 30 seconds even if nobody presses a button.
    start_land_market_expiry_task(bot)

    return restored

