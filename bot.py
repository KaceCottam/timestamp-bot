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

def construct_string(message: str, nlp_result: list[tuple[datetime, int, int, int, str]]) -> str:
    # Construct the string to send
    accumulator: str = ""
    last_offset = 0
    if not nlp_result:
        return message
    
    last_flag = None
    for (dt, flag, offset_start, offset_end, matched_text) in nlp_result:
        accumulator += message[last_offset:offset_start]
        last_offset = offset_end
        # convert the datetime to a timestamp string
        timestamp_str = to_timestamp(dt, flag, 'am' not in matched_text.lower() and 'pm' not in matched_text.lower())
        # sometimes the matched text grabs extra whitespace characters on the ends
        # so we need to keep those whitespace characters
        prefix = matched_text[:len(matched_text) - len(matched_text.lstrip())]
        suffix = matched_text[len(matched_text.rstrip()):]

        accumulator += prefix + timestamp_str + suffix
    accumulator += message[last_offset:]
    return accumulator

# now let us have a command `timestamp` that takes a message.
# it uses parsedatetime.Calendar.nlp to parse the message.
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
    # we will parse the message using parsedatetime.Calendar.nlp
    embed = Embed()
    embed.set_author(name=ctx.user.display_name, icon_url=ctx.user.avatar.url)
    embed.set_footer(text=f"Timezone: {get_user_timezone(ctx.user.id)}")
    cal = Calendar(version=VERSION_CONTEXT_STYLE)
    user_tz = get_user_timezone(ctx.user.id)
    tz = pytz.timezone(user_tz)
    result: list[tuple[datetime, int, int, int, str]] = [*cal.nlp(message, sourceTime=datetime.now(tz=tz), version=VERSION_CONTEXT_STYLE)]
    # if result is None, we will just write the message. There is no error.
    if result is None:
        embed.description = message
        await ctx.response.send_message(embeds=[embed])
        return
    
    # we need to update the result 
    new_result = []
    for dt, flag, offset_start, offset_end, matched_text in result:
        # we need to check the next word in the message to see if it is a timezone
        # if it is, we need to set the timezone to that timezone
        words = message[offset_end:].split()
        words.append(None) # to avoid index out of range
        if words[0] in TIMEZONE_MAP:
            # set the timezone to that timezone
            tz = pytz.timezone(TIMEZONE_MAP[words[0]])
            # remove the timezone from the message
            offset_end += len(words[0]) + 1
            matched_text = matched_text + " " + words[0]

            dt = tz.localize(dt)
            new_result.append((dt, flag, offset_start, offset_end, matched_text))
        else:
            # if the timezone is not in the message, we will just add the result
            new_result.append((dt, flag, offset_start, offset_end, matched_text))

    result = new_result

    # we will have to adjust the datetime objects to the user's timezone
    for i, (dt, *_) in enumerate(result):
        # convert the datetime to the user's timezone
        dt = tz.localize(dt) if dt.tzinfo is None else dt.astimezone(tz)
        result[i] = (dt.astimezone(BOT_TIMEZONE), *result[i][1:])

    message = construct_string(message, result)
    embed.description = message
    await ctx.response.send_message(embeds=[embed])

@tree.command(name="sync", description="Owner only", guild=discord.Object(id=883091779535126529))
@app_commands.describe(guild="Sync commands in this guild")
async def sync(ctx: Interaction, guild: str | None = None):
    if ctx.user.id != 97821722517962752:
        embed = Embed(title="Permission Denied", color=0xFF0000)
        embed.description = "You do not have permission to use this command."
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return
    # await ctx.response.defer()
    if guild is not None:
        # Sync commands in this guild
        synced_commands = await tree.sync(guild=discord.Object(id=int(guild)))
    else:
        synced_commands = await tree.sync()
    embed = Embed(title="Sync", color=0x00FF00)
    embed.description = "Command tree synced successfully!"
    embed.add_field(name="Synced Commands", value="\n".join([f"/{command.name}" for command in synced_commands]), inline=False)
    await ctx.response.send_message(embed=embed, ephemeral=True)

@client.event
async def on_ready():
    # print "ready" in the console when the bot is ready to work
    print("ready")


secret = os.getenv("BOT_SECRET")
if not secret:
    raise ValueError("BOT_SECRET environment variable not set in .env!")

client.run(secret)

