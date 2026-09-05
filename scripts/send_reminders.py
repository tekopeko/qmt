"""Manual/cron entry for the reminder pass — same function the app loop runs.

    python scripts/send_reminders.py

Safe to run any number of times: sends are claim-idempotent per occasion.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qmt import reminders  # noqa: E402

if __name__ == "__main__":
    print(reminders.run_once())
