import asyncio
import logging
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import aiosqlite
from geopy.geocoders import Nominatim
from kerykeion import AstrologicalSubject

# ==========================================
# 1. КОНФИГУРАЦИЯ И ДАННЫЕ
# ==========================================
BOT_TOKEN = "8625183654:AAHbJFRw58gT9lXVeIXgLs7ryH_H8yDmyBk"
DB_NAME = "astrotarot.db"

# Пример структуры Таро (1 карта для примера, в реальности здесь 78 карт)
TAROT_DECK = {
    "the_fool": {
        "name": "Шут (0)",
        "upright": "Новые начинания, спонтанность, вера в будущее, свобода духа.",
        "reversed": "Наивность, безрассудство, неоправданный риск.",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/9/90/RWS_Tarot_00_Fool.jpg"
    },
    "the_magician": {
        "name": "Маг (I)",
        "upright": "Мастерство, инициатива, осознанные действия, концентрация.",
        "reversed": "Манипуляции, скрытые мотивы, неиспользованный потенциал.",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/d/de/RWS_Tarot_01_Magician.jpg"
    },
    "high_priestess": {
        "name": "Жрица (II)",
        "upright": "Интуиция, тайные знания, подсознание, пассивность.",
        "reversed": "Скрытые враги, игнорирование внутреннего голоса, поверхностность.",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/8/88/RWS_Tarot_02_High_Priestess.jpg"
    }
}

# Пример интерпретаций (1 знак для примера)
ASTRO_INTERPRETATIONS = {
    "Mars": {
        "Scorpio": "сильная воля, страстность, магнетизм и склонность к глубоким трансформациям.",
        "Aries": "импульсивность, лидерские качества, взрывной темперамент."
    },
    "Sun": {
        "Leo": "яркость, харизма, потребность в признании и творческое самовыражение."
    }
}


# ==========================================
# 2. БАЗА ДАННЫХ И СОСТОЯНИЯ (FSM)
# ==========================================
class ProfileForm(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_city = State()


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                birth_date TEXT,
                birth_time TEXT,
                city TEXT
            )
        """)
        await db.commit()


# ==========================================
# 3. КЛАВИАТУРЫ
# ==========================================
def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню с навигацией и кнопкой поддержки на 4-й позиции."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔮 Расклад Таро", callback_data="menu_tarot")],
        [InlineKeyboardButton(text="✨ Моя Натальная карта", callback_data="menu_natal")],
        [InlineKeyboardButton(text="⚙️ Настройки профиля", callback_data="menu_profile")],
        [InlineKeyboardButton(text="🎧 Поддержка", url="https://t.me/Dutsi18")]
    ])


def get_tarot_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Карта дня", callback_data="tarot_day")],
        [InlineKeyboardButton(text="🎴 Расклад на 3 карты", callback_data="tarot_three")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]
    ])


# ==========================================
# 4. БИЗНЕС-ЛОГИКА (АСТРОЛОГИЯ И ТАРО)
# ==========================================
def pull_tarot_cards(count: int = 1) -> list:
    """Перемешивание и вытягивание карт."""
    keys = list(TAROT_DECK.keys())
    random.shuffle(keys)  # Механика перемешивания
    drawn_keys = keys[:count]

    results = []
    for key in drawn_keys:
        card = TAROT_DECK[key]
        is_reversed = random.choice([True, False])
        results.append({
            "name": card["name"],
            "state": "Перевернутая" if is_reversed else "Прямая",
            "meaning": card["reversed"] if is_reversed else card["upright"]
        })
    return results


def calculate_natal_chart(name: str, year: int, month: int, day: int, hour: int, minute: int, city: str):
    """
    Тяжелая синхронная функция. Ищет координаты через Geopy и считает карту через Kerykeion.
    Обернута в to_thread в хендлере.
    """
    geolocator = Nominatim(user_agent="astro_bot_tg")
    location = geolocator.geocode(city)
    if not location:
        raise ValueError("Город не найден.")

    # Расчет Kerykeion
    subject = AstrologicalSubject(name, year, month, day, hour, minute, city, location.latitude, location.longitude)

    # Сбор данных
    planets = {
        "Солнце": (subject.sun.sign, ASTRO_INTERPRETATIONS.get("Sun", {}).get(subject.sun.sign, "нет данных")),
        "Луна": (subject.moon.sign, "нет данных"),
        "Меркурий": (subject.mercury.sign, "нет данных"),
        "Венера": (subject.venus.sign, "нет данных"),
        "Марс": (subject.mars.sign, ASTRO_INTERPRETATIONS.get("Mars", {}).get(subject.mars.sign, "нет данных")),
        "Асцендент": (subject.first_house.sign, "нет данных")
    }
    return planets


# ==========================================
# 5. ХЕНДЛЕРЫ (ROUTERS)
# ==========================================
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот для работы с Таро и вычисления Натальной карты.",
        reply_markup=get_main_menu()
    )


@router.callback_query(F.data == "menu_main")
async def back_to_main(call: CallbackQuery):
    await call.message.edit_text("Главное меню:", reply_markup=get_main_menu())


# --- БЛОК ТАРО ---
@router.callback_query(F.data == "menu_tarot")
async def tarot_menu(call: CallbackQuery):
    await call.message.edit_text("Выберите тип расклада:", reply_markup=get_tarot_menu())


@router.callback_query(F.data == "tarot_day")
async def tarot_card_of_day(call: CallbackQuery):
    card = pull_tarot_cards(1)[0]
    text = f"🃏 **Ваша Карта дня:** {card['name']} ({card['state']})\n\n" \
           f"📖 **Значение:** {card['meaning']}"
    await call.message.answer(text)
    await call.answer()


@router.callback_query(F.data == "tarot_three")
async def tarot_three_cards(call: CallbackQuery):
    cards = pull_tarot_cards(3)
    positions = ["Прошлое", "Настоящее", "Будущее"]
    text = "🎴 **Расклад на 3 карты:**\n\n"
    for pos, card in zip(positions, cards):
        text += f"*{pos}:* {card['name']} ({card['state']})\n" \
                f"Значение: {card['meaning']}\n\n"
    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


# --- БЛОК ПРОФИЛЯ И АСТРОЛОГИИ ---
@router.callback_query(F.data == "menu_profile")
async def start_profile_setup(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите вашу дату рождения в формате ДД.ММ.ГГГГ:")
    await state.set_state(ProfileForm.waiting_for_date)
    await call.answer()


@router.message(ProfileForm.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    await state.update_data(birth_date=message.text)
    await message.answer("Отлично. Теперь введите точное время рождения (ЧЧ:ММ):")
    await state.set_state(ProfileForm.waiting_for_time)


@router.message(ProfileForm.waiting_for_time)
async def process_time(message: Message, state: FSMContext):
    await state.update_data(birth_time=message.text)
    await message.answer("И последнее — введите город рождения:")
    await state.set_state(ProfileForm.waiting_for_city)


@router.message(ProfileForm.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    user_data = await state.get_data()
    city = message.text

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, birth_date, birth_time, city) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
            birth_date=excluded.birth_date, birth_time=excluded.birth_time, city=excluded.city
        """, (message.from_user.id, user_data['birth_date'], user_data['birth_time'], city))
        await db.commit()

    await message.answer("Профиль сохранен! Теперь вы можете рассчитать натальную карту.", reply_markup=get_main_menu())
    await state.clear()


@router.callback_query(F.data == "menu_natal")
async def get_natal_chart(call: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT birth_date, birth_time, city FROM users WHERE user_id = ?",
                              (call.from_user.id,)) as cursor:
            row = await cursor.fetchone()

    if not row:
        await call.message.answer("Сначала заполните профиль в настройках.")
        await call.answer()
        return

    b_date, b_time, city = row
    await call.message.edit_text("⏳ Рассчитываю эфемериды и позиции планет... Это займет пару секунд.")

    try:
        day, month, year = map(int, b_date.split("."))
        hour, minute = map(int, b_time.split(":"))

        # Выполняем тяжелую блокирующую функцию в отдельном потоке
        chart = await asyncio.to_thread(
            calculate_natal_chart, "User", year, month, day, hour, minute, city
        )

        text = f"✨ **Ваша Натальная карта ({b_date} {b_time}, {city}):**\n\n"
        for planet, (sign, meaning) in chart.items():
            text += f"**{planet}:** {sign}\n_{meaning}_\n\n"

        await call.message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())

    except Exception as e:
        logging.error(f"Astro error: {e}")
        await call.message.answer(
            "Произошла ошибка при расчете. Проверьте правильность введенного города и формата даты/времени.")


# ==========================================
# 6. ЗАПУСК БОТА
# ==========================================
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())