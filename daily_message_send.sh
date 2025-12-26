#!/bin/bash

# 1. Navigate to the project directory
# IMPORTANT: Change this path to your actual project folder!
cd /home/misi/slackbot

# 2. Activate the Python Virtual Environment
source .venv/bin/activate

# 3. Run the Python script
python3 daily_message.py

# 4. Deactivate (optional, but good practice)
deactivate



# Run Office Bot announcement at 18:00 on Mon,Tue,Wed,Thu,Fri
# 0 18 * * 1-5 /root/slack-office-bot/run_announcement.sh >> /root/slack-office-bot/cron.log 2>&1