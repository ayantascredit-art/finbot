import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")
db = Database()

SYSTEM_PROMPT = """Ты — персональный финансовый советник в Telegram-боте. 
Помогаешь пользователю выбраться из долгов (ипотека + кредиты) и построить финансовую стабильность.

Отвечай коротко, конкретно, по-русски. Без воды и общих фраз.

Умеешь:
- Принимать записи расходов/доходов в свободной форме
- Если пользователь добавляет транзакцию — парсить её и отвечать СТРОГО в формате:
  TRANSACTION:{"type":"expense","amount":3000,"category":"Продукты","description":"недельные покупки"}
  Затем с новой строки — короткий комментарий.
- Давать конкретные советы по закрытию долгов (метод снежного кома, лавины)
- Анализировать траты и находить где можно сэкономить
- Мотивировать и держать фокус на цели

Если это не транзакция — отвечай просто текстом."""

MAIN_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("📊 Мои траты"), KeyboardButton("💡 Совет по долгам")],
    [KeyboardButton("📈 Статистика"), KeyboardButton("🎯 Мой план")],
], resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name or "друг"
    db.init_user(user_id)

    await update.message.reply_text(
        f"Привет, {name}! 💼\n\n"
        "Я твой личный финансовый советник. Помогу выбраться из долгов и построить стабильность.\n\n"
        "Просто пиши как есть:\n"
        "— «потратил 2500 на продукты»\n"
        "— «заплатил 45000 по ипотеке»\n"
        "— «получил 80000 зарплата»\n\n"
        "Или нажми кнопку ниже 👇",
        reply_markup=MAIN_KEYBOARD
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    db.init_user(user_id)

    # Получаем историю транзакций для контекста
    transactions = db.get_transactions(user_id, limit=20)
    stats = db.get_stats(user_id)

    context_info = f"""
Транзакции пользователя (последние 20): {json.dumps(transactions, ensure_ascii=False)}
Итого доходов: {stats['total_income']} ₽
Итого расходов: {stats['total_expense']} ₽
Баланс: {stats['balance']} ₽
"""

    # Быстрые команды
    if text == "📊 Мои траты":
        text = "Покажи анализ моих трат по категориям и где я трачу больше всего"
    elif text == "💡 Совет по долгам":
        text = "Дай конкретный совет как быстрее закрыть мои долги исходя из моих трат"
    elif text == "📈 Статистика":
        text = "Дай полную статистику: доходы, расходы, баланс и динамику"
    elif text == "🎯 Мой план":
        text = "Составь конкретный план на этот месяц чтобы начать выплачивать долги быстрее"

    prompt = f"{SYSTEM_PROMPT}\n\n{context_info}\n\nСообщение пользователя: {text}"

    await update.message.chat.send_action("typing")

    try:
        response = model.generate_content(prompt)
        reply = response.text.strip()

        # Парсим транзакцию если есть
        if reply.startswith("TRANSACTION:"):
            lines = reply.split("\n", 1)
            tx_line = lines[0].replace("TRANSACTION:", "").strip()
            comment = lines[1].strip() if len(lines) > 1 else ""

            try:
                tx_data = json.loads(tx_line)
                db.add_transaction(
                    user_id=user_id,
                    tx_type=tx_data.get("type", "expense"),
                    amount=float(tx_data.get("amount", 0)),
                    category=tx_data.get("category", "Другое"),
                    description=tx_data.get("description", "")
                )

                sign = "+" if tx_data.get("type") == "income" else "−"
                color = "🟢" if tx_data.get("type") == "income" else "🔴"
                reply_text = (
                    f"{color} Записал: {sign}{tx_data.get('amount', 0):,.0f} ₽ "
                    f"({tx_data.get('category', '')})\n\n{comment}"
                )
            except (json.JSONDecodeError, KeyError):
                reply_text = comment or reply
        else:
            reply_text = reply

        await update.message.reply_text(reply_text, reply_markup=MAIN_KEYBOARD)

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(
            "⚠️ Что-то пошло не так. Попробуй ещё раз.",
            reply_markup=MAIN_KEYBOARD
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = db.get_stats(user_id)
    transactions = db.get_transactions(user_id, limit=5)

    last_tx = ""
    for tx in transactions:
        sign = "+" if tx["type"] == "income" else "−"
        last_tx += f"  {sign}{tx['amount']:,.0f} ₽ — {tx['category']}\n"

    text = (
        f"📊 *Твоя статистика*\n\n"
        f"💰 Доходы: `{stats['total_income']:,.0f} ₽`\n"
        f"💸 Расходы: `{stats['total_expense']:,.0f} ₽`\n"
        f"📈 Баланс: `{stats['balance']:,.0f} ₽`\n\n"
        f"*Последние операции:*\n{last_tx if last_tx else 'Пока нет записей'}"
    )

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
