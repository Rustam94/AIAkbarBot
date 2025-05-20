import os
import json
import openai
import requests
import threading
from flask import Flask, request
import telegram
from dotenv import load_dotenv

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
pending_task = {}

def safe_send_message(chat_id, text, parse_mode=None):
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, disable_web_page_preview=True)
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

def get_todoist_tasks():
    try:
        load_todoist_users()
        headers = {"Authorization": f"Bearer {TODOIST_API_TOKEN}"}
        params = {"project_id": TODOIST_PROJECT_ID}
        response = requests.get("https://api.todoist.com/rest/v2/tasks", headers=headers, params=params)
        if response.status_code != 200:
            return {}
        all_tasks = response.json()
        tasks_dict = {}
        for task in all_tasks:
            creator = user_map.get(task.get("creator_id"), str(task.get("creator_id")))
            assignee = user_map.get(task.get("assignee_id"), str(task.get("assignee_id")))
            tasks_dict[task["id"]] = {
                "id": task["id"],
                "name": task.get("content", "No name"),
                "description": task.get("description", "—"),
                "created": task.get("created_at", "—"),
                "due": task.get("due", {}).get("date", "Muddat belgilanmagan") if task.get("due") else "Muddat belgilanmagan",
                "url": task.get("url", "#"),
                "creator": creator,
                "assignee": assignee
            }
        return tasks_dict
    except Exception as e:
        return {}

def handle_message(message):
    text = message.text or ""
    chat_id = message.chat_id
    user_id = message.from_user.id
    tasks = get_todoist_tasks()
    task_list = list(tasks.values())

    if user_id in pending_task:
        pending_task.pop(user_id)
        if "." in text:
            name, desc = map(str.strip, text.split(".", 1))
        else:
            name, desc = text.strip(), "Tavsif berilmagan"
        result = create_todoist_task(name, desc)
        safe_send_message(chat_id, result)
        return

    is_reply = message.reply_to_message and message.reply_to_message.text
    reply_task = None
    if is_reply:
        for task in task_list:
            if task["name"] in message.reply_to_message.text:
                reply_task = task
                break

    if any(k in text.lower() for k in ["buyurtma qo‘sh", "yangi buyurtma", "vazifa yarat"]):
        pending_task[user_id] = True
        safe_send_message(chat_id, "Yangi buyurtma nomi va tavsifini yuboring. Masalan: Kitob dizayni. Ichki maket va bosh sahifa.")
        return

    response = ask_gpt_with_tasks(text, task_list, reply_task)
    safe_send_message(chat_id, response)

def create_todoist_task(name, description):
    try:
        headers = {
            "Authorization": f"Bearer {TODOIST_API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "content": name,
            "description": description,
            "project_id": TODOIST_PROJECT_ID
        }
        response = requests.post("https://api.todoist.com/rest/v2/tasks", headers=headers, data=json.dumps(data))
        if response.status_code in (200, 204):
            return f"📌 Buyurtma muvaffaqiyatli qo‘shildi: 📝 {name}"
        return f"⚠️ Xatolik: Buyurtma qo‘shilmadi. {response.text}"
    except Exception as e:
        return f"⚠️ Serverda xatolik: {str(e)}"

def ask_gpt_with_tasks(prompt, tasks, focused_task=None):
    try:
        model = "gpt-3.5-turbo"
        system_prompt = """
Sen ishlab chiqarish korxonasidagi sun’iy intellekt yordamchi botsan. Sening isming — Akbar. Har doim sizlab gapirasan, jamoa a’zosi sifatida o‘zini tutasan. Foydalanuvchilarni hamkasbing deb bilasan.

Sening asosiy vazifang — Todoist orqali buyurtmalarni boshqarish. Foydalanuvchi har qanday savol bersa, sen quyidagi ma’lumotlarga asoslanib to‘liq va toza o‘zbek tilida javob qaytarishing kerak:

1. Buyurtmalar ro‘yxatini ko‘rsatish.
2. Har bir buyurtmaning:
   - nomi
   - tavsifi
   - yaratuvchisi
   - bajaruvchisi
   - yaratilgan sanasi
   - muddat
   - havolasi
3. Buyurtmalar holati (bajarilgan/bajarilmagan).
4. Yangi buyurtma qo‘shish.
5. Buyurtmani bajarilgan deb belgilash.
6. Buyurtmani o‘chirish.
7. Subtasklar haqida ma’lumot.
8. Belgilangan muddatga yaqinlashgan topshiriqlar haqida eslatma.

Foydalanuvchi savollari turlicha bo‘ladi. Har doim aniqlik bilan va samimiy tarzda sizlab javob ber.
"""

        context = {
            "savol": prompt,
            "buyurtmalar": tasks
        }
        if focused_task:
            context["tanlangan_buyurtma"] = focused_task

        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)}
            ],
            max_tokens=800
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"⚠️ AI xatosi: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
