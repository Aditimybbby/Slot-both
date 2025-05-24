import asyncio
import os
import discord
from discord.ext import commands
import database as db
from random import randint

OWNER_IDS = [int(i) for i in os.getenv("OWNER_IDS", "").split(",") if i]
CATEGORY_ID = int(os.getenv("CATEGORY_ID"))

# helper for random embed colour
rand_colour = lambda: int("0x%06x" % randint(0, 0xFFFFFF), 16)

class AdminCog(commands.Cog):
    """Handles ,create ,revoke ,status and ,transfer."""

    def __init__(self, bot):
        self.bot = bot

    # ----------------------------------------------------------
    @commands.command(name="create")
    async def create_slot(self, ctx, member: discord.Member | None = None, duration: int | None = None):
        if not ctx.author.guild_permissions.administrator:
            return

        try:
            if member is None:
                await ctx.send("Mention the **user** who gets the slot:")
                resp = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                member = await commands.MemberConverter().convert(ctx, resp.content)

            if duration is None:
                await ctx.send("How many **days** should the slot last?")
                resp = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                duration = int(resp.content)

            await ctx.send("Finally, **slot name**?")
            resp = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
            slot_name = resp.content

        except asyncio.TimeoutError:
            await ctx.send("⌛ Timed-out.")
            return
        except Exception as exc:
            await ctx.send(f"Error: {exc}")
            return

        guild = ctx.guild
        category = guild.get_channel(CATEGORY_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        channel = await guild.create_text_channel(slot_name, category=category, overwrites=overwrites)

        await db.add_slot(guild.id, channel.id, member.id, slot_name, duration)

        rule_embed = discord.Embed(title="Slot rules", colour=rand_colour())
        rule_embed.description = (
            "• Max **2** `@here` pings per day.
"
            "• **NO** `@everyone` pings.
"
            "• Follow staff instructions."
        )
        await channel.send(member.mention, embed=rule_embed)

        await member.send(
            f"🎉 Your slot **{slot_name}** is live! Slot-ID: `{channel.id}` (expires in {duration} days)."
        )
        await ctx.send(f"✅ Created {channel.mention} for {member.mention}")

    # ----------------------------------------------------------
    @commands.command(name="revoke")
    async def revoke_slot(self, ctx, channel_id: int | None = None):
        if not ctx.author.guild_permissions.administrator:
            return

        try:
            if channel_id is None:
                await ctx.send("Channel **ID** to revoke:")
                resp = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                channel_id = int(resp.content)

            channel = ctx.guild.get_channel(channel_id)
            if channel is None:
                await ctx.send("Channel not found.")
                return

            await ctx.send("Reason for revoke?")
            resp = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
            reason = resp.content

        except asyncio.TimeoutError:
            await ctx.send("⌛ Timed-out.")
            return

        await self._hard_delete(channel, reason, ctx.author)

    # ----------------------------------------------------------
    @commands.command(name="status")
    async def slot_status(self, ctx, channel: discord.TextChannel | None = None):
        """Show info about the slot you’re in (or another channel)."""
        channel = channel or ctx.channel
        slot = await db.get_slot_by_channel(channel.id)
        if slot is None:
            await ctx.send("This channel isn’t a managed slot.")
            return
        owner = ctx.guild.get_member(slot[3])
        embed = discord.Embed(title=f"Slot status: {channel.name}", colour=rand_colour())
        embed.add_field(name="Owner", value=owner.mention if owner else slot[3])
        embed.add_field(name="Created", value=slot[5].split("T")[0])
        embed.add_field(name="Duration (days)", value=slot[6])
        await ctx.send(embed=embed)

    # ----------------------------------------------------------
    @commands.command(name="transfer")
    async def transfer_slot(self, ctx, new_owner: discord.Member | None = None):
        slot = await db.get_slot_by_channel(ctx.channel.id)
        if slot is None:
            await ctx.send("Run this inside the slot you want to transfer.")
            return
        if ctx.author.id != slot[3] and not ctx.author.guild_permissions.administrator:
            await ctx.send("Only the slot owner or an admin can transfer.")
            return

        try:
            if new_owner is None:
                await ctx.send("Mention the **new owner**:")
                resp = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                new_owner = await commands.MemberConverter().convert(ctx, resp.content)
        except asyncio.TimeoutError:
            await ctx.send("⌛ Timed-out.")
            return

        await db.update_slot_owner(ctx.channel.id, new_owner.id)
        await ctx.channel.set_permissions(new_owner, view_channel=True, send_messages=True)
        old_owner = ctx.guild.get_member(slot[3])
        if old_owner and old_owner != new_owner:
            await ctx.channel.set_permissions(old_owner, overwrite=None)
        await ctx.send(f"✅ Slot transferred to {new_owner.mention}")
        await new_owner.send(f"🎁 You have been given control of slot **{ctx.channel.name}**")

    # ----------------------------------------------------------
    async def _hard_delete(self, channel: discord.TextChannel, reason: str, actor):
        slot = await db.get_slot_by_channel(channel.id)
        if slot:
            owner = channel.guild.get_member(slot[3])
            if owner:
                await owner.send(f"❌ Your slot **{channel.name}** was revoked.
Reason: {reason}
By: {actor}")
        await db.remove_slot(channel.id)
        await channel.delete(reason=reason)
