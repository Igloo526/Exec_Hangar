import discord
import asyncio
import os
from discord.ext import commands
from discord import app_commands
from discord import Embed
from discord.ext import commands, tasks
from typing import Optional
from json import loads
from dotenv import load_dotenv
import math
from datetime import datetime, timezone

load_dotenv()
Role_Auth = int(os.getenv("ROLE_Auth"))
TOKEN = os.getenv("Discord_Token_Key")
CHANGE_NAME_CHANNEL_ID = os.getenv("Change_Name_CH_ID")
PYAM_STATUS_CHANNEL_ID = int(os.getenv("PYAM_STATUS_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.voice_states = True
intents.message_content = True
intents.members = True


CYCLE_DRIFT_MS = 295

DESIGN_ONLINE_MIN = 65
DESIGN_OFFLINE_MIN = 120

DESIGN_CYCLE_MIN = DESIGN_ONLINE_MIN + DESIGN_OFFLINE_MIN

DESIGN_ONLINE_MS = DESIGN_ONLINE_MIN * 60 * 1000

CYCLE_DURATION_MS = DESIGN_CYCLE_MIN * 60 * 1000 + CYCLE_DRIFT_MS

# Match JavaScript Math.round()
OPEN_DURATION_MS = math.floor(
    CYCLE_DURATION_MS * DESIGN_ONLINE_MS /
    (DESIGN_CYCLE_MIN * 60 * 1000) + 0.5
)

CLOSE_DURATION_MS = CYCLE_DURATION_MS - OPEN_DURATION_MS

# Original timestamp from app.js
INITIAL_OPEN_TIME = datetime.fromisoformat(
    "2026-11-12T15:01:40.977-04:00"
)


def get_pyam_channel_name():

    now = datetime.now(timezone.utc)

    elapsed_ms = (
        now.timestamp() - INITIAL_OPEN_TIME.timestamp()
    ) * 1000

    time_in_cycle = elapsed_ms % CYCLE_DURATION_MS

    # Online phase
    if time_in_cycle < OPEN_DURATION_MS:

        progress = time_in_cycle / OPEN_DURATION_MS

        thresholds = [
            (12 / 65, "🟩🟩🟩🟩🟩"),
            (24 / 65, "🟩🟩🟩🟩⬜"),
            (36 / 65, "🟩🟩🟩⬜⬜"),
            (48 / 65, "🟩🟩⬜⬜⬜"),
            (60 / 65, "🟩⬜⬜⬜⬜"),
            (1.0,     "⬜⬜⬜⬜⬜"),
        ]

    # Offline phase
    else:

        progress = (
            time_in_cycle - OPEN_DURATION_MS
        ) / CLOSE_DURATION_MS

        thresholds = [
            (1 / 5, "🟥🟥🟥🟥🟥"),
            (2 / 5, "🟩🟥🟥🟥🟥"),
            (3 / 5, "🟩🟩🟥🟥🟥"),
            (4 / 5, "🟩🟩🟩🟥🟥"),
            (1.0,   "🟩🟩🟩🟩🟥"),
        ]

    for threshold, lights in thresholds:

        if progress < threshold:
            return f"✈️-{lights}"

    return f"✈️-⬜⬜⬜⬜⬜"



bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


#update the channel status every 15 seconds
@tasks.loop(seconds=15)
async def pyam_status_updater():

    if PYAM_STATUS_CHANNEL_ID == 0:
        return

    channel_name = get_pyam_channel_name()

    channel = bot.get_channel(PYAM_STATUS_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(
                PYAM_STATUS_CHANNEL_ID
            )
        except discord.HTTPException as error:
            print(f"Could not fetch channel: {error}")
            return

    if channel.name != channel_name:

        try:
            await channel.edit(
                name=channel_name,
                reason="PYAM hangar status update"
            )

            print(f"Channel updated: {channel_name}")

        except discord.Forbidden:
            print("Missing Manage Channels permission.")

        except discord.HTTPException as error:
            print(f"Channel update failed: {error}")


@pyam_status_updater.before_loop
async def before_pyam_update():
    await bot.wait_until_ready()



#check bot online 
@bot.event
async def on_ready():

    print(f"{bot.user.name} Ready To Online!")

    activity = discord.Streaming(
        name="PYAM Hangar Status",
        url="https://exec.xyxyll.com/"
    )

    await bot.change_presence(activity=activity)

    if not pyam_status_updater.is_running():
        pyam_status_updater.start()



bot.run(TOKEN)







