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
from datetime import datetime, timezone, timedelta

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

# Function to change the channel name based on PYAM status
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


# Function to calculae future schedule of PYAM availabity
def get_pyam_schedule(days: int):

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)

    now_ms = now.timestamp() * 1000
    end_ms = end.timestamp() * 1000

    cycle_index = math.floor(
        (now_ms - INITIAL_OPEN_TIME.timestamp() * 1000)
        / CYCLE_DURATION_MS
    )

    cycle_start = (
        INITIAL_OPEN_TIME.timestamp() * 1000
        + cycle_index * CYCLE_DURATION_MS
    )

    intervals = []

    while cycle_start < end_ms:

        online_start = cycle_start
        offline_start = online_start + OPEN_DURATION_MS
        next_cycle = cycle_start + CYCLE_DURATION_MS

        periods = [
            ("ONLINE", online_start, offline_start),
            ("OFFLINE", offline_start, next_cycle)
        ]

        for status, start, finish in periods:

            if finish <= now_ms or start >= end_ms:
                continue

            intervals.append({
                "status": status,
                "start": datetime.fromtimestamp(
                    start / 1000, timezone.utc
                ),
                "end": datetime.fromtimestamp(
                    finish / 1000, timezone.utc
                ),
                "ongoing": start <= now_ms < finish
            })

        cycle_start = next_cycle

    return intervals


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# Update the channel status every 15 seconds
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


# Function to create an embed for the schedule command
def create_schedule_embed(intervals, days, page):

    per_page = 20
    total_pages = max(1, math.ceil(len(intervals) / per_page))

    start_index = page * per_page
    page_intervals = intervals[start_index:start_index + per_page]

    embed = discord.Embed(
        title="PYAM Hangar Schedule",
        description=(
            f"Next **{days} days** | "
            f"Page {page + 1}/{total_pages}\n"
            "Times are displayed in your local Discord timezone."
        ),
        color=discord.Color.blurple()
    )

    for period in page_intervals:

        status = period["status"]

        if status == "ONLINE":
            emoji = "🟩"
        else:
            emoji = "🟥"

        start = int(period["start"].timestamp())
        finish = int(period["end"].timestamp())

        if period["ongoing"]:
            value = (
                f"Started: <t:{start}:F>\n"
                f"Ends: <t:{finish}:F> (<t:{finish}:R>)"
            )
        else:
            value = (
                f"Starts: <t:{start}:F>\n"
                f"Ends: <t:{finish}:F> (<t:{finish}:R>)"
            )

        embed.add_field(
            name=f"{emoji} {status}",
            value=value,
            inline=False
        )

    return embed

# View class for the schedule command with pagination
class ScheduleView(discord.ui.View):

    def __init__(self, intervals, days, owner_id):
        super().__init__(timeout=180)

        self.intervals = intervals
        self.days = days
        self.owner_id = owner_id
        self.page = 0

        self.total_pages = max(
            1, math.ceil(len(intervals) / 20)
        )

        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.total_pages - 1

    async def interaction_check(self, interaction):

        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the user who requested this schedule can navigate it.",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary
    )
    async def previous(self, interaction, button):

        self.page -= 1
        self.update_buttons()

        embed = create_schedule_embed(
            self.intervals, self.days, self.page
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.secondary
    )
    async def next(self, interaction, button):

        self.page += 1
        self.update_buttons()

        embed = create_schedule_embed(
            self.intervals, self.days, self.page
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )


@bot.tree.command(
    name="pyam_schedule",
    description="Show the future PYAM online/offline schedule."
)
@app_commands.describe(
    days="Number of days to display (1-14). Default: 3."
)
@app_commands.checks.cooldown(1, 10.0)
async def pyam_schedule(
    interaction: discord.Interaction,
    days: app_commands.Range[int, 1, 14] = 3
):

    intervals = get_pyam_schedule(days)

    embed = create_schedule_embed(intervals, days, 0)

    view = ScheduleView(
        intervals,
        days,
        interaction.user.id
    )

    await interaction.response.send_message(
        embed=embed,
        view=view
    )


@pyam_schedule.error
async def pyam_schedule_error(interaction, error):

    if isinstance(error, app_commands.CommandOnCooldown):
        message = (
            f"Wait {error.retry_after:.1f} seconds "
            "before using this command again."
        )
    else:
        print(f"Schedule command error: {error}")
        message = "Could not generate the PYAM schedule."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True
        )


@pyam_status_updater.before_loop
async def before_pyam_update():
    await bot.wait_until_ready()



# Check bot online 
@bot.event
async def on_ready():

    print(f"{bot.user.name} Ready To Online!")

    activity = discord.Streaming(
        name="PYAM Hangar Status",
        url="https://exec.xyxyll.com/"
    )

    await bot.change_presence(activity=activity)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except discord.HTTPException as error:
        print(f"Command sync failed: {error}")

    if not pyam_status_updater.is_running():
        pyam_status_updater.start()



bot.run(TOKEN)







