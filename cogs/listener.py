# listener.py

import datetime
import discord
from discord.ext import commands
from bot import OWNER_IDS         # ← list of your bot‐owner IDs
import database as db
import re

LIMIT_PER_DAY = 2
HERE_PATTERN = re.compile(r'@here', re.IGNORECASE)
EVERY_PATTERN = re.compile(r'@everyone', re.IGNORECASE)

class KeepDeleteView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, slot_owner_id: int):
        super().__init__(timeout=None)
        self.channel = channel
        self.slot_owner_id = slot_owner_id

    @discord.ui.button(label="Keep Slot", style=discord.ButtonStyle.green, custom_id="slot_keep")
    async def keep(self, interaction, button):
        if interaction.user.id not in OWNER_IDS:
            return await interaction.response.send_message("🚫 Nope.", ephemeral=True)
        user = self.channel.guild.get_member(self.slot_owner_id) or await self.channel.guild.fetch_member(self.slot_owner_id)
        await self.channel.set_permissions(user, send_messages=True)
        await interaction.response.send_message(f"✅ Restored {user.mention}.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Delete Slot", style=discord.ButtonStyle.red, custom_id="slot_delete")
    async def delete(self, interaction, button):
        if interaction.user.id not in OWNER_IDS:
            return await interaction.response.send_message("🚫 Nope.", ephemeral=True)
        await interaction.response.send_message("🗑️ Deleting slot...", ephemeral=True)
        await db.remove_slot(self.channel.id)
        await self.channel.delete(reason="Deleted by bot‐owner")
        self.stop()

class PingListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content
        if not (HERE_PATTERN.search(content) or EVERY_PATTERN.search(content)):
            return

        slot = await db.get_slot_by_channel(message.channel.id)
        if not slot:
            return

        owner_id = slot.owner_id

        # 1) Handle @everyone immediately
        if EVERY_PATTERN.search(content):
            await message.delete()
            return await self._revoke(message.channel, owner_id, "Used @everyone")

        # 2) It's a @here – count and decide
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        count = await db.bump_ping(message.channel.id, today)

        if count <= LIMIT_PER_DAY:
            # just strip the @here and leave the rest
            new_content = HERE_PATTERN.sub("", content)
            try:
                await message.edit(content=new_content)
            except discord.Forbidden:
                # fallback: delete if edit not allowed
                await message.delete()
        else:
            # 3rd+ @here → full delete + revoke
            await message.delete()
            await self._revoke(message.channel, owner_id, "Exceeded @here limit")

    async def _revoke(self, channel, slot_owner_id, reason):
        # revoke perms
        user = channel.guild.get_member(slot_owner_id) or await channel.guild.fetch_member(slot_owner_id)
        await channel.set_permissions(user, send_messages=False)

        # notify bot‐owners
        for admin_id in OWNER_IDS:
            admin = channel.guild.get_member(admin_id) or await self.bot.fetch_user(admin_id)
            view = KeepDeleteView(channel, slot_owner_id)
            self.bot.add_view(view)
            try:
                await admin.send(
                    f"🔒 Slot **{channel.name}** (owner <@{slot_owner_id}>) was revoked.\n"
                    f"Reason: {reason}\n\n"
                    "🟢 **Keep Slot** to restore or 🔴 **Delete Slot** to remove it.",
                    view=view
                )
            except discord.Forbidden:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(PingListener(bot))
                
