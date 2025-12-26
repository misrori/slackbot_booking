import os
import json
from datetime import date, timedelta
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from dotenv import load_dotenv
import db_client

load_dotenv()

app = Flask(__name__)

# Slack Configuration
slack_token = os.environ.get("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)
OFFICE_MAP_URL = "https://i.ibb.co/gMKbfg8C/office.png"

# ---------------- HELPERS ----------------

def iso_today():
    return date.today().isoformat()

def iso_tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()

# ---------------- UI BUILDERS (English) ----------------

def build_booking_modal(selected_date=None, active_option="today"):
    """
    Constructs the booking modal.
    selected_date: YYYY-MM-DD string.
    active_option: Which radio button is active ("today", "tomorrow", "later").
    """
    
    # Default to today if no date provided
    if selected_date is None:
        selected_date = iso_today()
        
    # Define English options
    option_today = {"text": {"type": "plain_text", "text": f"Today ({iso_today()})"}, "value": "today"}
    option_tomorrow = {"text": {"type": "plain_text", "text": f"Tomorrow ({iso_tomorrow()})"}, "value": "tomorrow"}
    option_later = {"text": {"type": "plain_text", "text": "Later / Pick date"}, "value": "later"}

    # Determine initial selection
    if active_option == "today":
        initial = option_today
    elif active_option == "tomorrow":
        initial = option_tomorrow
    else:
        initial = option_later

    # 1. Date Selection Block
    blocks = [{
        "type": "input",
        "block_id": "date_selection_block",
        "dispatch_action": True,
        "element": {
            "type": "radio_buttons",
            "action_id": "date_radio_action",
            "initial_option": initial,
            "options": [option_today, option_tomorrow, option_later]
        },
        "label": {"type": "plain_text", "text": "When are you coming to the office?"}
    }]

    # 2. Show Datepicker only if 'Later' is selected
    if active_option == "later":
        blocks.append({
            "type": "section",
            "block_id": "datepicker_block",
            "text": {"type": "mrkdwn", "text": "*Select a specific date:*"},
            "accessory": {
                "type": "datepicker",
                "action_id": "date_picker_action",
                "initial_date": selected_date,
                "placeholder": {"type": "plain_text", "text": "Select date"}
            }
        })

    # 3. Map & Desk List (Dynamic)
    available_desks = db_client.get_available_desks(selected_date)
    
    desk_options = []
    if available_desks:
        for desk in available_desks:
            desk_options.append({"text": {"type": "plain_text", "text": f"🖥 {desk}"}, "value": desk})
    else:
        desk_options.append({"text": {"type": "plain_text", "text": "No desks available"}, "value": "none"})

    blocks.extend([
        {"type": "divider"},
        {"type": "image", "image_url": OFFICE_MAP_URL, "alt_text": "Office Map"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"Available desks on: *{selected_date}*"}}
    ])

    if available_desks:
        blocks.append({
            "type": "input",
            "block_id": "desk_select_block",
            "label": {"type": "plain_text", "text": "Choose a desk:"},
            "element": {
                "type": "static_select",
                "action_id": "desk_selected",
                "placeholder": {"type": "plain_text", "text": "Select..."},
                "options": desk_options
            }
        })
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "⚠️ *All desks are taken!*"}})

    # Store selected date in private metadata for submission handler
    return {
        "type": "modal",
        "callback_id": "booking_submission",
        "private_metadata": json.dumps({"selected_date": selected_date}),
        "title": {"type": "plain_text", "text": "Desk Booking"},
        "submit": {"type": "plain_text", "text": "Book"} if available_desks else None,
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks
    }

def build_my_bookings_modal(user_id):
    """
    Builds the list of bookings for the user (My Bookings).
    """
    bookings = db_client.get_user_bookings(user_id)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "My Bookings"}}]
    
    if not bookings:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "You have no upcoming bookings."}})
    else:
        for b in bookings:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📅 *{b['booking_date']}* | 🖥 *{b['desk_id']}*"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Delete"},
                    "style": "danger",
                    "value": str(b['id']),
                    "action_id": "delete_booking"
                }
            })
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Manage Bookings"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks
    }

def build_who_is_here_modal():
    """
    Builds the 'Who is in the house' modal.
    """
    today = iso_today()
    bookings = db_client.get_bookings_for_date(today)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"In the Office Today ({today})"}}, {"type": "divider"}]
    
    if not bookings:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "👻 The office is empty today."}})
    else:
        text_list = ""
        for b in bookings:
            text_list += f"• <@{b['user_id']}> is at *{b['desk_id']}*\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text_list}})
        
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Office Status"},
        "close": {"type": "plain_text", "text": "Cool"},
        "blocks": blocks
    }

# ---------------- ROUTES ----------------

@app.route("/slack/interactions", methods=["POST"])
def slack_interactions():
    # 1. SLASH COMMANDS
    if "command" in request.form:
        command = request.form["command"]
        trigger_id = request.form["trigger_id"]
        user_id = request.form["user_id"]

        try:
            if command == "/book":
                # Open with defaults: Today
                client.views_open(trigger_id=trigger_id, view=build_booking_modal(iso_today(), "today"))
            elif command == "/delete":
                client.views_open(trigger_id=trigger_id, view=build_my_bookings_modal(user_id))
            elif command == "/who_is_in_the_house":
                client.views_open(trigger_id=trigger_id, view=build_who_is_here_modal())
            return "", 200
        except Exception as e:
            print(f"Command Error: {e}")
            return "Something went wrong.", 200

    # 2. INTERACTIVE ACTIONS (Buttons, Modals)
    if "payload" in request.form:
        payload = json.loads(request.form["payload"])
        p_type = payload["type"]
        user_id = payload["user"]["id"]

        if p_type == "block_actions":
            actions = payload["actions"]
            action_id = actions[0]["action_id"]

            # --- DATE SELECTION LOGIC (Prevents 'Later' button reset) ---
            if action_id == "date_radio_action":
                choice = actions[0]["selected_option"]["value"]
                
                if choice == "today":
                    new_date = iso_today()
                elif choice == "tomorrow":
                    new_date = iso_tomorrow()
                else:
                    # If "later" is clicked, keep current map date (today), but set mode to 'later'
                    new_date = iso_today() 
                
                # Refresh modal, passing 'choice' to keep the correct radio button active
                client.views_update(
                    view_id=payload["view"]["id"],
                    hash=payload["view"]["hash"],
                    view=build_booking_modal(selected_date=new_date, active_option=choice)
                )

            # If user picks a date via Datepicker, we are definitely in 'later' mode
            if action_id == "date_picker_action":
                picked_date = actions[0]["selected_date"]
                client.views_update(
                    view_id=payload["view"]["id"],
                    hash=payload["view"]["hash"],
                    view=build_booking_modal(selected_date=picked_date, active_option="later")
                )

            # Delete button action
            if action_id == "delete_booking":
                db_client.delete_booking(actions[0]["value"], user_id)
                client.views_update(view_id=payload["view"]["id"], view=build_my_bookings_modal(user_id))

            return "", 200

        # 3. BOOKING SUBMISSION
        if p_type == "view_submission":
            view = payload["view"]
            if view["callback_id"] == "booking_submission":
                metadata = json.loads(view["private_metadata"])
                target_date = metadata["selected_date"]
                
                try:
                    selected_option = view["state"]["values"]["desk_select_block"]["desk_selected"]["selected_option"]
                    if not selected_option: return "", 200
                    
                    desk_id = selected_option["value"]
                    
                    # Attempt booking with check
                    success, msg = db_client.create_booking(user_id, desk_id, target_date)
                    
                    if success:
                        client.chat_postMessage(channel=user_id, text=f"✅ Success! You booked *{desk_id}* for {target_date}.")
                        return jsonify({"response_action": "clear"})
                    else:
                        # Return error inside the modal
                        return jsonify({
                            "response_action": "errors",
                            "errors": {
                                "desk_select_block": msg
                            }
                        })
                except KeyError:
                    pass

    return "", 200

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))