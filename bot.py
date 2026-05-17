import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

EVENT_TYPES_MAIN = ["Официальная игра", "Двусторонка", "Тренировка"]
EVENT_TYPES_MORE = ["Товарищеская игра", "Бросковая", "Корпоратив", "Аренда формы"]

DURATIONS_MAIN = ["1 час 15 минут"]
DURATIONS_MORE = ["1 час", "1 час 30 минут", "1 час 45 минут", "2 часа"]

LEVELS = ["Начинающий", "Старт", "Дебютант 1–3", "Дебютант 4–5", "Любитель", "СПШ", "ПРО"]
LEVELS_FOR_GOALIE = LEVELS + ["Любой"]

GOALIE_COUNT_MAIN = ["1 вратарь", "2 вратаря"]
GOALIE_COUNT_MORE = ["3 вратаря", "4 вратаря", "5 вратарей", "6 вратарей"]

USE_BUTTONS_HINT = "Пожалуйста, выбери вариант с помощью кнопок ниже."


class NewAnnouncement(StatesGroup):
    event_type = State()
    event_type_custom = State()
    address = State()
    duration = State()
    duration_custom = State()
    event_time = State()
    player_level = State()
    goalie_level = State()
    goalie_count = State()
    price = State()
    comment = State()
    comment_input = State()


def build_main_keyboard(
    prefix: str,
    options: list,
    columns: int = 2,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in options:
        builder.button(text=opt, callback_data=f"{prefix}:{opt}")
    builder.adjust(columns)
    builder.row(InlineKeyboardButton(text="Ещё", callback_data=f"{prefix}:more"))
    return builder.as_markup()


def build_more_keyboard(
    prefix: str,
    options: list,
    columns: int = 2,
    with_custom: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in options:
        builder.button(text=opt, callback_data=f"{prefix}:{opt}")
    builder.adjust(columns)
    if with_custom:
        builder.row(
            InlineKeyboardButton(text="Свой вариант", callback_data=f"{prefix}:custom")
        )
    builder.row(InlineKeyboardButton(text="Назад", callback_data=f"{prefix}:back"))
    return builder.as_markup()


def build_multiselect_keyboard(
    prefix: str,
    options: list,
    selected: set,
    columns: int = 2,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in options:
        label = f"✓ {opt}" if opt in selected else opt
        builder.button(text=label, callback_data=f"{prefix}:{opt}")
    builder.adjust(columns)
    builder.row(InlineKeyboardButton(text="Готово", callback_data=f"{prefix}:done"))
    return builder.as_markup()


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="Искать вратаря", callback_data="action:new")
    await message.answer(
        "Привет! Я бот для поиска игроков.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "action:new")
async def on_search_goalie_click(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewAnnouncement.event_type)
    keyboard = build_main_keyboard("event", EVENT_TYPES_MAIN, columns=2)
    await callback.message.answer(
        "Создаём новое объявление.\n\n1. Какой вид события?",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нет активного создания объявления.")
        return
    await state.clear()
    await message.answer("Создание объявления отменено.")


@dp.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await state.set_state(NewAnnouncement.event_type)
    keyboard = build_main_keyboard("event", EVENT_TYPES_MAIN, columns=2)
    await message.answer(
        "Создаём новое объявление.\n\n1. Какой вид события?",
        reply_markup=keyboard,
    )


@dp.callback_query(NewAnnouncement.event_type, F.data.startswith("event:"))
async def on_event_click(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "more":
        keyboard = build_more_keyboard("event", EVENT_TYPES_MORE, columns=2)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()
        return
    if value == "back":
        keyboard = build_main_keyboard("event", EVENT_TYPES_MAIN, columns=2)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()
        return
    if value == "custom":
        await state.set_state(NewAnnouncement.event_type_custom)
        await callback.message.edit_text("1. Напиши свой вариант события:")
        await callback.answer()
        return
    await state.update_data(event_type=value)
    await callback.message.edit_text(f"1. {value}")
    await state.set_state(NewAnnouncement.address)
    await callback.message.answer("2. Адрес?")
    await callback.answer()


@dp.message(NewAnnouncement.event_type)
async def event_type_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.event_type_custom)
async def process_event_type_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(event_type=message.text)
    await state.set_state(NewAnnouncement.address)
    await message.answer("2. Адрес?")


@dp.message(NewAnnouncement.address)
async def process_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text)
    await state.set_state(NewAnnouncement.duration)
    keyboard = build_main_keyboard("dur", DURATIONS_MAIN, columns=1)
    await message.answer("3. Продолжительность события?", reply_markup=keyboard)


@dp.callback_query(NewAnnouncement.duration, F.data.startswith("dur:"))
async def on_duration_click(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "more":
        keyboard = build_more_keyboard("dur", DURATIONS_MORE, columns=2)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()
        return
    if value == "back":
        keyboard = build_main_keyboard("dur", DURATIONS_MAIN, columns=1)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()
        return
    if value == "custom":
        await state.set_state(NewAnnouncement.duration_custom)
        await callback.message.edit_text("3. Напиши свою продолжительность:")
        await callback.answer()
        return
    await state.update_data(duration=value)
    await callback.message.edit_text(f"3. Продолжительность: {value}")
    await state.set_state(NewAnnouncement.event_time)
    await callback.message.answer("4. Время начала события?")
    await callback.answer()


@dp.message(NewAnnouncement.duration)
async def duration_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.duration_custom)
async def process_duration_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(duration=message.text)
    await state.set_state(NewAnnouncement.event_time)
    await message.answer("4. Время начала события?")


@dp.message(NewAnnouncement.event_time)
async def process_event_time(message: Message, state: FSMContext) -> None:
    await state.update_data(event_time=message.text)
    await state.set_state(NewAnnouncement.player_level)
    await state.update_data(player_level_selected=[])
    keyboard = build_multiselect_keyboard("lvl_p", LEVELS, set())
    await message.answer(
        "5. Уровень игроков?\n\nМожно выбрать несколько вариантов. Когда закончишь — нажми «Готово».",
        reply_markup=keyboard,
    )


@dp.callback_query(NewAnnouncement.player_level, F.data.startswith("lvl_p:"))
async def on_player_level_click(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = set(data.get("player_level_selected", []))

    if value == "done":
        if not selected:
            await callback.answer("Выбери хотя бы один уровень", show_alert=True)
            return
        levels_str = ", ".join(sorted(selected, key=LEVELS.index))
        await state.update_data(player_level=levels_str)
        await callback.message.edit_text(f"5. Уровень игроков: {levels_str}")
        await state.set_state(NewAnnouncement.goalie_level)
        await state.update_data(goalie_level_selected=[])
        keyboard = build_multiselect_keyboard("lvl_g", LEVELS_FOR_GOALIE, set())
        await callback.message.answer(
            "6. Желаемый уровень вратаря?\n\nМожно выбрать несколько вариантов. Когда закончишь — нажми «Готово».",
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    if value in selected:
        selected.remove(value)
    else:
        selected.add(value)
    await state.update_data(player_level_selected=list(selected))
    keyboard = build_multiselect_keyboard("lvl_p", LEVELS, selected)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@dp.message(NewAnnouncement.player_level)
async def player_level_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.callback_query(NewAnnouncement.goalie_level, F.data.startswith("lvl_g:"))
async def on_goalie_level_click(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = set(data.get("goalie_level_selected", []))

    if value == "done":
        if not selected:
            await callback.answer("Выбери хотя бы один уровень", show_alert=True)
            return
        levels_str = ", ".join(sorted(selected, key=LEVELS_FOR_GOALIE.index))
        await state.update_data(goalie_level=levels_str)
        await callback.message.edit_text(f"6. Желаемый уровень вратаря: {levels_str}")
        await state.set_state(NewAnnouncement.goalie_count)
        keyboard = build_main_keyboard("gc", GOALIE_COUNT_MAIN, columns=2)
        await callback.message.answer("7. Количество вратарей?", reply_markup=keyboard)
        await callback.answer()
        return

    if value in selected:
        selected.remove(value)
    else:
        selected.add(value)
    await state.update_data(goalie_level_selected=list(selected))
    keyboard = build_multiselect_keyboard("lvl_g", LEVELS_FOR_GOALIE, selected)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@dp.message(NewAnnouncement.goalie_level)
async def goalie_level_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.callback_query(NewAnnouncement.goalie_count, F.data.startswith("gc:"))
async def on_goalie_count_click(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "more":
        keyboard = build_more_keyboard("gc", GOALIE_COUNT_MORE, columns=2, with_custom=False)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()
        return
    if value == "back":
        keyboard = build_main_keyboard("gc", GOALIE_COUNT_MAIN, columns=2)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()
        return
    await state.update_data(goalie_count=value)
    await callback.message.edit_text(f"7. Количество вратарей: {value}")
    await state.set_state(NewAnnouncement.price)
    await callback.message.answer("8. Стоимость (в рублях)?")
    await callback.answer()


@dp.message(NewAnnouncement.goalie_count)
async def goalie_count_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.price)
async def process_price(message: Message, state: FSMContext) -> None:
    await state.update_data(price=message.text)
    await state.set_state(NewAnnouncement.comment)
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать", callback_data="comment:write")
    builder.button(text="Нет", callback_data="comment:none")
    builder.adjust(2)
    await message.answer(
        "9. Дополнительный комментарий?",
        reply_markup=builder.as_markup(),
    )


def format_price(price_text: str, goalie_count_text: str) -> str:
    price_clean = price_text.strip()
    digits_only = price_clean.replace(" ", "")
    if digits_only.isdigit():
        formatted = f"{digits_only} руб."
    else:
        formatted = price_clean

    digits_in_count = "".join(c for c in goalie_count_text if c.isdigit())
    count = int(digits_in_count) if digits_in_count else 1
    if count > 1 and "каждому" not in formatted.lower():
        formatted = f"{formatted} каждому"
    return formatted


async def show_preview(target_msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    formatted_price = format_price(data["price"], data["goalie_count"])

    preview_lines = [
        data["event_type"],
        f"Адрес: {data['address']}",
        f"Продолжительность: {data['duration']}",
        f"Начало: {data['event_time']}",
        f"Уровень игроков: {data['player_level']}",
        f"Желаемый уровень вратаря: {data['goalie_level']}",
        f"{data['goalie_count']}, {formatted_price}",
    ]
    if data.get("comment"):
        preview_lines.append(f"Комментарий: {data['comment']}")

    preview = "\n".join(preview_lines)
    await target_msg.answer(
        "Превью объявления:\n\n"
        f"{preview}\n\n"
        "Подтверждение и публикацию в группу добавим следующим шагом."
    )
    await state.clear()


@dp.callback_query(NewAnnouncement.comment, F.data.startswith("comment:"))
async def on_comment_click(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "write":
        await state.set_state(NewAnnouncement.comment_input)
        await callback.message.edit_text("9. Напиши комментарий:")
        await callback.answer()
        return
    await state.update_data(comment=None)
    await callback.message.edit_text("9. Без комментария")
    await show_preview(callback.message, state)
    await callback.answer()


@dp.message(NewAnnouncement.comment)
async def comment_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.comment_input)
async def process_comment_input(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text)
    await show_preview(message, state)


async def main() -> None:
    print("Бот запущен. Останови его нажатием Ctrl+C в этом терминале.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
