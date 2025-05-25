import discord
from discord.ext import commands, tasks
from discord import Embed, Permissions
import asyncio
import base64, json
from datetime import datetime, timedelta, date

# Bot configuration
BOT_PREFIX = ","
CATEGORY_ID = 1375748081735172126
ADMIN_ROLE_ID = 1375747962487181342
ADMIN_IDS = {993153549095673936, 1241446608424407052, 1083998643322892401, 981093886351003709}
TIMEZONE_OFFSET = +5.5  # Asia/Kolkata offset from UTC

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)
bot.remove_command('help')  # ← ensure no existing help command remains

# In-memory slot registry
# slot_data: {
#   channel_id: {
#       owner_id: int,
#       expiration: datetime,
#       key: str,
#       timer_msg_id: int,
#       last_reminder: int,
#       pings: int,
#       last_ping_reset: date,
#       channel_name: str
#   }
# }
slots = {}

# Helpers
def parse_duration(s: str) -> timedelta:
    unit = s[-1].lower()
    try:
        val = int(s[:-1])
    except ValueError:
        raise
    if unit == 'h': return timedelta(hours=val)
    if unit == 'd': return timedelta(days=val)
    if unit == 'm': return timedelta(days=30*val)
    raise ValueError

async def revoke_slot(channel: discord.TextChannel, reason: str):
    data = slots.pop(channel.id, None)
    if not data:
        return
    owner = channel.guild.get_member(data['owner_id'])
    # DM owner
    if owner:
        em = Embed(color=discord.Color.red(), description=f"🔒 Your slot **{channel.name}** has been revoked.\n**Reason:** {reason}\nPlease contact any admin/owner.")
        await owner.send(embed=em)
    await channel.delete()

# Background tasks
tasks_registered = False

@tasks.loop(minutes=1)
async def update_timers():
    now = datetime.utcnow()
    for ch_id, data in list(slots.items()):
        exp = data['expiration']
        remaining = exp - now
        if remaining.total_seconds() <= 0:
            # expired
            guild = bot.get_guild(bot.guilds[0].id)
            channel = guild.get_channel(ch_id)
            if channel:
                await revoke_slot(channel, "Slot expired ⏰")
            continue
        # update embed
        days = remaining.days
        hours, rem = divmod(remaining.seconds, 3600)
        minutes = rem // 60
        guild = bot.get_guild(bot.guilds[0].id)
        channel = guild.get_channel(ch_id)
        if not channel: continue
        try:
            timer_msg = await channel.fetch_message(data['timer_msg_id'])
            em = Embed(color=discord.Color.blue(), title="⏳ Time Remaining")
            em.description = f"**{days}d:{hours}h:{minutes}m**"
            await timer_msg.edit(embed=em)
        except Exception:
            pass

@tasks.loop(minutes=60)
async def send_reminders():
    now = datetime.utcnow()
    for ch_id, data in slots.items():
        exp = data['expiration']
        remaining = exp - now
        days = remaining.days
        if 0 < days <= 5 and days != data.get('last_reminder'):
            guild = bot.get_guild(bot.guilds[0].id)
            channel = guild.get_channel(ch_id)
            owner = guild.get_member(data['owner_id'])
            msg = f"📢 Hey {owner.mention}, Your slot is expiring in **{days} days**. Please renew it as soon as possible."
            if channel:
                await channel.send(msg)
            if owner:
                await owner.send(msg)
            slots[ch_id]['last_reminder'] = days

# Events

@bot.event
async def on_ready():
    global tasks_registered
n    if not tasks_registered:
        update_timers.start()
        send_reminders.start()
        tasks_registered = True
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Ping management only in slot channels
    if message.channel.id in slots:
        data = slots[message.channel.id]
        today = date.today()
        if data['last_ping_reset'] != today:
            data['pings'] = 0
            data['last_ping_reset'] = today
        # everyone ping
        if message.mention_everyone and "@everyone" in message.content:
            await revoke_slot(message.channel, "Used @everyone ping ❌")
            return
        # here ping
        if message.mention_everyone and "@here" in message.content:
            data['pings'] += 1
            if data['pings'] > 2:
                await revoke_slot(message.channel, "Exceeded @here pings ⚠️")
            else:
                if data['pings'] == 2:
                    await message.author.send(embed=Embed(
                        color=discord.Color.orange(),
                        description="⚠️ You have reached your 2/2 daily @here pings. Don't ping again today."
                    ))
            return
    await bot.process_commands(message)

# Commands

@bot.command(aliases=['help', 'h'])
async def help(ctx):
    em = Embed(color=discord.Color.teal(), title="📖 Bot Commands")
    em.add_field(name=",create", value="Create a slot: follow prompts.", inline=False)
    em.add_field(name=",revoke", value="Revoke a slot (admin only).", inline=False)
    em.add_field(name=",transfer", value="Transfer your slot to another user.", inline=False)
    em.add_field(name=",Aslot", value="Recover your slot using a key.", inline=False)
    await ctx.send(embed=em)

@bot.command()
@commands.has_any_role(ADMIN_ROLE_ID)
async def create(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    await ctx.send("🔍 Please mention slot owner (username or ID):")
    owner_msg = await bot.wait_for('message', check=check, timeout=60)
    try:
        owner_id = int(owner_msg.content.strip('<@!>'))
    except:
        member = discord.utils.get(ctx.guild.members, name=owner_msg.content)
        owner_id = member.id if member else None
    if not owner_id:
        return await ctx.send("❌ Could not find that user.")
    if any(d['owner_id'] == owner_id for d in slots.values()):
        return await ctx.send("⚠️ That user already has a slot.")
    owner = ctx.guild.get_member(owner_id)
    await ctx.send("⏰ Enter slot duration (e.g. 1h, 1d, 1m):")
    dur_msg = await bot.wait_for('message', check=check, timeout=60)
    try:
        delta = parse_duration(dur_msg.content)
    except:
        return await ctx.send("❌ Invalid duration format.")
    expiration = datetime.utcnow() + delta
    await ctx.send("✏️ Enter slot name:")
    name_msg = await bot.wait_for('message', check=check, timeout=60)
    slot_name = name_msg.content
    # Create channel
    category = discord.utils.get(ctx.guild.categories, id=CATEGORY_ID)
    overwrites = {
        ctx.guild.default_role: Permissions(view_channel=True, send_messages=False, mention_everyone=False),
        owner: Permissions(view_channel=True, send_messages=True, mention_everyone=True),
        ctx.guild.get_role(ADMIN_ROLE_ID): Permissions(view_channel=True, send_messages=True, manage_channels=True, mention_everyone=True)
    }
    for aid in ADMIN_IDS:
        member = ctx.guild.get_member(aid)
        if member:
            overwrites[member] = Permissions(view_channel=True, send_messages=True, mention_everyone=True)
    channel = await ctx.guild.create_text_channel(slot_name, category=category, overwrites=overwrites)
    # Generate key
    data = {'channel_name': slot_name, 'owner_id': owner_id, 'expiration': expiration.isoformat()}
    key = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    # Record slot
    slots[channel.id] = {
        'owner_id': owner_id,
        'expiration': expiration,
        'key': key,
        'timer_msg_id': None,
        'last_reminder': None,
        'pings': 0,
        'last_ping_reset': date.today(),
        'channel_name': slot_name
    }
    # Acknowledge creation
    em = Embed(color=discord.Color.red(), title="✅ Slot Created")
    em.add_field(name="Channel", value=channel.mention, inline=True)
    em.add_field(name="Owner", value=owner.mention, inline=True)
    em.add_field(name="Duration", value=dur_msg.content, inline=True)
    em.set_footer(text=f"Created by Luxury Mart • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    await ctx.send(embed=em)
    # DM owner
    dm = Embed(color=discord.Color.green(), title="🔑 Slot Key")
    dm.description = f"Your slot **{slot_name}** is created! Save this key to regain access later:\n```
{key}
```"
    await owner.send(embed=dm)
    # Send rules and timer in channel
    rules = ("• No @everyone pings — will revoke slot instantly.\n"
             "• Max 2 @here pings per day.\n"
             "• 3rd @here ping will revoke the slot.\n"
             "• Only slot owner and staff can send messages here.\n"
             "• Slots auto-delete after expiry.\n"
             "• Be respectful and follow server rules.")
    info = Embed(color=discord.Color.blurple(), title="📋 Slot Rules & Info")
    info.add_field(name="Rules", value=rules, inline=False)
    info.add_field(name="Owner", value=owner.mention, inline=True)
    info.add_field(name="UserID", value=str(owner_id), inline=True)
    info.add_field(name="Duration", value=dur_msg.content, inline=True)
    info.add_field(name="Revoke", value=",revoke", inline=True)
    msg = await channel.send(embed=info)
    timer = Embed(color=discord.Color.blue(), title="⏳ Time Remaining")
    remaining = expiration - datetime.utcnow()
    days, rem = remaining.days, remaining.seconds
    hrs, mins = divmod(rem, 3600)[0], divmod(rem, 60)[0]
    timer.description = f"**{days}d:{hrs}h:{mins}m**"
    timer_msg = await channel.send(embed=timer)
    slots[channel.id]['timer_msg_id'] = timer_msg.id

@bot.command()
@commands.has_any_role(ADMIN_ROLE_ID)
async def revoke(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    await ctx.send("🔍 Enter channel ID to revoke:")
    ch_msg = await bot.wait_for('message', check=check, timeout=60)
    try:
        cid = int(ch_msg.content)
    except:
        return await ctx.send("❌ Invalid channel ID.")
    channel = ctx.guild.get_channel(cid)
    if not channel or cid not in slots:
        return await ctx.send("⚠️ That channel is not a slot.")
    await ctx.send("✏️ Reason for revoking:")
    reason_msg = await bot.wait_for('message', check=check, timeout=60)
    await revoke_slot(channel, reason_msg.content)
    await ctx.send(embed=Embed(color=discord.Color.green(), description="✅ Slot revoked."))

@bot.command()
async def transfer(ctx):
    owner_slots = [cid for cid,data in slots.items() if data['owner_id']==ctx.author.id]
    if not owner_slots:
        return await ctx.send("⚠️ You don't own any slot.")
    if len(owner_slots)>1:
        return await ctx.send("⚠️ You own multiple slots; cannot transfer.")
    ch_id = owner_slots[0]
    channel = ctx.guild.get_channel(ch_id)
    def check(m): return m.author==ctx.author and m.channel==ctx.channel
    await ctx.send("🔍 Mention new owner (username or ID):")
    new_msg = await bot.wait_for('message', check=check, timeout=60)
    try:
        new_id = int(new_msg.content.strip('<@!>'))
    except:
        member = discord.utils.get(ctx.guild.members, name=new_msg.content)
        new_id = member.id if member else None
    if not new_id:
        return await ctx.send("❌ Could not find that user.")
    new_owner = ctx.guild.get_member(new_id)
    data = slots[ch_id]
    old_owner = ctx.guild.get_member(data['owner_id'])
    # update perms
    await channel.set_permissions(old_owner, overwrite=Permissions(view_channel=True, send_messages=False, mention_everyone=False))
    await channel.set_permissions(new_owner, overwrite=Permissions(view_channel=True, send_messages=True, mention_everyone=True))
    slots[ch_id]['owner_id'] = new_id
    await ctx.send(embed=Embed(color=discord.Color.green(), description=f"✅ Slot successfully transferred to {new_owner.mention}."))

@bot.command(name='Aslot')
async def access_slot(ctx):
    def check(m): return m.author==ctx.author and isinstance(m.channel, discord.DMChannel)
    await ctx.author.send("🔐 Please enter your slot key:")
    key_msg = await bot.wait_for('message', check=check, timeout=120)
    key = key_msg.content.strip()
    try:
        data = json.loads(base64.urlsafe_b64decode(key.encode()).decode())
        exp = datetime.fromisoformat(data['expiration'])
    except:
        return await ctx.author.send(embed=Embed(color=discord.Color.red(), description="❌ Invalid key."))
    if datetime.utcnow() >= exp:
        return await ctx.author.send(embed=Embed(color=discord.Color.red(), description="❌ That slot has expired."))
    if data['owner_id'] != ctx.author.id:
        return await ctx.author.send(embed=Embed(color=discord.Color.red(), description="❌ You are not the owner of this slot."))
    # recreate channel if missing
    guild = bot.guilds[0]
    existing = discord.utils.get(guild.text_channels, name=data['channel_name'])
    if existing:
        return await ctx.author.send(embed=Embed(color=discord.Color.orange(), description="⚠️ Your slot channel already exists."))
    category = discord.utils.get(guild.categories, id=CATEGORY_ID)
    overwrites = {
        guild.default_role: Permissions(view_channel=True, send_messages=False, mention_everyone=False),
        ctx.author: Permissions(view_channel=True, send_messages=True, mention_everyone=True),
        guild.get_role(ADMIN_ROLE_ID): Permissions(view_channel=True, send_messages=True, manage_channels=True, mention_everyone=True)
    }
    for aid in ADMIN_IDS:
        member = guild.get_member(aid)
        if member:
            overwrites[member] = Permissions(view_channel=True, send_messages=True, mention_everyone=True)
    channel = await guild.create_text_channel(data['channel_name'], category=category, overwrites=overwrites)
    # restore slot
    slots[channel.id] = {
        'owner_id': ctx.author.id,
        'expiration': exp,
        'key': key,
        'timer_msg_id': None,
        'last_reminder': None,
        'pings': 0,
        'last_ping_reset': date.today(),
        'channel_name': data['channel_name']
    }
    # send rules/info/timer
    rules = ("• No @everyone pings — will revoke slot instantly.\n"
             "• Max 2 @here pings per day.\n"
             "• 3rd @here ping will revoke the slot.\n"
             "• Only slot owner and staff can send messages here.\n"
             "• Slots auto-delete after expiry.\n"
             "• Be respectful and follow server rules.")
    info = Embed(color=discord.Color.blurple(), title="📋 Slot Rules & Info")
    info.add_field(name="Rules", value=rules, inline=False)
    info.add_field(name="Owner", value=ctx.author.mention, inline=True)
    info.add_field(name="UserID", value=str(ctx.author.id), inline=True)
    info.add_field(name="Duration", value="N/A (restored)", inline=True)
    info.add_field(name="Revoke", value=",revoke", inline=True)
    msg = await channel.send(embed=info)
    timer = Embed(color=discord.Color.blue(), title="⏳ Time Remaining")
    rem = exp - datetime.utcnow()
    d, r = rem.days, rem.seconds
    h, m = divmod(r, 3600)[0], divmod(r, 60)[0]
    timer.description = f"**{d}d:{h}h:{m}m**"
    timer_msg = await channel.send(embed=timer)
    slots[channel.id]['timer_msg_id'] = timer_msg.id
    await ctx.author.send(embed=Embed(color=discord.Color.green(), description=f"✅ Slot channel {channel.mention} restored."))

# Run the bot
bot.run('YOUR_BOT_TOKEN')
            
