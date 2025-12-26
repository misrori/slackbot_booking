import os
from supabase import create_client, Client
from datetime import date
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

# Generate 30 desks automatically: "Desk 1", "Desk 2", ..., "Desk 30"
ALL_DESKS = [f"Desk {i}" for i in range(1, 31)]

def get_available_desks(target_date: str):
    """
    Returns a list of desks that are NOT booked on the target date.
    """
    try:
        # Query bookings for the specific date
        response = supabase.table("bookings").select("desk_id").eq("booking_date", target_date).execute()
        booked_desks = [item['desk_id'] for item in response.data]
        
        # Filter available desks
        available = [desk for desk in ALL_DESKS if desk not in booked_desks]
        return available
    except Exception as e:
        print(f"DB Error (get_available_desks): {e}")
        return []

def create_booking(user_id: str, desk_id: str, target_date: str):
    """
    Attempts to create a booking.
    1. Checks if the user already has a booking for that date.
    2. Inserts the new booking if the desk is free.
    """
    try:
        # 1. CHECK: Did this user already book a desk for this date?
        existing_check = supabase.table("bookings")\
            .select("id")\
            .eq("user_id", user_id)\
            .eq("booking_date", target_date)\
            .execute()
        
        if existing_check.data and len(existing_check.data) > 0:
            return False, "❌ You already have a booking for this date! Please leave some space for others. :)"

        # 2. CREATE BOOKING
        data = {"user_id": user_id, "desk_id": desk_id, "booking_date": target_date}
        supabase.table("bookings").insert(data).execute()
        return True, "Booking successful!"
        
    except Exception as e:
        print(f"Booking Error: {e}")
        # This catches the Unique Constraint violation (Race Condition)
        return False, "Sorry, someone just booked this desk a second ago!"

def get_user_bookings(user_id: str):
    """
    Retrieves future bookings for a specific user.
    """
    today = date.today().isoformat()
    try:
        response = supabase.table("bookings")\
            .select("*")\
            .eq("user_id", user_id)\
            .gte("booking_date", today)\
            .order("booking_date")\
            .execute()
        return response.data
    except Exception as e:
        print(f"DB Error (get_user_bookings): {e}")
        return []

def delete_booking(booking_id: int, user_id: str):
    """
    Deletes a specific booking by ID.
    """
    try:
        response = supabase.table("bookings")\
            .delete()\
            .eq("id", booking_id)\
            .eq("user_id", user_id)\
            .execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"DB Error (delete_booking): {e}")
        return False

def get_bookings_for_date(target_date: str):
    """
    Returns all bookings for a specific date (to see who is in the office).
    """
    try:
        response = supabase.table("bookings")\
            .select("*")\
            .eq("booking_date", target_date)\
            .execute()
        return response.data
    except Exception as e:
        print(f"DB Error (get_bookings_for_date): {e}")
        return []