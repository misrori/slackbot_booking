import os
from supabase import create_client, Client
from datetime import date
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

# Generate 30 desks
ALL_DESKS = [f"Desk {i}" for i in range(1, 31)]

# --- BOOKING FUNCTIONS ---

def get_available_desks(target_date: str):
    """Returns desks NOT booked on target_date."""
    try:
        response = supabase.table("bookings").select("desk_id").eq("booking_date", target_date).execute()
        booked_desks = [item['desk_id'] for item in response.data]
        return [desk for desk in ALL_DESKS if desk not in booked_desks]
    except Exception as e:
        print(f"DB Error (get_available_desks): {e}")
        return []

def create_booking(user_id: str, desk_id: str, target_date: str):
    """Creates a booking if user hasn't booked yet."""
    try:
        # Check existing
        existing = supabase.table("bookings").select("id").eq("user_id", user_id).eq("booking_date", target_date).execute()
        if existing.data:
            return False, "❌ You already have a seat for this day!"

        # Insert
        data = {"user_id": user_id, "desk_id": desk_id, "booking_date": target_date}
        supabase.table("bookings").insert(data).execute()
        return True, "Success!"
    except Exception as e:
        print(f"Booking Error: {e}")
        return False, "Someone just took this desk!"

def delete_booking(booking_id: int, user_id: str):
    """Deletes a booking."""
    try:
        response = supabase.table("bookings").delete().eq("id", booking_id).eq("user_id", user_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"DB Error: {e}")
        return False

def get_user_bookings(user_id: str):
    """Get future bookings for user."""
    today = date.today().isoformat()
    try:
        return supabase.table("bookings").select("*").eq("user_id", user_id).gte("booking_date", today).order("booking_date").execute().data
    except Exception:
        return []

def get_bookings_for_date(target_date: str):
    """Get all people coming on a specific date."""
    try:
        return supabase.table("bookings").select("*").eq("booking_date", target_date).execute().data
    except Exception:
        return []

# --- MESSAGE DASHBOARD FUNCTIONS ---

def save_daily_message(target_date: str, channel_id: str, message_ts: str):
    """Saves the Slack message ID so we can update it later."""
    try:
        data = {"target_date": target_date, "channel_id": channel_id, "message_ts": message_ts}
        supabase.table("daily_messages").upsert(data).execute()
    except Exception as e:
        print(f"DB Error (save_daily_message): {e}")

def get_daily_message(target_date: str):
    """Retrieves the message ID for a specific date."""
    try:
        response = supabase.table("daily_messages").select("*").eq("target_date", target_date).maybe_single().execute()
        return response.data
    except Exception as e:
        print(f"DB Error (get_daily_message): {e}")
        return None