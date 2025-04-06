import discord
from discord import Embed, app_commands, Interaction
from parsedatetime import Calendar
import pytz
import sqlite3
import os
import dotenv
from datetime import datetime

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

@tree.command(name="timestamp",
              description="Convert human-readable time to timestamp")
@app_commands.describe(
    time_phrase="Human-readable time (e.g. 'in 30 minutes')",
    timezone= "Optional timezone override (saves for future use)",
    timestamp_format="Format of the timestamp (default: 'R' for relative, 't' for short, 'f' for long)"
)
@app_commands.choices(timezone=[
    discord.app_commands.Choice(name="PST", value="US/Pacific"),
    discord.app_commands.Choice(name="CST", value="US/Central"),
    discord.app_commands.Choice(name="EST", value="US/Eastern")
    ],
    timestamp_format=[
        discord.app_commands.Choice(name="Relative (in X minutes)", value="R"),
        discord.app_commands.Choice(name="Short (X:XX am/pm)", value="t"),
        discord.app_commands.Choice(name="Long (Month X, XXXX at XX:XX am/pm)", value="f")
    ]
)
async def _timestamp(ctx: Interaction, time_phrase: str, timezone: str | None = None, timestamp_format: str | None = None):
    # Get or set timezone
    if timezone:
        set_user_timezone(ctx.user.id, timezone)
    user_tz = timezone if timezone else get_user_timezone(ctx.user.id)
    tz = pytz.timezone(user_tz)
    
    # Parse time
    cal = Calendar()
    parsed_date, parse_status = cal.parseDT(datetimeString=time_phrase, sourceTime=datetime.now(tz=tz), tzinfo=tz)
    
    if parse_status == 0:
        # Parsing failed
        embed = Embed(title="Parsing Error", color=0xFF0000)
        embed.description = f"Unable to parse the time phrase: '{time_phrase}'"
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Format response
    unix_timestamp = int(parsed_date.timestamp())

    def pick_formatting_mark(dt):
        now = datetime.now(tz)
        diff = (dt - now).total_seconds()
        if diff <= 3600:
            return 'R'
        elif diff <= 43200:
            return 't'
        else:
            return 'f'

    formatting_mark = pick_formatting_mark(parsed_date) if timestamp_format is None else timestamp_format
        
    response = f"<t:{unix_timestamp}:{formatting_mark}>"
    
    await ctx.response.send_message(response, silent=True)

@tree.command(name="sync", description="Owner only")
@app_commands.check(lambda i: i.user.id == 1358574053945901146)
async def sync(ctx: Interaction):
    await tree.sync()
    embed = Embed(title="Sync", color=0x00FF00)
    embed.description = "Command tree synced successfully!"
    await ctx.response.send_message(embed=embed, ephemeral=True)

@client.event
async def on_ready():
    # print "ready" in the console when the bot is ready to work
    print("ready")


secret = os.getenv("BOT_SECRET")
if not secret:
    raise ValueError("BOT_SECRET environment variable not set in .env!")

client.run(secret)

