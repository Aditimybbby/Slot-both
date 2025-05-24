import os
import asyncio
from dotenv import load_dotenv
from discord.ext import commands
from discord import Intents
from random import randint
import database as db

# ----- helpers -------------------------------------------------------------
load_dotenv()
TOKEN       = os.getenv("TOKEN")
CATEGORY_ID = int(os.getenv("CATEGORY_ID"))
OWNER_IDS   = [int(i) for i in os.getenv("OWNER_IDS", "").split(",") if i]
ADMIN_ROLES = [int(i) for i in os.getenv("ADMIN_ROLE_IDS", "").split(",") if i]

intents = Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=",", intents=intents)


def rand_colour():
    """Return a random Discord colour using full 24‑bit RGB space."""
    return int("0x%06x" % randint(0, 0xFFFFFF), 16)


def is_admin():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator or any(r.id in ADMIN_ROLES for r in ctx.author.roles)
    return commands.check(predicate)

# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    await db.init_db()
    print(f"[READY] Logged in as {bot.user} ({bot.user.id})")

# custom help that matches the spec ------------------------------------------------
@bot.command(name="help")
@is_admin()
async def _help(ctx):
    from discord import Embed
    embed = Embed(title=f"Hey {ctx.author.display_name}! Here are my commands:",
                  colour=rand_colour())
    embed.add_field(name=",create  <@user> <duration>",
                    value="Create a slot channel for a user. Leave args blank for interactive mode.",
                    inline=False)
    embed.add_field(name=",status [#channel]",
                    value="Show status of the current or specified slot.", inline=False)
    embed.add_field(name=",transfer <@new_owner> (run inside slot)",
                    value="Transfer control of the slot to another user.", inline=False)
    embed.add_field(name=",revoke <channel-id>",
                    value="Revoke (delete) a slot channel after confirmation.", inline=False)
    embed.add_field(name=",revoke  <channel‑ID>",
                    value="Delete a slot channel after confirmation.", inline=False)
    await ctx.send(embed=embed, delete_after=60)

# ---------------------------------------------------------------------------
async def setup_cogs():
    from cogs.admin import AdminCog
    from cogs.listener import PingListener
    await bot.add_cog(AdminCog(bot, rand_colour))
    await bot.add_cog(PingListener(bot, rand_colour))

bot.loop.create_task(setup_cogs())
bot.run(TOKEN)
