import os
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is missing")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY environment variable is missing")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)
