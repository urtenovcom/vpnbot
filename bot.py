import asyncio
import os
import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import database as db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ───────────────────────────────────────────
# СОСТОЯНИЯ
# ───────────────────────────────────────────
class AdminStates(StatesGroup):
    waiting_new_username = State()
    waiting_keys = State()
    waiting_notification = State()
    waiting_instructions = State()

# ───────────────────────────────────────────
# КЛАВИАТУРЫ
# ───────────────────────────────────────────
def admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить пользователя")],
        [KeyboardButton(text="👥 Выбрать пользователя")],
        [KeyboardButton(text="📢 Отправить оповещение")],
        [KeyboardButton(text="📋 Добавить инструкции")],
        [KeyboardButton(text="🗑 Удалить пользователя")],
    ], resize_keyboard=True)

def user_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔑 Мои ключи")],
        [KeyboardButton(text="❗️ Важно!")],
    ], resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)

# ───────────────────────────────────────────
# СТАРТ
# ───────────────────────────────────────────
[dp.message](workspace://dp.message)(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username

    if user_id == ADMIN_ID:
        await message.answer(
            "👋 Привет, Админ! Панель управления готова.",
            reply_markup=admin_keyboard()
        )
        return

    if not username:
        await message.answer(
            "❌ У тебя не установлен юзернейм в Telegram.\n"
            "Зайди в Настройки → Изменить профиль → Имя пользователя.\n"
            "Затем напиши /start снова."
        )
        return

    user = await db.get_user_by_username(username)
    if user:
        if not user[1]:
            await db.link_telegram_id(username, user_id)
        await message.answer(
            f"👋 Привет, @{username}! Ты в системе. Выбери действие:",
            reply_markup=user_keyboard()
        )
    else:
        await message.answer(
            "❌ Тебя нет в списке. Обратись к администратору."
        )

# ───────────────────────────────────────────
# ADMIN — Добавить пользователя
# ───────────────────────────────────────────
[dp.message(F.text](workspace://dp.message(F.text) == "➕ Добавить пользователя")
async def admin_add_user(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_new_username)
    await message.answer(
        "Введи юзернейм пользователя (можно с @ или без):",
        reply_markup=cancel_keyboard()
    )

[dp.message(AdminStates.waiting_new_username](workspace://dp.message(AdminStates.waiting_new_username))
async def process_new_username(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return
    username = message.text.strip().lstrip("@")
    existing = await db.get_user_by_username(username)
    if existing:
        await message.answer(
            f"⚠️ Пользователь @{username} уже есть в базе.",
            reply_markup=admin_keyboard()
        )
    else:
        await db.add_user(username)
        await message.answer(
            f"✅ Пользователь @{username} добавлен!",
            reply_markup=admin_keyboard()
        )
    await state.clear()

# ───────────────────────────────────────────
# ADMIN — Выбрать пользователя и добавить ключи
# ───────────────────────────────────────────
[dp.message(F.text](workspace://dp.message(F.text) == "👥 Выбрать пользователя")
async def admin_select_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await db.get_all_users()
    if not users:
        await message.answer("Список пуст. Сначала добавь пользователей.")
        return
    buttons = []
    for user in users:
        uid, tg_id, uname = user
        status = "✅" if tg_id else "⏳"
        buttons.append([InlineKeyboardButton(
            text=f"{status} @{uname}",
            callback_data=f"select_user:{uid}:{uname}"
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "✅ — уже заходил в бот\n⏳ — ещё не заходил\n\nВыбери пользователя:",
        reply_markup=kb
    )

[dp.callback_query(F.data.startswith](workspace://dp.callback_query(F.data.startswith)("select_user:"))
async def user_selected(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    _, uid, uname = call.data.split(":")
    await state.update_data(selected_user_id=int(uid), selected_username=uname)
    await state.set_state(AdminStates.waiting_keys)
    await call.message.answer(
        f"📝 Выбран: @{uname}\n\n"
        f"Отправь ключи — каждый ключ с новой строки.\n"
        f"Старые ключи будут заменены новыми.",
        reply_markup=cancel_keyboard()
    )
    await call.answer()

[dp.message(AdminStates.waiting_keys](workspace://dp.message(AdminStates.waiting_keys))
async def process_keys(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return
    data = await state.get_data()
    user_id = data["selected_user_id"]
    username = data["selected_username"]
    raw_keys = [k.strip() for k in message.text.strip().split("\n") if k.strip()]
    await db.add_keys(user_id, raw_keys)
    keys_text = "\n\n".join([f"`{k}`" for k in raw_keys])
    await message.answer(
        f"✅ Ключи для @{username} сохранены:\n\n{keys_text}",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown"
    )
    # Уведомить пользователя автоматически
    user = await db.get_user_by_username(username)
    if user and user[1]:
        try:
            now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            await bot.send_message(
                user[1],
                f"🔔 Твои VPN-ключи обновлены!\n"
                f"🕐 Дата обновления: {now}\n\n"
                f"Нажми «🔑 Мои ключи» чтобы посмотреть."
            )
        except Exception:
            pass
    await state.clear()

# ───────────────────────────────────────────
# ADMIN — Отправить оповещение всем
# ───────────────────────────────────────────
[dp.message(F.text](workspace://dp.message(F.text) == "📢 Отправить оповещение")
async def admin_notification(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_notification)
    await message.answer(
        "Напиши текст оповещения.\nБот разошлёт его всем пользователям:",
        reply_markup=cancel_keyboard()
    )

[dp.message(AdminStates.waiting_notification](workspace://dp.message(AdminStates.waiting_notification))
async def process_notification(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return
    users = await db.get_all_users()
    sent = 0
    failed = 0
    for user in users:
        uid, tg_id, uname = user
        if tg_id:
            try:
                await bot.send_message(
                    tg_id,
                    f"📢 Сообщение от администратора:\n\n{message.text}"
                )
                sent += 1
            except Exception:
                failed += 1
    await message.answer(
        f"✅ Отправлено: {sent} чел.\n❌ Не доставлено (не запускали бота): {failed} чел.",
        reply_markup=admin_keyboard()
    )
    await state.clear()

# ───────────────────────────────────────────
# ADMIN — Добавить инструкции
# ───────────────────────────────────────────
[dp.message(F.text](workspace://dp.message(F.text) == "📋 Добавить инструкции")
async def admin_instructions(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_instructions)
    await message.answer(
        "Введи текст инструкций.\nПользователи увидят его в разделе «❗️ Важно!»:",
        reply_markup=cancel_keyboard()
    )

[dp.message(AdminStates.waiting_instructions](workspace://dp.message(AdminStates.waiting_instructions))
async def process_instructions(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return
    await db.save_instructions(message.text)
    await message.answer("✅ Инструкции сохранены!", reply_markup=admin_keyboard())
    await state.clear()

# ───────────────────────────────────────────
# ADMIN — Удалить пользователя
# ───────────────────────────────────────────
[dp.message(F.text](workspace://dp.message(F.text) == "🗑 Удалить пользователя")
async def admin_delete_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await db.get_all_users()
    if not users:
        await message.answer("Список пуст.")
        return
    buttons = []
    for user in users:
        uid, tg_id, uname = user
        buttons.append([InlineKeyboardButton(
            text=f"🗑 @{uname}",
            callback_data=f"delete_user:{uid}:{uname}"
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Кого удалить?", reply_markup=kb)

[dp.callback_query(F.data.startswith](workspace://dp.callback_query(F.data.startswith)("delete_user:"))
async def confirm_delete(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    _, uid, uname = call.data.split(":")
    await db.delete_user(int(uid))
    await call.message.answer(
        f"✅ Пользователь @{uname} удалён.",
        reply_markup=admin_keyboard()
    )
    await call.answer()

# ───────────────────────────────────────────
# USER — Мои ключи
# ───────────────────────────────────────────
[dp.message(F.text](workspace://dp.message(F.text) == "🔑 Мои ключи")
async def user_keys(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    user = await db.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("❌ Тебя нет в списке. Обратись к администратору.")
        return
    keys = await db.get_keys(user[0])
    last_update = await db.get_last_key_update(user[0])
    if not keys:
        await message.answer("У тебя пока нет ключей. Ожидай от администратора.")
        return
    keys_text = "\n\n".join([f"`{k[0]}`" for k in keys])
    update_str = ""
    if last_update:
        dt = datetime.datetime.fromisoformat(last_update)
        update_str = f"\n\n🕐 *Последнее обновление:* {dt.strftime('%d.%m.%Y в %H:%M')}"
    await message.answer(
        f"🔑 *Твои VPN-ключи:*\n\n{keys_text}{update_str}",
        parse_mode="Markdown"
    )

# ───────────────────────────────────────────
# USER — Важно! (инструкции)
# ───────────────────────────────────────────
[dp.message(F.text](workspace://dp.message(F.text) == "❗️ Важно!")
async def user_important(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    result = await db.get_instructions()
    if not result:
        await message.answer("Инструкции ещё не добавлены администратором.")
        return
    text, updated_at = result
    dt = datetime.datetime.fromisoformat(updated_at)
    await message.answer(
        f"❗️ *Важная информация:*\n\n{text}\n\n"
        f"_Обновлено: {dt.strftime('%d.%m.%Y в %H:%M')}_",
        parse_mode="Markdown"
    )

# ───────────────────────────────────────────
# ЗАПУСК
# ───────────────────────────────────────────
async def main():
    await db.init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
