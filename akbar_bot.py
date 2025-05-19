import os
import openai
import requests
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
            f"📌 <b>Yangi buyurtma qo‘shildi:</b>
"
            f"📝 <b>Nomi:</b> {task.get('content')}
"
            f"📅 <b>Muddat:</b> {task.get('due', {}).get('date') or 'Belgilanmagan'}"
        )
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=task_info, parse_mode="HTML")
    return "ok"

def strikethrough(text):
    return ''.join([c + '̶' for c in text])

def get_todoist_tasks():
    try:
        headers = {"Authorization": f"Bearer {TODOIST_API_TOKEN}"}
        params = {"project_id": TODOIST_PROJECT_ID}
        response = requests.get("https://api.todoist.com/rest/v2/tasks", headers=headers, params=params)

        if response.status_code != 200:
            return ["⚠️ Vazifalarni olib bo‘lmadi."]

        tasks = response.json()
        if not tasks:
            return ["Hech qanday faol buyurtma yo‘q."]

        messages = []
        for task in tasks:
            title = task.get("content", "Noma’lum vazifa")
            due = task["due"]["date"] if task.get("due") and task["due"].get("date") else "Muddat belgilanmagan"
            task_url = task.get("url", "#")

            message = (
                f"📝 <b>Nomi:</b> {title}
"
                f"📅 <b>Muddat:</b> {due}
"
                f"🔗 <a href='{task_url}'>Todoist'da ochish</a>"
            )

            messages.append(message)

        return messages
    except Exception as e:
        return [f"⚠️ Xatolik: {str(e)}"]

def handle_message(message):
    text = message.text or ""
    text_lower = text.lower()

    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.username == bot.get_me().username
    )

    if "akbar" in text_lower or BOT_NAME.lower() in text_lower or is_reply_to_bot:
        if any(word in text_lower for word in ["buyurtma qo'sh", "vazifa yarat", "task qo'sh", "yangi buyurtma"]):
            bot.send_message(chat_id=message.chat_id, text="Buyurtma nomi va tavsifini yozib bering, iltimos.")
        elif any(word in text_lower for word in [
            "qanday vazifalar", "todoist", "buyurtmalar ro'yxati", "vazifalar bor", "buyurtmalar bor"
        ]):
            tasks = get_todoist_tasks()
            for t in tasks:
                bot.send_message(chat_id=message.chat_id, text=t, parse_mode="HTML")
        else:
            response = ask_gpt(text)
            bot.send_message(chat_id=message.chat_id, text=response)

def ask_gpt(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen 'Akbar' ismli sun’iy intellekt yordamchisan. "
                        "Sen ishlab chiqarish jamoasining ichki a’zosisan va Todoist asosida ishlaysan. "
                        "Foydalanuvchilarning buyruqlarini faqat kerakli hollarda bajarasiz. "
                        "Javoblaring doimo o‘zbek tilida, samimiy, qisqa va jamoaviy bo‘lsin."
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
