import os
import openai
import requests
import threading
from flask import Flask, request
import telegram
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_NAME = os.getenv("BOT_NAME", "@Akbar")
TODOIST_API_TOKEN = os.getenv("TODOIST_API_TOKEN")
TODOIST_PROJECT_ID = os.getenv("TODOIST_PROJECT_ID")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

openai.api_key = OPENAI_API_KEY
bot = telegram.Bot(token=TELEGRAM_TOKEN)
app = Flask(__name__)

user_map = {}

def safe_send_message(chat_id, text, parse_mode=None):
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except Exception as e:
        print(f"⚠️ Yuborishda xatolik: {e}")

def strikethrough(text):
    return ''.join([c + '\u0336' for c in text])

def load_todoist_users():
    try:
        headers = {"Authorization": f"Bearer {TODOIST_API_TOKEN}"}
        response = requests.get("https://api.todoist.com/sync/v9/sync", headers=headers, params={"sync_token": "*", "resource_types": '["collaborators"]'})
        if response.status_code == 200:
            data = response.json()
            for user in data.get("collaborators", []):
                user_map[user["id"]] = user.get("full_name") or user.get("email")
    except Exception as e:
        print(f"⚠️ Foydalanuvchi yuklashda xatolik: {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    if update.message:
        handle_message(update.message)
    return "ok"

@app.route("/todoist-hook", methods=["POST"])
def todoist_webhook():
    data = request.json
    if data and data.get("event_name") == "item:added":
        task = data.get("event_data", {})
        task_info = (
            f"📌 <b>Yangi buyurtma qo‘shildi:</b>\n"
            f"📝 <b>Nomi:</b> {task.get('content')}\n"
            f"📅 <b>Muddat:</b> {task.get('due', {}).get('date') or 'Belgilanmagan'}"
        )
        threading.Thread(target=safe_send_message, args=(TELEGRAM_CHAT_ID, task_info, "HTML")).start()
    return "ok"

def get_todoist_tasks(full=False):
    try:
        load_todoist_users()
        headers = {"Authorization": f"Bearer {TODOIST_API_TOKEN}"}
        params = {"project_id": TODOIST_PROJECT_ID}
        response = requests.get("https://api.todoist.com/rest/v2/tasks", headers=headers, params=params)

        if response.status_code != 200:
            return {}

        all_tasks = response.json()
        tasks_dict = {}
        subtasks_map = {}

        for task in all_tasks:
            if task.get("parent_id"):
                parent_id = task["parent_id"]
                if parent_id not in subtasks_map:
                    subtasks_map[parent_id] = []
                subtasks_map[parent_id].append((task["content"], "completed" if task.get("is_completed") else "active"))
            else:
                creator = user_map.get(task.get("creator_id"), str(task.get("creator_id")))
                assignee = user_map.get(task.get("assignee_id"), str(task.get("assignee_id")))
                tasks_dict[task["id"]] = {
                    "id": task["id"],
                    "name": task.get("content", "No name"),
                    "description": task.get("description", "—"),
                    "created": task.get("created_at", "—"),
                    "due": task.get("due", {}).get("date", "Muddat belgilanmagan") if task.get("due") else "Muddat belgilanmagan",
                    "url": task.get("url", "#"),
                    "subtasks": {},
                    "creator": creator,
                    "assignee": assignee
                }

        for parent_id, subtasks in subtasks_map.items():
            if parent_id in tasks_dict:
                tasks_dict[parent_id]["subtasks"] = {name: status for name, status in subtasks}

        if not full:
            return tasks_dict

        messages = []
        for task in tasks_dict.values():
            message = (
                f"📌 <b>Nomi:</b> {task['name']}\n"
                f"📄 <b>Tavsif:</b> {task['description']}\n"
                f"👤 <b>Yaratuvchi:</b> {task['creator']}\n"
                f"👥 <b>Bajaruvchi:</b> {task['assignee']}\n"
                f"📅 <b>Yaratilgan sana:</b> {task['created']}\n"
                f"⏳ <b>Topshirish muddati:</b> {task['due']}\n"
                f"🔗 <a href='{task['url']}'>Todoist'da ochish</a>"
            )

            if task["subtasks"]:
                message += "\n\n🔽 <b>Pozitsiyalar:</b>"
                for subtask, status in task["subtasks"].items():
                    display = strikethrough(subtask) if status == "completed" else subtask
                    message += f"\n  ➖ {display}"

            messages.append(message)

        return messages
    except Exception as e:
        return [f"⚠️ Xatolik: {str(e)}"]

def handle_message(message):
    text = message.text or ""
    text_lower = text.lower()
    tasks = get_todoist_tasks()

    if message.reply_to_message:
        for task in tasks.values():
            if task["name"] in message.reply_to_message.text:
                if "bajaruvchi" in text_lower:
                    response = f"👥 <b>Bajaruvchi:</b> {task['assignee']}"
                elif "holat" in text_lower or "qanday" in text_lower:
                    response = f"📌 <b>Buyurtma:</b> {task['name']}\n⏳ <b>Muddat:</b> {task['due']}"
                else:
                    response = "Buyurtmaga oid savolingizni aniqroq yozing."
                threading.Thread(target=safe_send_message, args=(message.chat_id, response, "HTML")).start()
                return

    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.username == bot.get_me().username
    )

    if "akbar" in text_lower or BOT_NAME.lower() in text_lower or is_reply_to_bot:
        if any(word in text_lower for word in ["buyurtma qo'sh", "vazifa yarat", "task qo'sh", "yangi buyurtma"]):
            threading.Thread(target=safe_send_message, args=(message.chat_id, "Buyurtma nomi va tavsifini yozib bering, iltimos.", None)).start()
        elif any(word in text_lower for word in [
            "qanday vazifalar", "todoist", "buyurtmalar ro'yxati", "vazifalar bor", "buyurtmalar bor"
        ]):
            for t in get_todoist_tasks(full=True):
                threading.Thread(target=safe_send_message, args=(message.chat_id, t, "HTML")).start()
        else:
            response = ask_gpt(text)
            threading.Thread(target=safe_send_message, args=(message.chat_id, response, None)).start()

def ask_gpt(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen ishlab chiqarish jamoasining ichki sun’iy intellekt yordamchisan. "
                        "Sening isming Akbar. Foydalanuvchilar bilan sizlab, jamoa a'zosi sifatida suhbatlash. "
                        "Todoist asosida ishlaysan. Yordamga tayyormisan degan savollarga samimiy, aniq, odamga o‘xshab javob ber."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=400
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"⚠️ AI xatosi: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
