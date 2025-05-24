import datetime
import os
import discord
from discord.ext import commands
import database as db
from random import randint

OWNER_IDS = [int(i) for i in os.getenv("OWNER_IDS", "").split(",") if i]
LIMIT_PER_DAY = 2
rand_colour = lambda: int("0x%06x" % randint(0, 0xFFFFFF), 16)

class KeepDeleteView(discord.ui.View):
    """Persistent buttons for owners to keep/delete a slot."""
    def __init__(self, bot, channel_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id

    @discord.ui.button(label="Keep", style=discord.ButtonStyle.green, custom_id="slot_keep")
    async def keep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("Not for you.", ephemeral=True)
            return
        await interaction.response.send_message("Slot kept. Thanks!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red, custom_id="slot_delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("Not for you.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(self.channel_id)
        if channel:
            await interaction.response.send_message("Deleting slot…", ephemeral=True)
            from cogs.admin import AdminCog
            cog = interaction.client.get_cog("AdminCog")
            await cog._hard_delete(channel, "Owner chose delete", interaction.user)
        self.stop()

class PingListener(commands.Cog):
    """Listens for @here/@everyone misuse and handles automatic revocation."""
    def __init__(self, bot):
        self.bot = bot
        # register a global persistent view so the buttons survive restarts
        self.bot.add_view(KeepDeleteView(bot, 0))  # dummy for registration

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content_lower = message.content.lower()
        if "@here" not in content_lower and "@everyone" not in content_lower:
            return

        slot = await db.get_slot_by_channel(message.channel.id)
        if slot is None:
            return  # not a slot channel

        # @everyone → immediate revoke with buttons to owners
        if "@everyone" in content_lower:
            await self._ask_owners(message.channel, message.author, "Used @everyone")
            return

        # track @here count
        day_key = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        count = await db.bump_ping(message.channel.id, day_key)
        await message.channel.send(f"🔔 {count}/{LIMIT_PER_DAY} pings today.")
        if count > LIMIT_PER_DAY:
            await self._ask_owners(message.channel, message.author, "Exceeded @here limit")

    async def _ask_owners(self, channel: discord.TextChannel, offender: discord.Member, reason: str):
        """Send owners a keep/delete decision card."""
        view = KeepDeleteView(self.bot, channel.id)
        self.bot.add_view(view)  # make it persistent

        embed = discord.Embed(title="Slot requires attention", colour=rand_colour())
        embed.add_field(name="Channel", value=channel.mention)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Offender", value=offender.mention)
        for oid in OWNER_IDS:
            owner = channel.guild.get_member(oid)
            if owner:
                await owner.send(embed=embed, view=view)

        await channel.send("🚫 Slot temporarily locked pending owner decision.")
            
