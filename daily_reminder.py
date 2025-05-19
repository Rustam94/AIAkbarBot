import os
import requests
import telegram
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TODOIST_API_TOKEN = os.getenv("TODOIST_API_TOKEN")
TODOIST_PROJECT_ID = os.getenv("TODOIST_PROJECT_ID")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telegram.Bot(token=TELEGRAM_TOKEN)

def get_due_tasks():
    try:
        headers = {"Authorization": f"Bearer {TODOIST_API_TOKEN}"}
        params = {"project_id": TODOIST_PROJECT_ID}
        response = requests.get("https://api.todoist.com/rest/v2/tasks", headers=headers, params=params)

        if response.status_code != 200:
            return []

        return response.json()
    except Exception:
        return []

def send_reminders():
    tasks = get_due_tasks()
    today = datetime.utcnow().date()
    messages = []

    for task in tasks:
        due_str = task.get("due", {}).get("date")
        if not due_str:
            continue  # Skip tasks with no due date

        due_date = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
        delta = (due_date - today).days

        if delta in [2, 3]:
            messages.append(f"⏰ Buyurtma muddati yaqinlashmoqda:
📝 {task['content']}
📅 Muddati: {due_str}")
        elif delta == 1:
            messages.append(f"⚠️ *Ertaga* bu buyurtmaning muddati tugaydi:
📝 {task['content']}
📅 {due_str}")

    for msg in messages:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🧑‍🏭 Akbar:
" + msg, parse_mode=telegram.constants.ParseMode.MARKDOWN)

if __name__ == "__main__":
    send_reminders()