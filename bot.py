import asyncio
import os
import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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

class AdminStates(StatesGroup):
    waiting_new_username = State()
    waiting_keys = State()
    waiting_notification = State()
    waiting_instructions = State()

BTN_ADD_USER = "Dobavit polzovatelya"
BTN_SELECT_USER = "Vybrat polzovatelya"
BTN_NOTIFY = "Otpravit opoveshenie"
BTN_INSTRUCTIONS = "Dobavit instrukcii"
BTN_DELETE_USER = "Udalit polzovatelya"
BTN_MY_KEYS = "Moi klyuchi"
BTN_IMPORTANT = "Vazhno"
BTN_CANCEL = "Otmena"

def admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=BTN_ADD_USER)],
        [KeyboardButton(text=BTN_SELECT_USER)],
        [KeyboardButton(text=BTN_NOTIFY)],
        [KeyboardButton(text=BTN_INSTRUCTIONS)],
        [KeyboardButton(text=BTN_DELETE_USER)],
    ], resize_keyboard=True)

def user_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=BTN_MY_KEYS)],
        [KeyboardButton(text=BTN_IMPORTANT)],
    ], resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=BTN_CANCEL)]
    ], resize_keyboard=True)


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    if user_id == ADMIN_ID:
        await message.answer("Privet, Admin! Panel upravleniya gotova.", reply_markup=admin_keyboard())
        return
    if not username:
        await message.answer("U tebya ne ustanovlen username v Telegram. Zaidi v Nastroyki i ustanovi ego, zatem napishi /start snova.")
        return
    user = await db.get_user_by_username(username)
    if user:
        if not user[1]:
            await db.link_telegram_id(username, user_id)
        await message.answer(f"Privet, @{username}! Ty v sisteme. Vyberi deystvie:", reply_markup=user_keyboard())
    else:
        await message.answer("Tebya net v spiske. Obratisya k administratoru.")


@dp.message(F.text == BTN_ADD_USER)
async def admin_add_user(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_new_username)
    await message.answer("Vvedi username polzovatelya (mozhno s @ ili bez):", reply_markup=cancel_keyboard())


@dp.message(AdminStates.waiting_new_username)
async def process_new_username(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Otmeneno.", reply_markup=admin_keyboard())
        return
    username = message.text.strip().lstrip("@")
    existing = await db.get_user_by_username(username)
    if existing:
        await message.answer(f"Polzovatel @{username} uzhe est v baze.", reply_markup=admin_keyboard())
    else:
        await db.add_user(username)
        await message.answer(f"Polzovatel @{username} dobavlen!", reply_markup=admin_keyboard())
    await state.clear()


@dp.message(F.text == BTN_SELECT_USER)
async def admin_select_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await db.get_all_users()
    if not users:
        await message.answer("Spisok pust. Snachala dobav polzovateley.")
        return
    buttons = []
    for user in users:
        uid, tg_id, uname = user
        status = "OK" if tg_id else "zhdet"
        buttons.append([InlineKeyboardButton(text=f"[{status}] @{uname}", callback_data=f"select_user:{uid}:{uname}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Vyberi polzovatelya:", reply_markup=kb)


@dp.callback_query(F.data.startswith("select_user:"))
async def user_selected(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    _, uid, uname = call.data.split(":")
    await state.update_data(selected_user_id=int(uid), selected_username=uname)
    await state.set_state(AdminStates.waiting_keys)
    await call.message.answer(f"Vybran: @{uname}\n\nOtprav klyuchi - kazhdiy s novoy stroki.\nStarye klyuchi budut zameneny.", reply_markup=cancel_keyboard())
    await call.answer()


@dp.message(AdminStates.waiting_keys)
async def process_keys(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Otmeneno.", reply_markup=admin_keyboard())
        return
    data = await state.get_data()
    user_id = data["selected_user_id"]
    username = data["selected_username"]
    raw_keys = [k.strip() for k in message.text.strip().split("\n") if k.strip()]
    await db.add_keys(user_id, raw_keys)
    keys_text = "\n\n".join([f"`{k}`" for k in raw_keys])
    await message.answer(f"Klyuchi dlya @{username} sohraneny:\n\n{keys_text}", reply_markup=admin_keyboard(), parse_mode="Markdown")
    user = await db.get_user_by_username(username)
    if user and user[1]:
        try:
            now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            await bot.send_message(user[1], f"Tvoi VPN-klyuchi obnovleny!\nData obnovleniya: {now}\n\nNazhmi 'Moi klyuchi' chtoby posmotret.")
        except Exception:
            pass
    await state.clear()


@dp.message(F.text == BTN_NOTIFY)
async def admin_notification(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_notification)
    await message.answer("Napishi tekst opoveshenia. Bot razoshlet ego vsem polzovatelyam:", reply_markup=cancel_keyboard())


@dp.message(AdminStates.waiting_notification)
async def process_notification(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Otmeneno.", reply_markup=admin_keyboard())
        return
    users = await db.get_all_users()
    sent = 0
    failed = 0
    for user in users:
        uid, tg_id, uname = user
        if tg_id:
            try:
                await bot.send_message(tg_id, f"Soobshenie ot administratora:\n\n{message.text}")
                sent += 1
            except Exception:
                failed += 1
    await message.answer(f"Otpravleno: {sent} chel.\nNe dostavleno: {failed} chel.", reply_markup=admin_keyboard())
    await state.clear()


@dp.message(F.text == BTN_INSTRUCTIONS)
async def admin_instructions(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_instructions)
    await message.answer("Vvedi tekst instrukciy. Polzovateli uvydyat ego v razdele Vazhno:", reply_markup=cancel_keyboard())


@dp.message(AdminStates.waiting_instructions)
async def process_instructions(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Otmeneno.", reply_markup=admin_keyboard())
        return
    await db.save_instructions(message.text)
    await message.answer("Instrukcii sohraneny!", reply_markup=admin_keyboard())
    await state.clear()


@dp.message(F.text == BTN_DELETE_USER)
async def admin_delete_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await db.get_all_users()
    if not users:
        await message.answer("Spisok pust.")
        return
    buttons = []
    for user in users:
        uid, tg_id, uname = user
        buttons.append([InlineKeyboardButton(text=f"Udalit @{uname}", callback_data=f"delete_user:{uid}:{uname}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Kogo udalit?", reply_markup=kb)


@dp.callback_query(F.data.startswith("delete_user:"))
async def confirm_delete(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    _, uid, uname = call.data.split(":")
    await db.delete_user(int(uid))
    await call.message.answer(f"Polzovatel @{uname} udalen.", reply_markup=admin_keyboard())
    await call.answer()


@dp.message(F.text == BTN_MY_KEYS)
async def user_keys(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    user = await db.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Tebya net v spiske. Obratisya k administratoru.")
        return
    keys = await db.get_keys(user[0])
    last_update = await db.get_last_key_update(user[0])
    if not keys:
        await message.answer("U tebya poka net klyuchey. Ozhidai ot administratora.")
        return
    keys_text = "\n\n".join([f"`{k[0]}`" for k in keys])
    update_str = ""
    if last_update:
        dt = datetime.datetime.fromisoformat(last_update)
        update_str = f"\n\nPoslednee obnovlenie: {dt.strftime('%d.%m.%Y v %H:%M')}"
    await message.answer(f"Tvoi VPN-klyuchi:\n\n{keys_text}{update_str}", parse_mode="Markdown")


@dp.message(F.text == BTN_IMPORTANT)
async def user_important(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    result = await db.get_instructions()
    if not result:
        await message.answer("Instrukcii eshhe ne dobavleny administratorom.")
        return
    text, updated_at = result
    dt = datetime.datetime.fromisoformat(updated_at)
    await message.answer(f"Vazhnaya informaciya:\n\n{text}\n\nObnovleno: {dt.strftime('%d.%m.%Y v %H:%M')}")


async def main():
    await db.init_db()
    print("Bot zapushhen!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
