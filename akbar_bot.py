import os
import json
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
pending_task = {}

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

        return tasks_dict
    except Exception as e:
        return {}

def handle_message(message):
    text = message.text or ""
    text_lower = text.lower()
    chat_id = message.chat_id
    user_id = message.from_user.id
    tasks = get_todoist_tasks()
    tasks_list = list(tasks.values())

    if user_id in pending_task:
        pending = pending_task.pop(user_id)
        if "." in text:
            name, desc = map(str.strip, text.split(".", 1))
        else:
            name, desc = text.strip(), "Tavsif berilmagan"
        result = create_todoist_task(name, desc)
        threading.Thread(target=safe_send_message, args=(chat_id, result, None)).start()
        return

    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.username == bot.get_me().username
    )

    if "yangi buyurtma" in text_lower or "buyurtma qo‘sh" in text_lower or "vazifa yarat" in text_lower:
        pending_task[user_id] = True
        threading.Thread(
            target=safe_send_message,
            args=(chat_id, "Yangi buyurtma yaratish uchun nomi va tavsifini yuboring. Masalan: 📌 Matn yozish. Yangi maqola uchun kirish qismi", None)
        ).start()
        return

    if "akbar" in text_lower or BOT_NAME.lower() in text_lower or is_reply_to_bot or message.reply_to_message:
        response = ask_gpt_with_tasks(text, tasks_list)
        threading.Thread(target=safe_send_message, args=(chat_id, response, None)).start()

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
        if response.status_code == 200 or response.status_code == 204:
            return f"📌 Buyurtma muvaffaqiyatli qo‘shildi: 📝 {name}"
        else:
            return f"⚠️ Xatolik: Buyurtma qo‘shilmadi. {response.text}"
    except Exception as e:
        return f"⚠️ Serverda xatolik: {str(e)}"

def ask_gpt_with_tasks(prompt, tasks):
    try:
        task_info_text = json.dumps(tasks, ensure_ascii=False)
        user_prompt = f"Savol: {prompt}\n\nBuyurtmalar: {task_info_text}"
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Siz ishlab chiqarish bo'yicha buyurtmalarni boshqaruvchi yordamchi AI botsiz. Xatolarsiz, toza o'zbek tilida yoz. "
                        "Quyida buyurtmalar ro'yxati mavjud. Foydalanuvchi (Hamkasb) sizdan har qanday savol so‘rasa, "
                        "siz shu ro'yxat asosida aniq, qisqa, jamoa tilida javob berasiz. "
                        "Savollar har xil bo'lishi mumkin: kim bajarayapti, qachon tugaydi, holati qanday, nimalar bor, va hokazo."
                        "Todoist bilan integratsiyalashgansan. Foydalanuvchilarning buyruqlari asosida: yangi buyurtma yaratish, borlarini ko‘rish, bajaruvchilarni aytish, muddatlarini eslatish, Subtasklar haqida ma’lumot — bularni bajara olasan. "
                        "Buyurtmalar ro‘yxatini ko‘rsatish. Har bir buyurtmaning: nomi, tavsifi, yaratuvchisi, bajaruvchisi, yaratilgan sanasi, muddat, havolasini bilasan va so'ralganda javob berasan."
                        "Yangi buyurtma qo‘sh deyilganida, undan nomi va tavsifini so‘raysan va buyurtmani yaratib yuborasan."
                    )
                },
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"⚠️ AI xatosi: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
