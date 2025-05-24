import asyncio
from discord.ext import commands
from discord import Intents
from random import randint
import database as db

# ----- Configuration (hard-coded!) -----------------------------------------
TOKEN       = "MTEzOTg2NTY5NzQwMTQ1MDUxNg.GncFs-.Jie29HHgEnGTTMIPtlfNVPUbo5htOKJAW7Or9E"  # ← put your full bot token here
CATEGORY_ID = 123456789012345678  # ← your channel category ID
OWNER_IDS   = [111111111111111111, 222222222222222222]  # ← your Discord user IDs
ADMIN_ROLES = [333333333333333333, 444444444444444444]  # ← role IDs that count as “admin”

# ----- Bot Setup -----------------------------------------------------------
intents = Intents.default()
intents.message_content = True
intents.members         = True

def rand_colour():
    """Return a random Discord colour using full 24-bit RGB space."""
    return int(f"0x{randint(0, 0xFFFFFF):06x}", 16)

def is_admin():
    async def predicate(ctx):
        return (
            ctx.author.guild_permissions.administrator
            or any(r.id in ADMIN_ROLES for r in ctx.author.roles)
        )
    return commands.check(predicate)

class SlotBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=",", intents=intents)

    async def setup_hook(self):
        # 1) Initialize your database
        await db.init_db()
        # 2) Load all your cogs here
        from cogs.admin    import AdminCog
        from cogs.listener import PingListener

        await self.add_cog(AdminCog(self, rand_colour))
        await self.add_cog(PingListener(self, rand_colour))

bot = SlotBot()

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} ({bot.user.id})")

# If you have custom help or other events, put them below

if __name__ == "__main__":
    bot.run(TOKEN)
    
