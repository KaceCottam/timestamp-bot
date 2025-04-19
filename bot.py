import discord
from discord import Embed, app_commands, Interaction
from parsedatetime import Calendar, VERSION_CONTEXT_STYLE, pdtContext
import pytz
import sqlite3
import os
import dotenv
from datetime import datetime, timedelta

# Load environment variables
dotenv.load_dotenv()

# Initialize Discord client
client = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(client)

# Initialize database
conn = sqlite3.connect('timezones.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS user_timezones
             (user_id INTEGER PRIMARY KEY, timezone TEXT DEFAULT 'US/Pacific')''')
conn.commit()

def get_user_timezone(user_id):
    c.execute("SELECT timezone FROM user_timezones WHERE user_id=?", (user_id,))
    result = c.fetchone()
    return result[0] if result else 'US/Pacific'

def set_user_timezone(user_id, timezone):
    c.execute("INSERT OR REPLACE INTO user_timezones (user_id, timezone) VALUES (?, ?)",
              (user_id, timezone))
    conn.commit()

# let us make a "set timezone" command
@tree.command(name="set_timezone", description="Set your timezone")
@app_commands.describe(timezone="Your timezone")
@app_commands.choices(timezone=[
    discord.app_commands.Choice(name=s, value=s) for s in ["US/Pacific", "US/Eastern", "US/Central", "US/Mountain"]
])
async def set_user_timezone_command(ctx: Interaction, timezone: str):
    # Set the user's timezone
    set_user_timezone(ctx.user.id, timezone)
    embed = Embed(title="Timezone Set", color=0x00FF00)
    embed.description = f"Your timezone has been set to '{timezone}'."
    await ctx.response.send_message(embed=embed, ephemeral=True)

def to_timestamp(dt: datetime, flag: pdtContext, adjust_timedelta: bool) -> str:
    """
    formatting mark will be this, depending on accuracy:
    f (date and time)
    d (date)
    t (hour and min)
    R (only hour)
    R (only minute)
    R (only second)
    """
    format_mark = 'f' # by default
    if flag.accuracy & pdtContext().ACU_DATE and flag.accuracy & pdtContext().ACU_TIME:
        format_mark = 'f'
    elif flag.accuracy & pdtContext().ACU_DATE:
        format_mark = 'd'
    elif flag.accuracy & pdtContext().ACU_HOUR and flag.accuracy & pdtContext().ACU_MIN:
        if adjust_timedelta and dt < datetime.now(dt.tzinfo):
            dt = dt + timedelta(hours=12)
        format_mark = 't'
    elif flag.accuracy & pdtContext().ACU_HOUR:
        format_mark = 'R'
    elif flag.accuracy & pdtContext().ACU_MIN:
        format_mark = 'R'
    elif flag.accuracy & pdtContext().ACU_SEC:
        format_mark = 'R'
    
    linux_time = int(dt.timestamp())

    return f"<t:{linux_time}:{format_mark}>"

def parse_string(message: str, cal: Calendar, tz: pytz.timezone) -> str:
    """
    Parse the string, replace times and dates with Discord timestamps, and handle timezones.
    """
    result = cal.nlp(message, sourceTime=datetime.now(tz=tz), version=VERSION_CONTEXT_STYLE)
    if not result:
        return message

    result: list[tuple[datetime, pdtContext, int, int, str, str | None]] = [*result]
    # Update the result with timezone adjustments
    new_result = []
    for dt, flag, offset_start, offset_end, matched_text in result:
        words = message[offset_end:].split()
        words.append('')  # Avoid index out of range
        if words[0].upper() in TIMEZONE_MAP:
            tz = pytz.timezone(TIMEZONE_MAP[words[0].upper()])
            offset_end += len(words[0]) + 1
            matched_text = matched_text + " " + words[0]
            dt = tz.localize(dt)
            new_result.append((dt, flag, offset_start, offset_end, matched_text, TIMEZONE_MAP[words[0].upper()]))
        else:
            new_result.append((dt, flag, offset_start, offset_end, matched_text, None))
    
    result = new_result

    new_result = []

    # because of the above, we may be able to join some of the results together
    combined_previous = False
    for result1, result2 in zip(result, result[1:]):
        dt1, flag1, offset_start1, offset_end1, _, override_timezone1 = result1
        dt2, flag2, offset_start2, offset_end2, _, override_timezone2 = result2
        if not message[offset_end1:offset_start2].isspace() and not (override_timezone1 and override_timezone2):
            # skip if the flags are the same
            # skip if there is text in between the words
            new_result.append(result1)
            combined_previous = False
            continue 
        combined_previous = True
        dt_time = dt1.time() if flag1.ACU_HOUR else dt2.time()
        dt_date = dt2.date() if flag1.ACU_HOUR else dt1.date()
        dt = datetime.combine(date=dt_date, time=dt_time, tzinfo=dt1.tzinfo or dt2.tzinfo)
        if override_timezone1 or override_timezone2:
            dt = dt.replace(tzinfo=dt1.tzinfo if override_timezone1 else dt2.tzinfo)
        flag = pdtContext(flag1.accuracy | flag2.accuracy)
        offset_start = offset_start1
        offset_end = offset_end2
        matched_text = message[offset_start:offset_end]
        new_result.append((dt, flag, offset_start, offset_end, matched_text, override_timezone1 or override_timezone2))
    
    if not combined_previous:
        # if the last result was not combined, add it to the new result
        new_result.append(result[-1])

    result = new_result
           
    # Adjust datetime objects to the user's timezone
    for i, (dt, *_) in enumerate(result):
        dt = tz.localize(dt) if dt.tzinfo is None else dt.astimezone(tz)
        result[i] = (dt.astimezone(BOT_TIMEZONE), *result[i][1:])

    # Construct the string to send
    accumulator: str = ""
    last_offset = 0
    for (dt, flag, offset_start, offset_end, matched_text, _) in result:
        accumulator += message[last_offset:offset_start]
        last_offset = offset_end
        timestamp_str = to_timestamp(dt, flag, 'am' not in matched_text.lower() and 'pm' not in matched_text.lower())
        prefix = matched_text[:len(matched_text) - len(matched_text.lstrip())]
        suffix = matched_text[len(matched_text.rstrip()):]
        accumulator += prefix + timestamp_str + suffix
    accumulator += message[last_offset:]
    return accumulator

BOT_TIMEZONE = pytz.timezone("US/Pacific")

TIMEZONE_MAP = {
    "EST": "US/Eastern",
    "CST": "US/Central",
    "MST": "US/Mountain",
    "PST": "US/Pacific"
}

@tree.command(name="timestamp", description="Send a message and replace times and dates with a discord timestamp.")
@app_commands.describe(message="Message to parse")
async def timestamp(ctx: Interaction, message: str):
    await ctx.response.defer(ephemeral=False)  # Make the response non-ephemeral
    cal = Calendar(version=VERSION_CONTEXT_STYLE)
    user_tz = get_user_timezone(ctx.user.id)
    tz = pytz.timezone(user_tz)
    
    # Use parse_string to process the message
    parsed_message = parse_string(message, cal, tz)
    
    # Respond with an embed
    try:
        embed = Embed(description=parsed_message, color=0x00FF00)
        embed.set_author(name=ctx.user.display_name, icon_url=ctx.user.display_avatar.url)
        embed.set_footer(text=f"User's timezone: {user_tz}")
        await ctx.followup.send(embed=embed, ephemeral=False)
    except Exception as e:
        await ctx.followup.send(
            content=f"Failed to send the message: {str(e)}",
            ephemeral=True
        )

@tree.context_menu(name="Send Timestamp")
async def send_timestamp(ctx: Interaction, message: discord.Message):
    await ctx.response.defer(ephemeral=False)  # Make the response non-ephemeral
    cal = Calendar(version=VERSION_CONTEXT_STYLE)
    sender_tz = get_user_timezone(message.author.id)  # Get the sender's timezone
    tz = pytz.timezone(sender_tz)
    
    # Use parse_string to process the message content
    parsed_message = parse_string(message.content, cal, tz)
    
    # Respond with an embed
    try:
        embed = Embed(description=parsed_message, color=0x00FF00)
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.set_footer(text=f"Sender's timezone: {sender_tz}")
        await ctx.followup.send(embed=embed, ephemeral=False)
    except Exception as e:
        await ctx.followup.send(
            content=f"Failed to send the message: {str(e)}",
            ephemeral=True
        )

@tree.command(name="sync", description="Owner only", guild=discord.Object(id=883091779535126529))
@app_commands.describe(guild="Sync commands in this guild")
async def sync(ctx: Interaction, guild: str | None = None):
    await ctx.response.defer()
    if ctx.user.id != 97821722517962752:
        embed = Embed(title="Permission Denied", color=0xFF0000)
        embed.description = "You do not have permission to use this command."
        await ctx.followup.send(embed=embed, ephemeral=True)
        return
    if guild is not None:
        # Sync commands in this guild
        synced_commands = await tree.sync(guild=discord.Object(id=int(guild)))
    else:
        synced_commands = await tree.sync()
    embed = Embed(title="Sync", color=0x00FF00)
    embed.description = "Command tree synced successfully!"
    embed.add_field(name="Synced Commands", value="\n".join([f"/{command.name}" for command in synced_commands]), inline=False)
    await ctx.followup.send(embed=embed, ephemeral=True)

@client.event
async def on_ready():
    # Sync the command tree when the bot is ready
    print("ready")


secret = os.getenv("BOT_SECRET")
if not secret:
    raise ValueError("BOT_SECRET environment variable not set in .env!")

client.run(secret)

