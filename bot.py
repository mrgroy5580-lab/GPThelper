
import os
import json
import tempfile
from flask import Flask, request
from telegram import Update, BotCommand, InputFile
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
import openai
import requests

# --- Настройки ---
TELEGRAM_TOKEN = os.getenv("8481954029:AAG93JyOPtyafOD15jbqrDzW5dHa5yrQP8M")
OPENAI_API_KEY = os.getenv("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")
RENDER_URL = os.getenv("RENDER_URL")  # https://<your-app>.onrender.com
PORT = int(os.getenv("PORT", 5000))

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Please set TELEGRAM_TOKEN and OPENAI_API_KEY environment variables")

openai.api_key = OPENAI_API_KEY

# --- Файлы хранения ---
HISTORY_FILE = "history.json"
CONFIG_FILE = "config.json"   # stores mode and language per user

# --- Утилиты для JSON ---
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_histories = load_json(HISTORY_FILE, {})
user_configs = load_json(CONFIG_FILE, {})  # {user_id: {"mode":"text","lang":"ru"}}

# --- Тексты интерфейса ---
LANG_TEXTS = {
    "ru": {
        "welcome": "Привет! Выберите режим работы: \\n/mode <text|image|code|table> — режимы\\n/lang <ru|be|en> — язык\\n/reset — очистить историю\\n/export — экспорт CSV",
        "mode_set": "✅ Режим установлен: {mode}",
        "lang_set": "✅ Язык интерфейса установлен: {lang}",
        "unknown_cmd": "Неизвестная команда.",
        "ask_prompt": "Напиши запрос для режима: {mode} (на {lang})",
        "error": "Ошибка: {err}",
        "reset": "🧹 История очищена.",
        "send_image_error": "Не удалось сгенерировать изображение: {err}"
    },
    "be": {
        "welcome": "Прывітанне! Абярыце рэжым працы: \\n/mode <text|image|code|table> — рэжымы\\n/lang <ru|be|en> — мова\\n/reset — ачысціць гісторыю\\n/export — экспарт CSV",
        "mode_set": "✅ Рэжым устаноўлены: {mode}",
        "lang_set": "✅ Мова інтэрфейсу ўстаноўлена: {lang}",
        "unknown_cmd": "Невядомая каманда.",
        "ask_prompt": "Напішы запыт для рэжыму: {mode} (на {lang})",
        "error": "Памылка: {err}",
        "reset": "🧹 Гісторыя ачышчана.",
        "send_image_error": "Не ўдалося стварыць малюнак: {err}"
    },
    "en": {
        "welcome": "Hello! Choose work mode: \\n/mode <text|image|code|table> — modes\\n/lang <ru|be|en> — language\\n/reset — clear history\\n/export — export CSV",
        "mode_set": "✅ Mode set to: {mode}",
        "lang_set": "✅ Interface language set to: {lang}",
        "unknown_cmd": "Unknown command.",
        "ask_prompt": "Send a prompt for mode: {mode} (lang: {lang})",
        "error": "Error: {err}",
        "reset": "🧹 History cleared.",
        "send_image_error": "Failed to generate image: {err}"
    }
}

# --- Flask app for webhook endpoint ---
app = Flask(__name__)

# --- Telegram application ---
application = Application.builder().token(TELEGRAM_TOKEN).build()

# --- Helpers ---
def get_user_config(user_id):
    cfg = user_configs.get(user_id, {})
    if "mode" not in cfg:
        cfg["mode"] = "text"
    if "lang" not in cfg:
        cfg["lang"] = "ru"
    user_configs[user_id] = cfg
    return cfg

def set_user_mode(user_id, mode):
    cfg = get_user_config(user_id)
    cfg["mode"] = mode
    user_configs[user_id] = cfg
    save_json(CONFIG_FILE, user_configs)

def set_user_lang(user_id, lang):
    cfg = get_user_config(user_id)
    cfg["lang"] = lang
    user_configs[user_id] = cfg
    save_json(CONFIG_FILE, user_configs)

# --- Command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cfg = get_user_config(user_id)
    texts = LANG_TEXTS[cfg.get("lang","ru")]
    await update.message.reply_text(texts["welcome"])

async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    arg = (context.args[0].lower() if context.args else "").strip()
    cfg = get_user_config(user_id)
    texts = LANG_TEXTS[cfg.get("lang","ru")]
    modes = ["text","image","code","table"]
    if arg in modes:
        set_user_mode(user_id, arg)
        await update.message.reply_text(texts["mode_set"].format(mode=arg))
    else:
        await update.message.reply_text("Usage: /mode <text|image|code|table>")

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cfg = get_user_config(user_id)
    texts = LANG_TEXTS[cfg.get("lang","ru")]
    await update.message.reply_text(
        texts["welcome"] + "\\n\\n" + "Change language: /lang <ru|be|en>"
    )

async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    arg = (context.args[0].lower() if context.args else "").strip()
    if arg not in ("ru","be","en"):
        await update.message.reply_text("Usage: /lang <ru|be|en>")
        return
    set_user_lang(user_id, arg)
    texts = LANG_TEXTS[arg]
    await update.message.reply_text(texts["lang_set"].format(lang=arg))

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_histories.pop(user_id, None)
    save_json(HISTORY_FILE, user_histories)
    cfg = get_user_config(user_id)
    texts = LANG_TEXTS[cfg.get("lang","ru")]
    await update.message.reply_text(texts["reset"])

async def cmd_export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    conv = user_histories.get(user_id, [])
    if not conv:
        await update.message.reply_text("No conversation to export.")
        return
    lines = ["role,text"]
    for m in conv:
        role = m.get("role","")
        text = m.get("content","").replace('"','""')
        lines.append(f'"{role}","{text}"')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write("\\n".join(lines).encode("utf-8"))
        tmp_path = tmp.name
    await update.message.reply_document(document=InputFile(tmp_path), filename="conversation.csv")

# --- Message handler: routes based on mode ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = (update.message.text or "").strip()
    if not text:
        return
    cfg = get_user_config(user_id)
    mode = cfg["mode"]
    lang = cfg["lang"]
    # Ensure history exists
    if user_id not in user_histories:
        user_histories[user_id] = [{"role":"system","content": {"ru":"Ты дружелюбный ассистент.","be":"Ты дружелюбны памочнік.","en":"You are a helpful assistant."}[lang]}]
    # Append user message
    user_histories[user_id].append({"role":"user","content": text})
    # Trim history
    if len(user_histories[user_id]) > 12:
        user_histories[user_id] = user_histories[user_id][-12:]
    try:
        if mode == "text":
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=user_histories[user_id]
            )
            reply = resp["choices"][0]["message"]["content"]
            user_histories[user_id].append({"role":"assistant","content": reply})
            save_json(HISTORY_FILE, user_histories)
            await update.message.reply_text(reply)
        elif mode == "code":
            messages = user_histories[user_id] + [{"role":"system","content":"Focus on producing code. Return code formatted in Markdown fences. If language is obvious, indicate it."}]
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=messages
            )
            reply = resp["choices"][0]["message"]["content"]
            user_histories[user_id].append({"role":"assistant","content": reply})
            save_json(HISTORY_FILE, user_histories)
            await update.message.reply_text(reply)
        elif mode == "image":
            image_resp = openai.Image.create(
                prompt=text,
                n=1,
                size="1024x1024"
            )
            image_url = image_resp["data"][0]["url"]
            img_data = requests.get(image_url).content
            user_histories[user_id].append({"role":"assistant","content": f"[image] {image_url}"})
            save_json(HISTORY_FILE, user_histories)
            await update.message.reply_photo(photo=img_data, caption=f"🎨 {text}")
        elif mode == "table":
            prompt = (
                "Return only CSV content (no extra explanation). First line must be header. Respond in the user's language.\n\nUser prompt:\n" + text
            )
            messages = [{"role":"system","content":"You must output valid CSV only."}, {"role":"user","content":prompt}]
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=messages
            )
            csv_text = resp["choices"][0]["message"]["content"]
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(csv_text.encode("utf-8"))
                tmp_path = tmp.name
            user_histories[user_id].append({"role":"assistant","content":"[table csv]"})
            save_json(HISTORY_FILE, user_histories)
            await update.message.reply_document(document=InputFile(tmp_path), filename="table.csv")
        else:
            await update.message.reply_text(LANG_TEXTS[lang]["unknown_cmd"])
    except Exception as e:
        await update.message.reply_text(LANG_TEXTS[lang]["error"].format(err=str(e)))

# --- Setup commands and webhook route ---
async def set_bot_commands():
    commands = [
        BotCommand("start","Start / приветствие"),
        BotCommand("mode","Select mode: /mode <text|image|code|table>"),
        BotCommand("lang","Set language: /lang <ru|be|en>"),
        BotCommand("settings","Open settings"),
        BotCommand("reset","Clear history"),
        BotCommand("export","Export conversation CSV (/export)")
    ]
    await application.bot.set_my_commands(commands)

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "✅ ChatGPT Universal Bot is running", 200

@app.before_first_request
def on_startup():
    webhook_url = f"{RENDER_URL}/{TELEGRAM_TOKEN}"
    print("Setting webhook to", webhook_url)
    application.bot.set_webhook(webhook_url)
    application.create_task(set_bot_commands())

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("mode", cmd_mode))
application.add_handler(CommandHandler("settings", cmd_settings))
application.add_handler(CommandHandler("lang", cmd_lang))
application.add_handler(CommandHandler("reset", cmd_reset))
application.add_handler(CommandHandler("export", cmd_export_csv))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == "__main__":
    print("Starting Flask server...")
    app.run(host="0.0.0.0", port=PORT)
