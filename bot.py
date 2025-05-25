import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import base64
import random

# ─── CONFIG ────────────────────────────────────────────────────────────────
BOT_PREFIX      = ","
CATEGORY_ID     = 1375748081735172126
ADMIN_ROLE_ID   = 1375747962487181342
ADMIN_IDS       = {
    993153549095673936,
    1241446608424407052,
    1083998643322892401,
    981093886351003709
}

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)
bot.remove_command("help")

# In-memory slot store:
# { channel_id: { owner_id, created_at, expiration (datetime), pings (int) } }
slots = {}

# ─── HELP COMMAND ─────────────────────────────────────────────────────────
@bot.command(aliases=["h"])
async def help(ctx):
    embed = discord.Embed(
        title="📖 Luxury Mart Slot Bot Help",
        color=discord.Color.blue()
    )
    embed.add_field(
        name=",create",
        value="Create a new slot (admins only).",
        inline=False
    )
    embed.add_field(
        name=",revoke",
        value="Revoke someone’s slot (admins only).",
        inline=False
    )
    embed.add_field(
        name=",transfer",
        value="Transfer your slot to another user.",
        inline=False
    )
    embed.add_field(
        name=",Aslot",
        value="Restore your slot via your key.",
        inline=False
    )
    await ctx.send(embed=embed)

# ─── UTILITIES ────────────────────────────────────────────────────────────
def is_admin(member: discord.Member) -> bool:
    # By ID or by having the admin role
    if member.id in ADMIN_IDS:
        return True
    return any(r.id == ADMIN_ROLE_ID for r in member.roles)

def encode_key(data: dict) -> str:
    """
    Base64‐encode a little pipe‐delimited blob:
      owner_id|channel_name|expiration_iso|pings
    """
    raw = f"{data['owner_id']}|{data['channel_name']}|{data['expiration'].isoformat()}|{data['pings']}"
    return base64.urlsafe_b64encode(raw.encode()).decode()

def decode_key(key: str) -> dict:
    raw = base64.urlsafe_b64decode(key.encode()).decode()
    owner_id, channel_name, exp_iso, pings = raw.split("|")
    return {
        "owner_id":   int(owner_id),
        "channel_name": channel_name,
        "expiration": datetime.datetime.fromisoformat(exp_iso),
        "pings":      int(pings)
    }

async def revoke_slot(channel: discord.TextChannel, reason: str):
    info = slots.pop(channel.id, None)
    # Delete the channel and DM the owner
    await channel.delete(reason=reason)
    if info:
        guild = channel.guild
        owner = guild.get_member(info["owner_id"])
        if owner:
            await owner.send(
                embed=discord.Embed(
                    description=f"❌ Your slot `{channel.name}` was revoked: {reason}",
                    color=discord.Color.red()
                )
            )

# ─── ASLOT COMMAND ────────────────────────────────────────────────────────
@bot.command()
async def Aslot(ctx: commands.Context):
    # Must be run in a server channel
    if ctx.guild is None:
        return await ctx.send(
            embed=discord.Embed(
                description="⚠️ Run `,Aslot` in one of the server’s channels.",
                color=discord.Color.red()
            )
        )

    # 1) Prompt in DM
    try:
        dm = await ctx.author.create_dm()
        await dm.send(
            embed=discord.Embed(
                description="🔑 Please enter your slot key to restore your slot:",
                color=discord.Color.blue()
            )
        )
    except discord.Forbidden:
        return await ctx.send(
            embed=discord.Embed(
                description="⚠️ I can’t DM you. Please enable DMs from server members.",
                color=discord.Color.orange()
            )
        )

    def check_dm(msg: discord.Message):
        return (
            msg.author == ctx.author
            and isinstance(msg.channel, discord.DMChannel)
        )

    # 2) Wait for key
    try:
        reply = await bot.wait_for("message", check=check_dm, timeout=120)
    except asyncio.TimeoutError:
        return await dm.send(
            embed=discord.Embed(
                description="⌛ You took too long to reply. Please try `,Aslot` again.",
                color=discord.Color.red()
            )
        )

    # 3) Decode & validate
    try:
        data = decode_key(reply.content.strip())
    except Exception:
        return await dm.send(
            embed=discord.Embed(
                description="❌ Invalid key format.",
                color=discord.Color.red()
            )
        )

    if data["owner_id"] != ctx.author.id:
        return await dm.send(
            embed=discord.Embed(
                description="🚫 That key does not belong to you.",
                color=discord.Color.red()
            )
        )

    if datetime.datetime.utcnow() > data["expiration"]:
        return await dm.send(
            embed=discord.Embed(
                description="⏰ Your slot key has expired.",
                color=discord.Color.red()
            )
        )

    # 4) Re-create the channel under the original category
    category = ctx.guild.get_channel(CATEGORY_ID)
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            mention_everyone=False
        ),
        ctx.author: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            mention_everyone=True
        ),
    }
    # admins by ID
    for aid in ADMIN_IDS:
        m = ctx.guild.get_member(aid)
        if m:
            overwrites[m] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                mention_everyone=True
            )
    # admin role
    ar = ctx.guild.get_role(ADMIN_ROLE_ID)
    if ar:
        overwrites[ar] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            mention_everyone=True
        )

    channel = await ctx.guild.create_text_channel(
        name=data["channel_name"],
        category=category,
        overwrites=overwrites
    )

    # 5) Store it back in memory
    slots[channel.id] = {
        "owner_id":   data["owner_id"],
        "created_at": datetime.datetime.utcnow(),
        "expiration": data["expiration"],
        "pings":      data["pings"]
    }

    # 6) Send the rules/info embed in the new channel
    rules_text = (
        "• No @everyone pings allowed — will revoke immediately.\n"
        "• Max 2 @here pings per day.\n"
        "• 3rd @here ping will revoke the slot.\n"
        "• Only slot owner & staff can send here.\n"
        "• Slots auto-delete after expiry.\n"
        "• Be respectful & follow server rules."
    )
    info_text = (
        f"**Owner:** {ctx.author.mention}\n"
        f"**UserID:** {ctx.author.id}\n"
        f"**Expires:** <t:{int(data['expiration'].timestamp())}:R>"
    )
    embed = discord.Embed(
        title="✅ Slot Restored!",
        description=rules_text,
        color=discord.Color.green()
    ).add_field(name="Slot Info", value=info_text)
    await channel.send(embed=embed)

    # 7) Confirm in DM
    await dm.send(
        embed=discord.Embed(
            description=f"🎉 Your slot has been restored: {channel.mention}",
            color=discord.Color.green()
        )
    )

# ─── PING MANAGEMENT ──────────────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    # allow commands to still run
    await bot.process_commands(message)

    if message.author.bot:
        return

    ch = message.channel
    if not isinstance(ch, discord.TextChannel):
        return
    info = slots.get(ch.id)
    if not info:
        return

    content = message.content

    # 1) @everyone instantly revokes
    if "@everyone" in content:
        return await revoke_slot(ch, "Used @everyone ping")

    # 2) @here counting
    if "@here" in content:
        info["pings"] += 1
        cnt = info["pings"]

        if cnt > 2:
            return await revoke_slot(ch, "Exceeded @here pings")

        # show 1/2 or 2/2
        await ch.send(
            embed=discord.Embed(
                description=f"🔔 Ping {cnt}/2",
                color=discord.Color.blue()
            )
        )
        # warn on the 2nd ping
        if cnt == 2:
            await message.author.send(
                embed=discord.Embed(
                    description="⚠️ You have reached your 2/2 daily @here ping limit.",
                    color=discord.Color.orange()
                )
            )

# ─── BOT START ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run("YOUR_BOT_TOKEN")
    
