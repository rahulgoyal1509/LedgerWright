"""
Loads backend/.env (if present) into os.environ as soon as anything imports
from app.* — so GEMINI_API_KEY etc. are picked up automatically without
setting them manually in every terminal session.
"""

from dotenv import load_dotenv

load_dotenv()