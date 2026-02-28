import asyncio
import logging
import os
import uuid
from typing import Dict
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
MANAGER_USERNAME = "@Donatovgift_manager"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния FSM
class CreateDeal(StatesGroup):
    gift = State()
    currency = State()
    price = State()
    requisites = State()


# Хранилища данных
deals: Dict[str, dict] = {}
admins: set[int] = {ADMIN_ID}
user_successful_deals: Dict[int, int] = {}
user_deals_count: Dict[int, int] = {}
DEAL_TIMEOUT = 3600


def is_admin(user_id: int) -> bool:
    return user_id in admins


async def create_deal_id() -> str:
    """Генерация уникального ID сделки"""
    for _ in range(50):
        deal_id = str(uuid.uuid4())[:8].upper()
        if deal_id not in deals:
            return deal_id
    raise ValueError("Не удалось создать уникальный ID")


async def send_log_to_admin(user_id: int, username: str, action: str, extra: str = ""):
    """Отправка лога админу"""
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📊 <b>{action}</b>\n👤 <code>{user_id}</code>\n📝 @{username or 'нет'}\n{extra}",
            parse_mode="HTML"
        )
    except Exception:
        pass


def get_main_menu(user_id: int) -> InlineKeyboardMarkup:
    """Главное меню с статистикой"""
    success = user_successful_deals.get(user_id, 0)
    total = user_deals_count.get(user_id, 0)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💼 Создать сделку", callback_data="create_deal"))
    builder.add(InlineKeyboardButton(text=f"✅ {success}/{total}", callback_data="my_stats"))

    if is_admin(user_id):
        builder.add(InlineKeyboardButton(text="👑 АДМИН", callback_data="admin_panel"))

    builder.add(InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/Donatovgift_manager"))
    builder.add(InlineKeyboardButton(text="⭐ Отзывы", url="https://t.me/Donatovgifts_review"))
    builder.adjust(1, repeat=True)
    return builder.as_markup()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик /start с deep linking"""
    args = message.text.split(maxsplit=1)

    if len(args) > 1 and args[1].startswith("deal_"):
        deal_id = args[1].replace("deal_", "")
        await show_payment_window(message, deal_id)
        return

    await send_log_to_admin(message.from_user.id, message.from_user.username, "Старт бота")
    await message.answer(
        "🎁 <b>Donatovgift — безопасная торговля</b>",
        reply_markup=get_main_menu(message.from_user.id),
        parse_mode="HTML"
    )


async def show_payment_window(message: Message, deal_id: str):
    """Окно оплаты при переходе по ссылке"""
    if deal_id not in deals:
        await message.answer("❌ Сделка не найдена", reply_markup=get_main_menu(message.from_user.id))
        return

    deal = deals[deal_id]
    if deal.get('paid', False):
        await message.answer("✅ Сделка выполнена", reply_markup=get_main_menu(message.from_user.id))
        return

    # Устанавливаем покупателя
    deals[deal_id]['current_buyer'] = message.from_user.id
    seller_success = user_successful_deals.get(deal['seller_id'], 0)

    symbol = "₽" if deal['currency'] == "Рубли" else "⭐"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 ОПЛАТИТЬ СЕЙЧАС", callback_data=f"pay_now_{deal_id}"))

    if is_admin(message.from_user.id):
        builder.row(InlineKeyboardButton(text="🔥 НАКРУТИТЬ", callback_data=f"admin_pay_{deal_id}"))

    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu"))

    text = f"""💳 <b>ОПЛАТА СДЕЛКИ #{deal_id}</b>

📦 <b>{deal['gift']}</b>
💰 <b>{deal['price']} {symbol}</b>
💳 <b>{deal['currency']}</b>
✅ <b>Продавец: {seller_success} успехов</b>

<i>🔥 Нажмите ОПЛАТИТЬ СЕЙЧАС</i>"""

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("pay_now_"))
async def instant_payment(callback: CallbackQuery):
    """Мгновенная оплата кнопкой"""
    deal_id = callback.data.replace("pay_now_", "")
    await callback.answer("✅ Оплата принята!")
    await process_deal_payment(callback.from_user, deal_id)
    await callback.message.edit_text(
        "✅ <b>Оплата прошла!</b>\n⏳ Ожидайте NFT от продавца",
        reply_markup=get_main_menu(callback.from_user.id),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("admin_pay_"))
async def admin_fake_payment(callback: CallbackQuery):
    """Админская накрутка оплаты"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return

    deal_id = callback.data.replace("admin_pay_", "")
    await process_deal_payment(callback.from_user, deal_id)
    await callback.answer("🔥 Накручено!")


async def process_deal_payment(user, deal_id: str):
    """Обработка оплаты с уведомлением продавцу"""
    if deal_id not in deals or deals[deal_id].get('paid', False):
        return

    deal = deals[deal_id]
    deals[deal_id]['paid'] = True
    deals[deal_id]['buyer_id'] = user.id
    deals[deal_id]['buyer_username'] = user.username

    # +1 успех продавцу
    seller_id = deal['seller_id']
    user_successful_deals[seller_id] = user_successful_deals.get(seller_id, 0) + 1

    symbol = "₽" if deal['currency'] == "Рубли" else "⭐"

    # 🔥 ТОЧНОЕ УВЕДОМЛЕНИЕ ПРОДАВЦУ
    seller_text = f"""💰 <b>Пользователь переслал деньги!</b>

Для успешной сделки, вам необходимо передать NFT менеджеру {MANAGER_USERNAME}
<b>!Строго ему - критически важное правило!</b>

━━━━━━━━━━━━━━━━━━━
🆔 <b>Сделка #{deal_id}</b>
🎁 <b>{deal['gift']}</b>
💰 <b>{deal['price']} {symbol}</b>
💳 <b>Реквизиты:</b> <code>{deal['requisites']}</code>

✅ Теперь у вас <b>{user_successful_deals[seller_id]} успехов</b>"""

    await bot.send_message(seller_id, seller_text, parse_mode="HTML")
    await send_log_to_admin(user.id, user.username, f"ОПЛАТА {deal_id}", deal['gift'])


# FSM создание сделки
@dp.callback_query(F.data == "create_deal")
async def create_deal_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания сделки"""
    if not is_admin(callback.from_user.id):
        count = user_deals_count.get(callback.from_user.id, 0)
        if count >= 5:
            await callback.answer("⏳ Лимит 5 сделок", show_alert=True)
            return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await callback.message.edit_text(
        "🎁 <b>Шаг 1/4 — Подарок</b>\n\n📦 Название подарка:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.gift)
    await callback.answer()


@dp.callback_query(F.data == "cancel_deal")
async def cancel_deal(callback: CallbackQuery, state: FSMContext):
    """Отмена создания сделки"""
    await state.clear()
    await callback.message.edit_text("❌ Создание отменено", reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()


@dp.message(CreateDeal.gift)
async def process_gift(message: Message, state: FSMContext):
    """Шаг 1 FSM"""
    gift = message.text.strip()
    if len(gift) < 3 or len(gift) > 100:
        await message.answer("❌ 3-100 символов")
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
    """Шаг 2 FSM"""
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
    """Шаг 3 FSM"""
    price = message.text.strip().replace(" ", "")
    if not price.isdigit() or not (1 <= int(price) <= 100000):
        await message.answer("❌ Цена 1-100000")
        return

    await state.update_data(price=price)
    data = await state.get_data()
    req_type = "карта" if data['currency'] == "Рубли" else "@username"

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
    """Завершение создания сделки"""
    await state.update_data(requisites=message.text.strip())
    data = await state.get_data()

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

    # 🔥 КНОПКА ПЕРЕСЫЛКИ
    share_text = f"Сделка #{deal_id}\n{data['gift']} за {data['price']} {'₽' if data['currency'] == 'Рубли' else '⭐'}\n🔗 https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📤 ПЕРЕСЛАТЬ ПОКУПАТЕЛЮ", switch_inline_query=share_text))
    builder.row(InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu"))

    symbol = "₽" if data['currency'] == "Рубли" else "⭐"
    text = f"""✅ <b>Сделка создана #{deal_id}</b>

🎁 {data['gift']}
💰 {data['price']} {symbol}

📤 <b>ПЕРЕСЛАТЬ:</b> Нажмите кнопку выше!"""

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await send_log_to_admin(message.from_user.id, message.from_user.username, f"СОЗДАНА {deal_id}")
    await state.clear()


# Остальные обработчики
@dp.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery):
    await callback.message.edit_text("🏠 Главное меню", reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()


@dp.message(Command("setdeals"))
async def set_deals(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("❌ /setdeals 90")
    try:
        count = int(args[1])
        user_deals_count[message.from_user.id] = count
        await message.answer(f"✅ Сделок: {count}")
    except ValueError:
        await message.answer("❌ Число!")


@dp.message(Command("set_success"))
async def set_success(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("❌ /set_success 90")
    try:
        count = int(args[1])
        user_successful_deals[message.from_user.id] = count
        await message.answer(f"✅ Успехов: {count}")
    except ValueError:
        await message.answer("❌ Число!")


@dp.message(Command("stats"))
async def show_stats(message: Message):
    success = user_successful_deals.get(message.from_user.id, 0)
    total = user_deals_count.get(message.from_user.id, 0)
    await message.answer(f"📊 Успехов: {success}\n📦 Сделок: {total}")


async def cleanup_loop():
    """Очистка просроченных сделок"""
    while True:
        await asyncio.sleep(300)
        current_time = asyncio.get_event_loop().time()
        expired = [did for did, deal in list(deals.items()) if current_time - deal.get('created_at', 0) > DEAL_TIMEOUT]
        for did in expired:
            del deals[did]


async def main():
    asyncio.create_task(cleanup_loop())
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
