import os
import openai
from flask import Flask, request
import telegram
from dotenv import load_dotenv

# .env faylni yuklaymiz
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_NAME = os.getenv("BOT_NAME", "@AIAkbarBot")

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
    text = message.text
    if text and ("akbar" in text.lower() or BOT_NAME.lower() in text.lower()):
        response = ask_gpt(text)
        message.reply_text("🧑‍💼 Akbar:\n" + response)

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
                        "Foydalanuvchi 'Akbar' deb murojaat qilsa, bu sening isming deb tushun. "
                        "Hech qachon foydalanuvchini 'Akbar' deb chaqirma. "
                        "Foydalanuvchiga mijoz emas, balki ishchi sifatida javob ber. "
                        "Javoblaring doimo jamoaviy, qisqa va rasmiy uslubda bo‘lsin. "
                        "O'zingni ishchi sifatida tut, samimiy bo‘l, lekin doimo ichki muomala uslubida."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return "⚠️ AI javob bera olmadi: " + str(e)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
