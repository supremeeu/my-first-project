import asyncio
import os
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
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
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

announcements: dict = {}

EVENT_TYPES_MAIN = ["Официальная игра", "Двусторонка", "Тренировка"]
EVENT_TYPES_MORE = ["Товарищеская игра", "Бросковая", "Корпоратив", "Аренда формы"]

DURATIONS_MAIN = ["1 час 15 минут"]
DURATIONS_MORE = ["1 час", "1 час 30 минут", "1 час 45 минут", "2 часа"]

LEVELS = ["Начинающий", "Старт", "Дебютант 1–3", "Дебютант 4–5", "Любитель", "СПШ", "ПРО"]
LEVELS_FOR_GOALIE = LEVELS + ["Любой"]

GOALIE_COUNT_MAIN = ["1 вратарь", "2 вратаря"]
GOALIE_COUNT_MORE = ["3 вратаря", "4 вратаря", "5 вратарей", "6 вратарей"]

USE_BUTTONS_HINT = "Пожалуйста, выбери вариант с помощью кнопок ниже."

EDIT_OPTIONS = [
    ("event_type", "Вид события"),
    ("address", "Адрес"),
    ("duration", "Продолжительность"),
    ("event_time", "Время начала"),
    ("player_level", "Уровень игроков"),
    ("goalie_level", "Уровень вратаря"),
    ("goalie_count", "Количество вратарей"),
    ("price", "Стоимость"),
    ("comment", "Комментарий"),
]


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
    confirmation = State()


def build_main_keyboard(
    prefix: str, options: list, columns: int = 2
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in options:
        builder.button(text=opt, callback_data=f"{prefix}:{opt}")
    builder.adjust(columns)
    builder.row(InlineKeyboardButton(text="Ещё", callback_data=f"{prefix}:more"))
    return builder.as_markup()


def build_more_keyboard(
    prefix: str, options: list, columns: int = 2, with_custom: bool = True
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
    prefix: str, options: list, selected: set, columns: int = 2
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in options:
        label = f"✓ {opt}" if opt in selected else opt
        builder.button(text=label, callback_data=f"{prefix}:{opt}")
    builder.adjust(columns)
    builder.row(InlineKeyboardButton(text="Готово", callback_data=f"{prefix}:done"))
    return builder.as_markup()


def build_preview_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Опубликовать", callback_data="publish:yes"),
        InlineKeyboardButton(text="Редактировать", callback_data="publish:edit"),
    )
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="publish:no"))
    return builder.as_markup()


def build_edit_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in EDIT_OPTIONS:
        builder.button(text=label, callback_data=f"edit:{key}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="Назад", callback_data="edit:back"))
    return builder.as_markup()


def build_comment_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать", callback_data="comment:write")
    builder.button(text="Нет", callback_data="comment:none")
    builder.adjust(2)
    return builder.as_markup()


async def is_editing(state: FSMContext) -> bool:
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        return True
    return False


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


def build_reactions_keyboard(thinking_count: int, ready_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Думаю ({thinking_count})", callback_data="react:thinking")
    builder.button(text=f"Готов ({ready_count})", callback_data="react:ready")
    builder.adjust(2)
    return builder.as_markup()


def render_announcement_with_reactions(base_text: str, reactions: dict) -> str:
    ready = [r for r in reactions.values() if r["status"] == "ready"]
    thinking = [r for r in reactions.values() if r["status"] == "thinking"]

    lines = [base_text]
    if ready:
        lines.append("")
        lines.append(f"Готов ({len(ready)}):")
        for r in sorted(ready, key=lambda x: x["timestamp"]):
            lines.append(f"• {r['name']} — {r['timestamp'].strftime('%H:%M:%S')}")
    if thinking:
        lines.append("")
        lines.append(f"Думаю ({len(thinking)}):")
        for r in sorted(thinking, key=lambda x: x["timestamp"]):
            lines.append(f"• {r['name']} — {r['timestamp'].strftime('%H:%M:%S')}")
    return "\n".join(lines)


def display_user(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name


def build_announcement_text(data: dict) -> str:
    formatted_price = format_price(data["price"], data["goalie_count"])
    lines = [
        data["event_type"],
        f"Адрес: {data['address']}",
        f"Продолжительность: {data['duration']}",
        f"Начало: {data['event_time']}",
        f"Уровень игроков: {data['player_level']}",
        f"Желаемый уровень вратаря: {data['goalie_level']}",
        f"{data['goalie_count']}, {formatted_price}",
    ]
    if data.get("comment"):
        lines.append(f"Комментарий: {data['comment']}")
    return "\n".join(lines)


async def show_preview(target_msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    preview = build_announcement_text(data)
    await state.set_state(NewAnnouncement.confirmation)
    await target_msg.answer(
        f"Превью объявления:\n\n{preview}",
        reply_markup=build_preview_keyboard(),
    )


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


@dp.message(Command("chatid"))
async def cmd_chatid(message: Message) -> None:
    await message.answer(f"Chat ID: {message.chat.id}")


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
    if await is_editing(state):
        await show_preview(callback.message, state)
    else:
        await state.set_state(NewAnnouncement.address)
        await callback.message.answer("2. Адрес?")
    await callback.answer()


@dp.message(NewAnnouncement.event_type)
async def event_type_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.event_type_custom)
async def process_event_type_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(event_type=message.text)
    if await is_editing(state):
        await show_preview(message, state)
    else:
        await state.set_state(NewAnnouncement.address)
        await message.answer("2. Адрес?")


@dp.message(NewAnnouncement.address)
async def process_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text)
    if await is_editing(state):
        await show_preview(message, state)
    else:
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
    if await is_editing(state):
        await show_preview(callback.message, state)
    else:
        await state.set_state(NewAnnouncement.event_time)
        await callback.message.answer("4. Время начала события?")
    await callback.answer()


@dp.message(NewAnnouncement.duration)
async def duration_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.duration_custom)
async def process_duration_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(duration=message.text)
    if await is_editing(state):
        await show_preview(message, state)
    else:
        await state.set_state(NewAnnouncement.event_time)
        await message.answer("4. Время начала события?")


@dp.message(NewAnnouncement.event_time)
async def process_event_time(message: Message, state: FSMContext) -> None:
    await state.update_data(event_time=message.text)
    if await is_editing(state):
        await show_preview(message, state)
    else:
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
        if await is_editing(state):
            await show_preview(callback.message, state)
        else:
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
        if await is_editing(state):
            await show_preview(callback.message, state)
        else:
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
    if await is_editing(state):
        await show_preview(callback.message, state)
    else:
        await state.set_state(NewAnnouncement.price)
        await callback.message.answer("8. Стоимость (в рублях)?")
    await callback.answer()


@dp.message(NewAnnouncement.goalie_count)
async def goalie_count_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.price)
async def process_price(message: Message, state: FSMContext) -> None:
    await state.update_data(price=message.text)
    if await is_editing(state):
        await show_preview(message, state)
    else:
        await state.set_state(NewAnnouncement.comment)
        await message.answer(
            "9. Дополнительный комментарий?",
            reply_markup=build_comment_choice_keyboard(),
        )


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
    await state.update_data(is_editing=False)
    await show_preview(callback.message, state)
    await callback.answer()


@dp.message(NewAnnouncement.comment)
async def comment_text_fallback(message: Message) -> None:
    await message.answer(USE_BUTTONS_HINT)


@dp.message(NewAnnouncement.comment_input)
async def process_comment_input(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text)
    await state.update_data(is_editing=False)
    await show_preview(message, state)


@dp.callback_query(NewAnnouncement.confirmation, F.data == "publish:no")
async def on_publish_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Публикация отменена.")
    await callback.answer()


@dp.callback_query(NewAnnouncement.confirmation, F.data == "publish:yes")
async def on_publish_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    announcement_text = build_announcement_text(data)

    try:
        sent_msg = await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=announcement_text,
            reply_markup=build_reactions_keyboard(0, 0),
        )
        announcements[sent_msg.message_id] = {
            "organizer_id": callback.from_user.id,
            "base_text": announcement_text,
            "reactions": {},
        }
        await callback.message.edit_text("Объявление опубликовано в группе.")
    except Exception as e:
        await callback.message.edit_text(f"Не удалось опубликовать: {e}")

    await state.clear()
    await callback.answer()


@dp.callback_query(NewAnnouncement.confirmation, F.data == "publish:edit")
async def on_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=build_edit_menu_keyboard())
    await callback.answer()


@dp.callback_query(NewAnnouncement.confirmation, F.data == "edit:back")
async def on_edit_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=build_preview_keyboard())
    await callback.answer()


@dp.callback_query(NewAnnouncement.confirmation, F.data.startswith("edit:"))
async def on_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":", 1)[1]
    await state.update_data(is_editing=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    data = await state.get_data()

    if field == "event_type":
        await state.set_state(NewAnnouncement.event_type)
        keyboard = build_main_keyboard("event", EVENT_TYPES_MAIN, columns=2)
        await callback.message.answer("Какой вид события?", reply_markup=keyboard)
    elif field == "address":
        await state.set_state(NewAnnouncement.address)
        await callback.message.answer("Адрес?")
    elif field == "duration":
        await state.set_state(NewAnnouncement.duration)
        keyboard = build_main_keyboard("dur", DURATIONS_MAIN, columns=1)
        await callback.message.answer(
            "Продолжительность события?", reply_markup=keyboard
        )
    elif field == "event_time":
        await state.set_state(NewAnnouncement.event_time)
        await callback.message.answer("Время начала события?")
    elif field == "player_level":
        await state.set_state(NewAnnouncement.player_level)
        current = data.get("player_level", "")
        selected_list = [s.strip() for s in current.split(",") if s.strip()] if current else []
        await state.update_data(player_level_selected=selected_list)
        keyboard = build_multiselect_keyboard("lvl_p", LEVELS, set(selected_list))
        await callback.message.answer(
            "Уровень игроков?\n\nМожно выбрать несколько вариантов. Когда закончишь — нажми «Готово».",
            reply_markup=keyboard,
        )
    elif field == "goalie_level":
        await state.set_state(NewAnnouncement.goalie_level)
        current = data.get("goalie_level", "")
        selected_list = [s.strip() for s in current.split(",") if s.strip()] if current else []
        await state.update_data(goalie_level_selected=selected_list)
        keyboard = build_multiselect_keyboard(
            "lvl_g", LEVELS_FOR_GOALIE, set(selected_list)
        )
        await callback.message.answer(
            "Желаемый уровень вратаря?\n\nМожно выбрать несколько вариантов. Когда закончишь — нажми «Готово».",
            reply_markup=keyboard,
        )
    elif field == "goalie_count":
        await state.set_state(NewAnnouncement.goalie_count)
        keyboard = build_main_keyboard("gc", GOALIE_COUNT_MAIN, columns=2)
        await callback.message.answer("Количество вратарей?", reply_markup=keyboard)
    elif field == "price":
        await state.set_state(NewAnnouncement.price)
        await callback.message.answer("Стоимость (в рублях)?")
    elif field == "comment":
        await state.set_state(NewAnnouncement.comment)
        await callback.message.answer(
            "Дополнительный комментарий?",
            reply_markup=build_comment_choice_keyboard(),
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("react:"))
async def on_reaction_click(callback: CallbackQuery) -> None:
    new_status = callback.data.split(":", 1)[1]

    msg_id = callback.message.message_id
    if msg_id not in announcements:
        await callback.answer(
            "Объявление недоступно для откликов (возможно, бот перезапускался).",
            show_alert=True,
        )
        return

    ann = announcements[msg_id]
    user_id = callback.from_user.id

    if user_id == ann["organizer_id"]:
        await callback.answer(
            "На своё объявление откликнуться нельзя.", show_alert=True
        )
        return

    reactions = ann["reactions"]

    if user_id in reactions and reactions[user_id]["status"] == new_status:
        del reactions[user_id]
    else:
        reactions[user_id] = {
            "name": display_user(callback.from_user),
            "status": new_status,
            "timestamp": datetime.now(MSK),
        }

    thinking_count = sum(1 for r in reactions.values() if r["status"] == "thinking")
    ready_count = sum(1 for r in reactions.values() if r["status"] == "ready")
    new_text = render_announcement_with_reactions(ann["base_text"], reactions)
    new_kb = build_reactions_keyboard(thinking_count, ready_count)

    try:
        await callback.message.edit_text(new_text, reply_markup=new_kb)
    except TelegramBadRequest:
        pass

    await callback.answer()


async def main() -> None:
    print("Бот запущен. Останови его нажатием Ctrl+C в этом терминале.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
