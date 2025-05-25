import discord
from discord.ext import commands
from discord import Embed
import random
import asyncio
from datetime import datetime, timedelta

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=',', intents=intents)

# Admin IDs and Role ID
ADMIN_ROLE_ID = 1375747962487181342
ADMIN_IDS = [993153549095673936, 1241446608424407052, 1083998643322892401, 981093886351003709]
CATEGORY_ID = 1375748081735172126

# Slot data storage
slots = {}

# Helper function to create embeds
def create_embed(title, description, color=0x3498db, fields=None, footer=None):
    embed = Embed(title=title, description=description, color=color)
    if fields:
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
    if footer:
        embed.set_footer(text=footer)
    return embed

# Help command
@bot.command(name='help')
async def help(ctx):
    embed = create_embed(
        title="Bot Commands", 
        description="Here are the available commands:", 
        color=0x3498db, 
        fields=[
            (",create", "Create a new slot"), 
            (",revoke", "Revoke an existing slot"), 
            (",transfer", "Transfer slot ownership"), 
            (",Aslot", "Access a slot with key")
        ]
    )
    await ctx.send(embed=embed)

# Slot creation
@bot.command(name='create')
async def create(ctx):
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send(embed=create_embed("Error", "You don't have permission to create slots.", color=0xff0000))
        return

    # Step 1: Ask for owner username/id
    await ctx.send(embed=create_embed("Step 1", "Please enter the slot owner username or ID:"))
    def check(msg):
        return msg.author == ctx.author
    owner_msg = await bot.wait_for('message', check=check)

    # Step 2: Ask for slot duration
    await ctx.send(embed=create_embed("Step 2", "Enter the slot duration (e.g., 1h, 1d, 1m):"))
    duration_msg = await bot.wait_for('message', check=check)
    duration = duration_msg.content.lower()

    # Step 3: Ask for slot name
    await ctx.send(embed=create_embed("Step 3", "Enter the slot name:"))
    name_msg = await bot.wait_for('message', check=check)
    slot_name = name_msg.content

    # Create the channel
    category = discord.utils.get(ctx.guild.categories, id=CATEGORY_ID)
    channel = await ctx.guild.create_text_channel(slot_name, category=category)

    # Assign permissions to the owner
    member = await ctx.guild.fetch_member(int(owner_msg.content))
    await channel.set_permissions(member, send_messages=True, mention_everyone=False)

    # Generate key (a simple random string for now, could be encoded)
    slot_key = random.randint(1000, 9999)

    # Save slot info
    slots[channel.id] = {
        'owner_id': member.id,
        'duration': duration,
        'key': slot_key,
        'expiration': datetime.now() + timedelta(days=30) if duration == '1m' else datetime.now() + timedelta(days=1),  # Example: 1 month expiration
        'pings': 0
    }

    # Embed response with slot details
    embed = create_embed(
        title="Slot Created", 
        description=f"Slot created successfully: #{slot_name}", 
        color=0xFF5733, 
        fields=[
            ("Channel:", f"#{slot_name}"),
            ("Owner:", member.mention),
            ("Duration:", duration),
            ("Created By:", "Luxury Mart"),
            ("Creation Time:", f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        ],
        footer="Luxury Mart"
    )
    await ctx.send(embed=embed)

    # DM the slot owner with the key
    dm_channel = await member.create_dm()
    await dm_channel.send(f"Your slot has been created! Keep this key safe: `{slot_key}` to access your slot.")

# Revoke command
@bot.command(name='revoke')
async def revoke(ctx):
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send(embed=create_embed("Error", "You don't have permission to revoke slots.", color=0xff0000))
        return

    # Ask for channel ID
    await ctx.send(embed=create_embed("Step 1", "Enter the channel ID to revoke:"))
    def check(msg):
        return msg.author == ctx.author
    channel_msg = await bot.wait_for('message', check=check)
    channel_id = int(channel_msg.content)

    # Ask for reason
    await ctx.send(embed=create_embed("Step 2", "Enter the reason for revoking:"))
    reason_msg = await bot.wait_for('message', check=check)
    reason = reason_msg.content

    # Delete the channel and notify the owner
    channel = await ctx.guild.fetch_channel(channel_id)
    owner_id = slots[channel.id]['owner_id']
    owner = await ctx.guild.fetch_member(owner_id)

    # DM the owner
    dm_channel = await owner.create_dm()
    await dm_channel.send(f"Your slot has been revoked. Reason: {reason}. Please contact any admin.")

    # Delete the channel
    await channel.delete()

    # Remove from slots data
    del slots[channel.id]

# Transfer command
@bot.command(name='transfer')
async def transfer(ctx):
    # Check if user owns a slot
    for channel_id, slot in slots.items():
        if slot['owner_id'] == ctx.author.id:
            # Ask for new owner's username
            await ctx.send(embed=create_embed("Step 1", "Enter the username of the new owner:"))
            def check(msg):
                return msg.author == ctx.author
            new_owner_msg = await bot.wait_for('message', check=check)
            new_owner_id = int(new_owner_msg.content)

            # Fetch new owner and transfer permissions
            new_owner = await ctx.guild.fetch_member(new_owner_id)
            channel = await ctx.guild.fetch_channel(channel_id)

            # Transfer permissions
            await channel.set_permissions(ctx.author, send_messages=False)
            await channel.set_permissions(new_owner, send_messages=True)

            # Update slot owner
            slots[channel_id]['owner_id'] = new_owner_id
            await ctx.send(embed=create_embed("Slot Transferred", f"Slot successfully transferred to {new_owner.mention}.", color=0x3498db))
            return

    await ctx.send(embed=create_embed("Error", "You don't own a slot.", color=0xff0000))

# Access slot command (Aslot)
@bot.command(name='Aslot')
async def Aslot(ctx):
    await ctx.send(embed=create_embed("Step 1", "Enter the slot key:"))
    def check(msg):
        return msg.author == ctx.author
    key_msg = await bot.wait_for('message', check=check)
    key = int(key_msg.content)

    for channel_id, slot in slots.items():
        if slot['key'] == key and slot['expiration'] > datetime.now():
            # Give access to the channel
            channel = await ctx.guild.fetch_channel(channel_id)
            await channel.set_permissions(ctx.author, send_messages=True)
            await ctx.send(embed=create_embed("Access Granted", f"Slot {channel.name} is now accessible.", color=0x2ecc71))
            return

    await ctx.send(embed=create_embed("Error", "Invalid or expired slot key.", color=0xff0000))

# Ping management
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Slot pings limit check
    if message.mention_everyone:
        if "@everyone" in message.content:
            channel = message.channel
            if channel.id in slots:
                slot = slots[channel.id]
                # Delete @everyone ping
                await message.delete()
                # Revoke slot and DM owner
                owner = await message.guild.fetch_member(slot['owner_id'])
                dm_channel = await owner.create_dm()
                await dm_channel.send("Your slot has been revoked due to an illegal @everyone ping.")
                await channel.delete()
                del slots[channel.id]
                return

        if "@here" in message.content:
            channel = message.channel
            if channel.id in slots:
                slot = slots[channel.id]
                if slot['pings'] >= 2:
                    await message.delete()
                    owner = await message.guild.fetch_member(slot['owner_id'])
                    dm_channel = await owner.create_dm()
                    await dm_channel.send(f"Your slot has been revoked due to excessive pings.")
                    await channel.delete()
                    del slots[channel.id]
                    return
                else:
                    slot['pings'] += 1
                    await message.delete()

    await bot.process_commands(message)

# Run the bot
bot.run('YOUR_BOT_TOKEN')
    
