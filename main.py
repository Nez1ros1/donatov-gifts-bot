import asyncio
import os
import random
import string
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import (Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, 
                           InlineKeyboardButton, LabeledPrice, PreCheckoutQuery)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8520179075:AAGJvZJDVkdUJ2K0jGnMiID41YAri-_1yhI'
MANAGER = "@Donatovgift_manager"
REVIEWS_URL = "https://donatov.net/feedback"
SITE_URL = "https://donatov.net/"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- ХРАНИЛИЩА ДАННЫХ ---
DEALS = {}
PAYMENT_ACCESS = set() 
USER_STATS = {}

def get_stats(uid):
    if uid not in USER_STATS:
        # Базовая статистика по нулям + сохранение языка (по умолчанию 'ru')
        USER_STATS[uid] = {
            'total_deals': 0,
            'success_deals': 0,
            'volume': 0.0,
            'rating': 0.0,
            'lang': 'ru' 
        }
    return USER_STATS[uid]

# --- FSM СОСТОЯНИЯ ---
class DealCreate(StatesGroup):
    curr = State()
    amount = State()
    item = State()
    reqs = State()

class EchoState(StatesGroup):
    waiting_for_text = State()

class TicketState(StatesGroup):
    waiting_for_ticket = State()

class ReqState(StatesGroup):
    waiting_for_req = State()

# --- СЛОВАРИ ПЕРЕВОДОВ ---
TEXTS = {
    'ru': {
        'start_text': """Добро пожаловать в Donatov Gifts

<blockquote>DonatovGifts — Ваша безопасность в мире цифровых активов.

Мы предоставляем профессиональный сервис для проведения сделок с игровыми ценностями, NFT и аккаунтами. Наша платформа гарантирует сохранность средств до момента подтверждения выполнения обязательств обеими сторонами.</blockquote>

Безопасные сделки с гарантией

🛡 Защита от мошенников
💰 Автоматическое удержание средств
📝 Прозрачная статистика
🎯 Поддержка 24/7
📊 История сделок""",
        'btn_make_deal': "📝 Создать сделку",
        'btn_my_deals': "📋 Мои сделки",
        'btn_verification': "🔐 Верификация",
        'btn_requisites': "💳 Реквизиты",
        'btn_lang': "🌐 Язык",
        'btn_referrals': "🔗 Рефералы",
        'btn_about': "ℹ️ Подробнее",
        'btn_tickets': "✉️ Обращения",
        'btn_support': "📞 Поддержка",
        'btn_back': "⬅️ Назад",
        'lang_changed': "Язык успешно изменен!",
        'my_deals': "У вас {success_deals} успешных сделок",
        'about_text': f"🌐 Наш официальный сайт: {SITE_URL}"
    },
    'en': {
        'start_text': """Welcome to Donatov Gifts

<blockquote>DonatovGifts — Your security in the world of digital assets.

We provide a professional service for conducting transactions with game valuables, NFTs, and accounts. Our platform guarantees the safety of funds until both parties confirm the fulfillment of obligations.</blockquote>

Safe deals with a guarantee

🛡 Protection against scammers
💰 Automatic funds retention
📝 Transparent statistics
🎯 24/7 Support
📊 Transaction history""",
        'btn_make_deal': "📝 Create Deal",
        'btn_my_deals': "📋 My Deals",
        'btn_verification': "🔐 Verification",
        'btn_requisites': "💳 Requisites",
        'btn_lang': "🌐 Language",
        'btn_referrals': "🔗 Referrals",
        'btn_about': "ℹ️ About",
        'btn_tickets': "✉️ Tickets",
        'btn_support': "📞 Support",
        'btn_back': "⬅️ Back",
        'lang_changed': "Language changed successfully!",
        'my_deals': "You have {success_deals} successful deals",
        'about_text': f"🌐 Our official website: {SITE_URL}"
    }
}

# --- КЛАВИАТУРЫ ---
def get_main_kb(lang='ru'):
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t['btn_make_deal'], callback_data="make_deal")],
        [InlineKeyboardButton(text=t['btn_my_deals'], callback_data="my_deals"), 
         InlineKeyboardButton(text=t['btn_verification'], callback_data="v_stats")],
        [InlineKeyboardButton(text=t['btn_requisites'], callback_data="requisites"), 
         InlineKeyboardButton(text=t['btn_lang'], callback_data="lang")],
        [InlineKeyboardButton(text=t['btn_referrals'], callback_data="referrals"), 
         InlineKeyboardButton(text=t['btn_about'], callback_data="about")],
        [InlineKeyboardButton(text=t['btn_tickets'], callback_data="tickets")],
        [InlineKeyboardButton(text=t['btn_support'], url=f"https://t.me/{MANAGER[1:]}")]
    ])

def get_req_kb(lang='ru'):
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Изменить TON" if lang == 'ru' else "💎 Change TON", callback_data="req_change")],
        [InlineKeyboardButton(text="💳 Изменить RUB карту" if lang == 'ru' else "💳 Change RUB Card", callback_data="req_change")],
        [InlineKeyboardButton(text="💵 Изменить USD карту" if lang == 'ru' else "💵 Change USD Card", callback_data="req_change")],
        [InlineKeyboardButton(text="🌐 Изменить реквизиты" if lang == 'ru' else "🌐 Change Requisites", callback_data="req_change")],
        [InlineKeyboardButton(text="💰 Пополнить баланс" if lang == 'ru' else "💰 Deposit", callback_data="req_deposit")],
        [InlineKeyboardButton(text="💸 Вывод средств" if lang == 'ru' else "💸 Withdraw", callback_data="req_withdraw")],
        [InlineKeyboardButton(text=t['btn_back'], callback_data="home")]
    ])

# --- ТЕКСТЫ, КОТОРЫЕ ГЕНЕРИРУЮТСЯ ДИНАМИЧЕСКИ ---
def get_verification_text(uid, lang='ru'):
    st = get_stats(uid)
    if lang == 'ru':
        return f"""📊 <b>Ваша статистика:</b>
• Всего создано сделок: {st['total_deals']}
• Успешных сделок: {st['success_deals']}
• Общий объем: {st['volume']:g}
• Рейтинг продавца: {st['rating']} ⭐️
• Рефералов: 0
• <b>Верификация не пройдена ❌</b>
• Баланс: 0 ₽\n
<b>Что дает премиум-статус:</b>
• Верификация продавца - знак доверия
• Гарант сделок - защита от мошенников
• Приоритетная поддержка - быстрые ответы"""
    else:
        return f"""📊 <b>Your Statistics:</b>
• Total deals created: {st['total_deals']}
• Successful deals: {st['success_deals']}
• Total volume: {st['volume']:g}
• Seller rating: {st['rating']} ⭐️
• Referrals: 0
• <b>Verification not passed ❌</b>
• Balance: 0\n
<b>Premium benefits:</b>
• Seller verification - a sign of trust
• Deal guarantor - protection against scammers
• Priority support - fast replies"""

def get_req_text(lang='ru'):
    if lang == 'ru':
        return """💳 <b>Управление реквизитами</b>\n\n• TON: не указан\n• Карта RUB: не указан\n• Карта USD: не указан\n\n💰 <b>Ваши балансы:</b>\n• TON: 0.00\n• RUB: 0.00\n• USD: 0.00\n• Stars: 0.00\n\nВыберите действие:"""
    else:
        return """💳 <b>Requisites Management</b>\n\n• TON: not set\n• RUB Card: not set\n• USD Card: not set\n\n💰 <b>Your Balances:</b>\n• TON: 0.00\n• RUB: 0.00\n• USD: 0.00\n• Stars: 0.00\n\nChoose an action:"""

# --- СЕКРЕТНЫЕ КОМАНДЫ ДЛЯ СКРИНШОТОВ И НАКРУТКИ ---
@router.message(Command("aboba"))
async def cmd_aboba(m: Message, state: FSMContext):
    await state.set_state(EchoState.waiting_for_text)
    await m.answer("Напишите текст")

@router.message(EchoState.waiting_for_text)
async def process_aboba(m: Message, state: FSMContext):
    await m.answer(m.text)
    await state.clear()

@router.message(Command("deals"))
async def cmd_fake_deals(m: Message, command: CommandObject):
    if command.args and command.args.isdigit():
        st = get_stats(m.from_user.id)
        st['total_deals'] = int(command.args)
        await m.answer(f"✅ Общее кол-во сделок изменено на: <b>{st['total_deals']}</b>")

@router.message(Command("ddeals"))
async def cmd_fake_ddeals(m: Message, command: CommandObject):
    if command.args and command.args.isdigit():
        st = get_stats(m.from_user.id)
        st['success_deals'] = int(command.args)
        await m.answer(f"✅ Кол-во успешных сделок изменено на: <b>{st['success_deals']}</b>")

@router.message(Command("payment"))
async def pay_cmd(m: Message):
    PAYMENT_ACCESS.add(m.from_user.id)
    await m.answer("✅ <b>Платежный доступ активирован (режим симуляции оплат).</b>\nТеперь при нажатии «Оплатить товар» оплата пройдет успешно.")

# --- ЛОГИКА ОПЛАТЫ ---
async def process_successful_payment(message_or_query, d_id: str, deal: dict):
    seller_id = deal['owner_id']
    st = get_stats(seller_id)
    st['success_deals'] += 1
    try:
        st['volume'] += float(deal['amount'].replace(',', '.'))
    except ValueError: pass 

    seller_msg = (
        f"🔔 <b>Покупатель оплатил товар, передайте товар строго менеджеру {MANAGER}</b>\n\n"
        f"<i>Сделка #{d_id}. Как только менеджер подтвердит получение, средства будут зачислены на: <code>{deal['reqs']}</code></i>"
    )
    try: 
        await bot.send_message(seller_id, seller_msg)
    except: pass
    
    success_text = "🎉 <b>Оплата подтверждена!</b> Средства заморожены на счету гаранта."
    if isinstance(message_or_query, CallbackQuery):
        await message_or_query.message.answer(success_text)
    else:
        await message_or_query.answer(success_text)

@router.callback_query(F.data.startswith("pay_"))
async def handle_pay(c: CallbackQuery):
    d_id = c.data.split("_")[1]
    deal = DEALS.get(d_id)
    if not deal:
        await c.answer("Сделка не найдена", show_alert=True)
        return

    if c.from_user.id in PAYMENT_ACCESS:
        await process_successful_payment(c, d_id, deal)
        await c.answer("Оплата симулирована успешно.")
    else:
        if deal['curr'] == "STARS":
            try:
                amount_stars = int(float(deal['amount'])) 
                prices = [LabeledPrice(label=f"Сделка #{d_id}", amount=amount_stars)]
                await bot.send_invoice(
                    chat_id=c.from_user.id, title=f"Сделка #{d_id}",
                    description=f"Оплата товара: {deal['item']}", payload=f"deal_{d_id}",
                    provider_token="", currency="XTR", prices=prices
                )
            except ValueError:
                await c.message.answer("⚠️ Ошибка суммы / Amount error.")
            await c.answer()
        elif deal['curr'] == "RUB":
            sbp_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 Оплатить через СБП", url="https://qr.nspk.ru/")]])
            await c.message.answer(f"💳 <b>Оплата по СБП</b>\n\nСумма: <b>{deal['amount']} RUB</b>\nНазначение: Сделка #{d_id}", reply_markup=sbp_kb)
            await c.answer()
        else:
            await c.answer(f"Оплата через менеджера.", show_alert=True)

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def successful_payment_handler(m: Message):
    payload = m.successful_payment.invoice_payload
    if payload.startswith("deal_"):
        d_id = payload.split("_")[1]
        deal = DEALS.get(d_id)
        if deal: await process_successful_payment(m, d_id, deal)

# --- СОЗДАНИЕ СДЕЛКИ ---
@router.callback_query(F.data == "make_deal")
async def start_create(c: CallbackQuery, state: FSMContext):
    await state.set_state(DealCreate.curr)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 RUB", callback_data="c_RUB"), InlineKeyboardButton(text="💵 USD", callback_data="c_USD"), InlineKeyboardButton(text="⭐️ Stars", callback_data="c_STARS")],
        [InlineKeyboardButton(text="🇺🇦 UAH (Гривны)", callback_data="c_UAH"), InlineKeyboardButton(text="💎 TON", callback_data="c_TON")]
    ])
    lang = get_stats(c.from_user.id)['lang']
    msg = "Выберите валюту сделки:" if lang == 'ru' else "Choose deal currency:"
    await c.message.answer(msg, reply_markup=kb)
    await c.answer()

@router.callback_query(F.data.startswith("c_"))
async def set_cur(c: CallbackQuery, state: FSMContext):
    await state.update_data(curr=c.data.split("_")[1])
    await state.set_state(DealCreate.amount)
    lang = get_stats(c.from_user.id)['lang']
    msg = "Введите сумму сделки:" if lang == 'ru' else "Enter deal amount:"
    await c.message.answer(msg)
    await c.answer()

@router.message(DealCreate.amount)
async def set_amt(m: Message, state: FSMContext):
    await state.update_data(amount=m.text)
    await state.set_state(DealCreate.item)
    lang = get_stats(m.from_user.id)['lang']
    msg = "Введите название товара (NFT):" if lang == 'ru' else "Enter item name (NFT):"
    await m.answer(msg)

@router.message(DealCreate.item)
async def set_itm(m: Message, state: FSMContext):
    await state.update_data(item=m.text)
    await state.set_state(DealCreate.reqs)
    lang = get_stats(m.from_user.id)['lang']
    msg = "Укажите ваши реквизиты:" if lang == 'ru' else "Enter your requisites for withdrawal:"
    await m.answer(msg)

@router.message(DealCreate.reqs)
async def finish(m: Message, state: FSMContext):
    await state.update_data(reqs=m.text)
    data = await state.get_data()
    d_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    owner_nick = m.from_user.username or m.from_user.first_name
    DEALS[d_id] = {"owner_id": m.from_user.id, "owner_nick": owner_nick, **data}
    
    st = get_stats(m.from_user.id)
    st['total_deals'] += 1
    lang = st['lang']
    
    bot_me = await bot.get_me()
    link = f"https://t.me/{bot_me.username}?start=deal_{d_id}"
    
    if lang == 'ru':
        text = f"✅ <b>Сделка #{d_id} готова!</b>\n\n📦 Товар: {data['item']}\n💰 Сумма: {data['amount']} {data['curr']}\n💳 Вывод на: {data['reqs']}\n\n🔗 <b>Ссылка для покупателя:</b>\n{link}"
    else:
        text = f"✅ <b>Deal #{d_id} created!</b>\n\n📦 Item: {data['item']}\n💰 Amount: {data['amount']} {data['curr']}\n💳 Withdrawal to: {data['reqs']}\n\n🔗 <b>Link for buyer:</b>\n{link}"

    await m.answer(text, reply_markup=get_main_kb(lang))
    await state.clear()

# --- МЕНЮ И КНОПКИ ---
@router.callback_query(F.data == "my_deals")
async def show_my_deals(c: CallbackQuery):
    st = get_stats(c.from_user.id)
    lang = st['lang']
    text = TEXTS[lang]['my_deals'].format(success_deals=st['success_deals'])
    await c.message.answer(text, reply_markup=get_main_kb(lang))
    await c.answer()

@router.callback_query(F.data == "lang")
async def change_language(c: CallbackQuery):
    lang = get_stats(c.from_user.id)['lang']
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en")],
        [InlineKeyboardButton(text=TEXTS[lang]['btn_back'], callback_data="home")]
    ])
    await c.message.answer("Выберите язык / Choose language:", reply_markup=kb)
    await c.answer()

@router.callback_query(F.data.startswith("setlang_"))
async def set_lang_action(c: CallbackQuery):
    selected_lang = c.data.split("_")[1] # 'ru' или 'en'
    st = get_stats(c.from_user.id)
    st['lang'] = selected_lang # Сохраняем язык пользователя
    
    # Отправляем уведомление на новом языке
    await c.answer(TEXTS[selected_lang]['lang_changed'], show_alert=True)
    # Выдаем переведенное меню
    await c.message.answer(TEXTS[selected_lang]['start_text'], reply_markup=get_main_kb(selected_lang))

@router.callback_query(F.data == "about")
async def show_about(c: CallbackQuery):
    lang = get_stats(c.from_user.id)['lang']
    await c.message.answer(TEXTS[lang]['about_text'], reply_markup=get_main_kb(lang))
    await c.answer()

@router.callback_query(F.data == "v_stats")
async def v_stats(c: CallbackQuery):
    lang = get_stats(c.from_user.id)['lang']
    await c.message.answer(get_verification_text(c.from_user.id, lang), reply_markup=get_main_kb(lang))
    await c.answer()

@router.callback_query(F.data == "requisites")
async def show_reqs(c: CallbackQuery):
    lang = get_stats(c.from_user.id)['lang']
    await c.message.answer(get_req_text(lang), reply_markup=get_req_kb(lang))
    await c.answer()

@router.callback_query(F.data == "req_withdraw")
async def req_withdraw(c: CallbackQuery):
    lang = get_stats(c.from_user.id)['lang']
    msg = "❌ Вы не можете вывести средства, мин 100 руб." if lang == 'ru' else "❌ Cannot withdraw, min amount is 100 RUB."
    await c.answer(msg, show_alert=True)

@router.callback_query(F.data == "req_change")
async def req_change(c: CallbackQuery, state: FSMContext):
    lang = get_stats(c.from_user.id)['lang']
    await state.set_state(ReqState.waiting_for_req)
    msg = "Укажите ваши реквизиты для вывода:" if lang == 'ru' else "Enter your requisites:"
    await c.message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=TEXTS[lang]['btn_back'], callback_data="home")]]))
    await c.answer()

@router.message(ReqState.waiting_for_req)
async def req_saved(m: Message, state: FSMContext):
    lang = get_stats(m.from_user.id)['lang']
    msg = "✅ Реквизиты сохранены и отправлены на модерацию." if lang == 'ru' else "✅ Requisites saved and sent for moderation."
    await m.answer(msg, reply_markup=get_main_kb(lang))
    await state.clear()

@router.callback_query(F.data == "req_deposit")
async def req_deposit(c: CallbackQuery):
    lang = get_stats(c.from_user.id)['lang']
    msg = "Функция пополнения временно недоступна." if lang == 'ru' else "Deposit is temporarily unavailable."
    await c.answer(msg, show_alert=True)

@router.callback_query(F.data == "referrals")
async def show_refs(c: CallbackQuery):
    lang = get_stats(c.from_user.id)['lang']
    bot_me = await bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{c.from_user.id}"
    if lang == 'ru':
        msg = f"🔗 <b>Ваша реферальная ссылка:</b>\n{ref_link}\n\nПриглашайте друзей и получайте бонусы!"
    else:
        msg = f"🔗 <b>Your referral link:</b>\n{ref_link}\n\nInvite friends and get bonuses!"
    await c.message.answer(msg, reply_markup=get_main_kb(lang))
    await c.answer()

@router.callback_query(F.data == "tickets")
async def open_ticket(c: CallbackQuery, state: FSMContext):
    lang = get_stats(c.from_user.id)['lang']
    await state.set_state(TicketState.waiting_for_ticket)
    msg = "✍️ Напишите здесь ваше обращение:" if lang == 'ru' else "✍️ Write your message here:"
    await c.message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=TEXTS[lang]['btn_back'], callback_data="home")]]))
    await c.answer()

@router.message(TicketState.waiting_for_ticket)
async def process_ticket(m: Message, state: FSMContext):
    lang = get_stats(m.from_user.id)['lang']
    msg = "✅ Ваше обращение отправлено." if lang == 'ru' else "✅ Your ticket has been sent."
    await m.answer(msg, reply_markup=get_main_kb(lang))
    await state.clear()

# --- СТАРТ ---
@router.message(CommandStart())
async def start(m: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    lang = get_stats(m.from_user.id)['lang']
    
    if command and command.args and command.args.startswith("deal_"):
        d_id = command.args.split("_")[1]
        if d_id in DEALS:
            d = DEALS[d_id]
            if m.from_user.id == d['owner_id']:
                msg = "❌ Нельзя оплатить собственную сделку." if lang == 'ru' else "❌ You cannot pay for your own deal."
                await m.answer(msg, reply_markup=get_main_kb(lang))
                return
            
            if lang == 'ru':
                deal_text = f"🛡 <b>Безопасная Сделка #{d_id}</b>\n\n👤 Продавец: @{d.get('owner_nick', 'Скрыт')}\n📦 Товар: {d['item']}\n💰 Сумма к оплате: <b>{d['amount']} {d['curr']}</b>\n📝 Реквизиты продавца: <code>{d.get('reqs', 'Не указано')}</code>\n\n<i>Средства на удержании.</i>"
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить товар", callback_data=f"pay_{d_id}")],
                    [InlineKeyboardButton(text="🏠 В главное меню", callback_data="home")]
                ])
            else:
                deal_text = f"🛡 <b>Safe Deal #{d_id}</b>\n\n👤 Seller: @{d.get('owner_nick', 'Hidden')}\n📦 Item: {d['item']}\n💰 Amount to pay: <b>{d['amount']} {d['curr']}</b>\n📝 Seller requisites: <code>{d.get('reqs', 'Not specified')}</code>\n\n<i>Funds on hold.</i>"
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Pay for item", callback_data=f"pay_{d_id}")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="home")]
                ])
            await m.answer(deal_text, reply_markup=kb)
            return

    await m.answer(TEXTS[lang]['start_text'], reply_markup=get_main_kb(lang))

@router.callback_query(F.data == "home")
async def h(c: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = get_stats(c.from_user.id)['lang']
    await c.message.answer(TEXTS[lang]['start_text'], reply_markup=get_main_kb(lang))
    await c.answer()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
