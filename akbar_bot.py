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

openai.api_key = OPENAI_API_KEY
bot = telegram.Bot(token=TELEGRAM_TOKEN)
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    if update.message:
        handle_message(update.message)
    return "ok"

def handle_message(message):
    text = message.text or ""
    text_lower = text.lower()

    print("🔍 Xabar:", text_lower)

    if "akbar" in text_lower or BOT_NAME.lower() in text_lower:
        gpt_response = ask_gpt(text)
        todoist_result = todoist_task_yaratish(text)
        reply = "🧑‍💼 Akbar:\n" + gpt_response + "\n\n📋 " + todoist_result
        message.reply_text(reply)

def ask_gpt(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sen 'Akbar' ismli sun'iy intellekt yordamchisan. "
                        "Sen dizayn studiyasi ichki jamoasining a'zosisan. "
                        "Foydalanuvchi 'Akbar' deb murojaat qilsa, bu sening isming deb tushun, sizlab javob qaytar. "
                        "Hech qachon foydalanuvchini 'Akbar' deb chaqirma. "
                        "Foydalanuvchiga mijoz emas, balki ishchi sifatida javob ber. "
                        "Javoblaring doimo jamoaviy, qisqa va rasmiy uslubda bo‘lsin. "
                        "O'zingni ishchi sifatida tut, samimiy bo‘l, lekin ichki muomala uslubida. "
                        "Har doim o‘zbek tilida javob yoz. Boshqa tillarda yozma."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return "⚠️ AI javob bera olmadi: " + str(e)

def todoist_task_yaratish(task_name):
    try:
        headers = {
            "Authorization": f"Bearer {TODOIST_API_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "content": task_name,
            "project_id": TODOIST_PROJECT_ID
        }

        response = requests.post(
            "https://api.todoist.com/rest/v2/tasks",
            json=data,
            headers=headers
        )

        if response.status_code in [200, 201, 204]:
            return "✅ Buyurtma Todoistga qo‘shildi."
        else:
            return f"⚠️ Todoist xatosi: {response.status_code} - {response.text}"
    except Exception as e:
        return f"⚠️ Todoist xatosi: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
