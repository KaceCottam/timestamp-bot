# Timestamp Bot
A git bot that allows you to write a timestamp in the chat.

## Usage
To use the Timestamp Bot, you need to set up your environment and install the necessary dependencies.

1. **Create a `.env` file:**
    Copy the `.env.example` file to a new file named `.env` in the root directory of the project. Fill in the `BOT_SECRET` with your bot's secret key obtained from the Discord Developer Portal.

    ```bash
    cp .env.example .env
    ```

2. **Install dependencies:**
    Make sure you have Python and `pip` installed. Then, install the required Python packages using the following command:

    ```bash
    pip install -r requirements.txt
    ```

3. **Run the bot:**
    Start the bot using the following command:

    ```bash
    python bot.py
    ```

Your bot should now be up and running. You can use the `/timestamp` command in your Discord server to convert human-readable time phrases into Discord timestamps.

## Commands

### `/timestamp`
Convert human-readable time to a timestamp.

**Parameters:**
- `time_phrase` (str): Human-readable time (e.g. 'in 30 minutes').
- `timezone` (str, optional): Optional timezone override (saves for future use). Choices are:
    - `PST` (US/Pacific)
    - `CST` (US/Central)
    - `EST` (US/Eastern)

**Description:**
This command converts a given human-readable time phrase into a Discord timestamp. If a timezone is provided, it will override the user's saved timezone and save the new one for future use. The bot will respond with a formatted timestamp that can be used in Discord messages.