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

def rand_colour():
    """Return a random Discord colour using full 24-bit RGB space."""
    return int("0x%06x" % randint(0, 0xFFFFFF), 16)

def is_admin():
    async def predicate(ctx):
        return (
            ctx.author.guild_permissions.administrator
            or any(r.id in ADMIN_ROLES for r in ctx.author.roles)
        )
    return commands.check(predicate)

# ---------------------------------------------------------------------------
class SlotBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=",", intents=intents)

    async def setup_hook(self):
        # 1) Initialize the database
        await db.init_db()
        # 2) Load all your cogs here
        from cogs.admin import AdminCog
        from cogs.listener import PingListener

        await self.add_cog(AdminCog(self, rand_colour))
        await self.add_cog(PingListener(self, rand_colour))

bot = SlotBot()

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} ({bot.user.id})")

# custom help that matches the spec ------------------------------------------------

if __name__ == "__main__":
    bot.run(TOKEN)
    
