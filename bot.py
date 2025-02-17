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
              description="Convert human-readable time to timestamp",
              guild=discord.Object(id="883091779535126529"))
@app_commands.describe(
    time_phrase="Human-readable time (e.g. 'in 30 minutes')",
    timezone= "Optional timezone override (saves for future use)"
)
@app_commands.choices(timezone=[
    discord.app_commands.Choice(name="PST", value="US/Pacific"),
    discord.app_commands.Choice(name="CST", value="US/Central"),
    discord.app_commands.Choice(name="EST", value="US/Eastern")
])
async def _timestamp(ctx: Interaction, time_phrase: str, timezone: str = None):
    # Get or set timezone
    if timezone:
        set_user_timezone(ctx.user.id, timezone)
    user_tz = timezone if timezone else get_user_timezone(ctx.user.id)
    tz = pytz.timezone(user_tz)
    
    # Parse time
    cal = Calendar()
    time_struct, parse_status = cal.parse(time_phrase)
    
    if parse_status == 0:
        # Parsing failed
        embed = Embed(title="Parsing Error", color=0xFF0000)
        embed.description = f"Unable to parse the time phrase: '{time_phrase}'"
        await ctx.response.send_message(embed=embed, ephemeral=True)
        return
    
    dt = datetime(*time_struct[:6])
    localized_dt = tz.localize(dt)
    
    # Format response
    unix_timestamp = int(localized_dt.timestamp())

    def pick_formatting_mark(dt):
        now = datetime.now(tz)
        diff = (dt - now).total_seconds()
        if diff <= 3600:
            return 'R'
        elif diff <= 43200:
            return 't'
        else:
            return 'f'

    formatting_mark = pick_formatting_mark(localized_dt)
        
    response = f"<t:{unix_timestamp}:{formatting_mark}>"
    
    await ctx.response.send_message(response, silent=True)

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id="883091779535126529"))
    # print "ready" in the console when the bot is ready to work
    print("ready")


secret = os.getenv("BOT_SECRET")
if not secret:
    raise ValueError("BOT_SECRET environment variable not set")

client.run(secret)

