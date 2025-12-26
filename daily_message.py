import os
import locale
from datetime import date, timedelta
from slack_sdk import WebClient
from dotenv import load_dotenv
import db_client

# Load environment variables
load_dotenv()

# Try to set locale for day names (optional)
try:
    locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')
except:
    pass

# Configuration
slack_token = os.environ.get("SLACK_BOT_TOKEN")
channel_id = os.environ.get("SLACK_CHANNEL_ID")
slack_client = WebClient(token=slack_token)

def get_next_workday():
    """
    Calculates the next working day.
    If Today is Friday (4) -> Returns Next Monday (+3 days)
    If Today is Mon-Thu -> Returns Tomorrow (+1 day)
    """
    today = date.today()
    weekday = today.weekday() # Mon=0, ... Fri=4, Sun=6
    
    if weekday == 4: # Friday
        return today + timedelta(days=3)
    else:
        return today + timedelta(days=1)

def build_dashboard_blocks(target_date_obj, bookings):
    """
    Constructs the UI for the Slack message.
    """
    target_date_str = target_date_obj.isoformat()
    day_name = target_date_obj.strftime("%A") # e.g., "Monday"
    
    if not bookings:
        list_text = "The office is currently empty. 👻"
    else:
        lines = [f"• <@{b['user_id']}> ➝ *{b['desk_id']}*" for b in bookings]
        list_text = "\n".join(lines)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🏢 Office Status: {day_name}"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"On *{day_name}, {target_date_str}*, the following people will be in the office:"}
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": list_text}
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "I'm coming too! (Book)"},
                    "action_id": "open_booking_modal",
                    "style": "primary"
                }
            ]
        }
    ]
    return blocks

def main():
    """
    Main execution logic.
    """
    print("--- Starting Announcement Job ---")
    
    # 1. Calculate the Target Date (Next Workday)
    next_workday = get_next_workday()
    next_workday_str = next_workday.isoformat()
    print(f"Target Date: {next_workday_str}")
    
    # 2. Get current bookings from DB
    bookings = db_client.get_bookings_for_date(next_workday_str)
    
    # 3. Build the Message Blocks
    blocks = build_dashboard_blocks(next_workday, bookings)
    fallback_text = f"Office status for {next_workday_str}"

    try:
        # 4. Send the Message to Slack
        response = slack_client.chat_postMessage(
            channel=channel_id, 
            blocks=blocks, 
            text=fallback_text
        )
        
        # 5. Save the Message ID to DB for future updates
        if response["ok"]:
            db_client.save_daily_message(next_workday_str, channel_id, response["ts"])
            print(f"✅ Dashboard posted successfully. TS: {response['ts']}")
        else:
            print(f"❌ Slack API Error: {response['error']}")
            
    except Exception as e:
        print(f"❌ System Error: {e}")

if __name__ == "__main__":
    # This script runs once and exits. Perfect for Crontab.
    main()