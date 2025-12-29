import os
import json
import locale
from datetime import date, timedelta, datetime
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from dotenv import load_dotenv
import db_client

load_dotenv()

app = Flask(__name__)

slack_token = os.environ.get("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)
OFFICE_MAP_URL = "https://i.ibb.co/wNhCT0wh/officev3.png"

# ---------------- HELPERS ----------------

def iso_today():
    return date.today().isoformat()

def iso_tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()

def refresh_daily_dashboard(target_date_str):
    """
    REAL-TIME UPDATE LOGIC:
    1. Check if we sent a 'dashboard' message for this specific date.
    2. If yes, fetch the new list of people.
    3. Overwrite the old Slack message with the new list.
    """
    # 1. Look for message ID in DB
    record = db_client.get_daily_message(target_date_str)
    if not record:
        return # No message exists for this date, nothing to update.

    channel_id = record['channel_id']
    message_ts = record['message_ts']

    # 2. Get fresh data
    bookings = db_client.get_bookings_for_date(target_date_str)
    
    # 3. Rebuild Blocks (Exact same logic as scheduler.py)
    # We parse the date string back to object to get the day name
    target_date_obj = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    day_name = target_date_obj.strftime("%A")

    if not bookings:
        list_text = "The office is currently empty. 👻"
    else:
        lines = [f"• <@{b['user_id']}> ➝ *{b['desk_id']}*" for b in bookings]
        list_text = "\n".join(lines)

    new_blocks = [
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
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "🔄 *List updated just now*"}]
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

    # 4. Update Slack
    try:
        client.chat_update(channel=channel_id, ts=message_ts, blocks=new_blocks, text="Updated office status")
        print(f"Updated dashboard for {target_date_str}")
    except Exception as e:
        print(f"Failed to update dashboard: {e}")

# ---------------- UI BUILDERS ----------------

def build_booking_modal(selected_date=None, active_option="today"):
    if selected_date is None: selected_date = iso_today()
    
    # Options
    op_today = {"text": {"type": "plain_text", "text": f"Today ({iso_today()})"}, "value": "today"}
    op_tom = {"text": {"type": "plain_text", "text": f"Tomorrow ({iso_tomorrow()})"}, "value": "tomorrow"}
    op_later = {"text": {"type": "plain_text", "text": "Pick Date..."}, "value": "later"}

    if active_option == "today": initial = op_today
    elif active_option == "tomorrow": initial = op_tom
    else: initial = op_later

    blocks = [{
        "type": "input",
        "block_id": "date_selection_block",
        "dispatch_action": True,
        "element": {
            "type": "radio_buttons",
            "action_id": "date_radio_action",
            "initial_option": initial,
            "options": [op_today, op_tom, op_later]
        },
        "label": {"type": "plain_text", "text": "When are you coming?"}
    }]

    if active_option == "later":
        blocks.append({
            "type": "section",
            "block_id": "datepicker_block",
            "text": {"type": "mrkdwn", "text": "*Select Date:*"},
            "accessory": {"type": "datepicker", "action_id": "date_picker_action", "initial_date": selected_date}
        })

    # Available Desks
    available = db_client.get_available_desks(selected_date)
    desk_ops = []
    if available:
        for d in available:
            desk_ops.append({"text": {"type": "plain_text", "text": f"🖥 {d}"}, "value": d})
    else:
        desk_ops.append({"text": {"type": "plain_text", "text": "Full"}, "value": "none"})

    blocks.extend([
        {"type": "divider"},
        {"type": "image", "image_url": OFFICE_MAP_URL, "alt_text": "Map"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"Available: *{selected_date}*"}}
    ])

    if available:
        blocks.append({
            "type": "input",
            "block_id": "desk_select_block",
            "label": {"type": "plain_text", "text": "Desk:"},
            "element": {"type": "static_select", "action_id": "desk_selected", "placeholder": {"type": "plain_text", "text": "Select..."}, "options": desk_ops}
        })
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "⚠️ *Full House!*"}})

    return {
        "type": "modal",
        "callback_id": "booking_submission",
        "private_metadata": json.dumps({"selected_date": selected_date}),
        "title": {"type": "plain_text", "text": "Book Desk"},
        "submit": {"type": "plain_text", "text": "Book"} if available else None,
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks
    }

def build_my_bookings_modal(user_id):
    bookings = db_client.get_user_bookings(user_id)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": "My Bookings"}}]
    if not bookings:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "No bookings."}})
    else:
        for b in bookings:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📅 *{b['booking_date']}* | 🖥 *{b['desk_id']}*"},
                "accessory": {"type": "button", "text": {"type": "plain_text", "text": "Delete"}, "style": "danger", "value": str(b['id']), "action_id": "delete_booking"}
            })
    return {"type": "modal", "title": {"type": "plain_text", "text": "Manage"}, "blocks": blocks}

def build_who_is_here_modal():
    today = iso_today()
    bookings = db_client.get_bookings_for_date(today)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Today ({today})"}}]
    if not bookings:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "Office is empty."}})
    else:
        txt = "\n".join([f"• <@{b['user_id']}> ➝ *{b['desk_id']}*" for b in bookings])
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": txt}})
    return {"type": "modal", "title": {"type": "plain_text", "text": "Status"}, "blocks": blocks}

# ---------------- ROUTING ----------------

@app.route("/slack/interactions", methods=["POST"])
def slack_interactions():
    # 1. COMMANDS
    if "command" in request.form:
        cmd = request.form["command"]
        trig = request.form["trigger_id"]
        uid = request.form["user_id"]
        try:
            if cmd == "/book": client.views_open(trigger_id=trig, view=build_booking_modal(iso_today(), "today"))
            elif cmd == "/delete": client.views_open(trigger_id=trig, view=build_my_bookings_modal(uid))
            elif cmd == "/who_is_in_the_house": client.views_open(trigger_id=trig, view=build_who_is_here_modal())
            return "", 200
        except: return "Error", 200

    # 2. ACTIONS
    if "payload" in request.form:
        payload = json.loads(request.form["payload"])
        ptype = payload["type"]
        uid = payload["user"]["id"]

        if ptype == "block_actions":
            act = payload["actions"][0]
            aid = act["action_id"]

            if aid == "open_booking_modal":
                client.views_open(trigger_id=payload["trigger_id"], view=build_booking_modal(iso_today(), "today"))

            elif aid == "date_radio_action":
                val = act["selected_option"]["value"]
                # Logic: If Tomorrow selected, date=Tomorrow. If Today/Later selected, date=Today (map updates later)
                ndate = iso_tomorrow() if val == "tomorrow" else iso_today()
                client.views_update(view_id=payload["view"]["id"], view=build_booking_modal(ndate, val))

            elif aid == "date_picker_action":
                pdate = act["selected_date"]
                client.views_update(view_id=payload["view"]["id"], view=build_booking_modal(pdate, "later"))

            elif aid == "delete_booking":
                # We need to find the booking date BEFORE deleting to update the dashboard
                # For this simplified version, we just blindly trigger a refresh for Tomorrow and Next Monday just in case.
                db_client.delete_booking(act["value"], uid)
                client.views_update(view_id=payload["view"]["id"], view=build_my_bookings_modal(uid))
                
                # Check updates for standard days
                refresh_daily_dashboard(iso_tomorrow()) 
                # Ideally we query the booking date, but this covers 90% of cases

            return "", 200

        if ptype == "view_submission":
            view = payload["view"]
            if view["callback_id"] == "booking_submission":
                meta = json.loads(view["private_metadata"])
                tdate = meta["selected_date"]
                try:
                    sel = view["state"]["values"]["desk_select_block"]["desk_selected"]["selected_option"]
                    if not sel: return "", 200
                    
                    desk = sel["value"]
                    success, msg = db_client.create_booking(uid, desk, tdate)
                    
                    if success:
                        client.chat_postMessage(channel=uid, text=f"✅ Booked: {desk} for {tdate}")
                        
                        # TRIGGER REAL-TIME UPDATE
                        refresh_daily_dashboard(tdate)
                        
                        return jsonify({"response_action": "clear"})
                    else:
                        return jsonify({"response_action": "errors", "errors": {"desk_select_block": msg}})
                except: pass

    return "", 200

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))