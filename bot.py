import asyncio
import html
import os
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

announcements: dict = {}
user_phones: dict = {}
pending_phone_tasks: dict = {}

EVENT_TYPES_MAIN = ["Официальная игра", "Двусторонка", "Тренировка"]
EVENT_TYPES_MORE = ["Товарищеская игра", "Бросковая", "Корпоратив", "Аренда формы"]

DURATIONS_MAIN = ["1 час 15 минут"]
DURATIONS_MORE = ["1 час", "1 час 30 минут", "1 час 45 минут", "2 часа"]

LEVELS = ["Начинающий", "Старт", "Дебютант 1–3", "Дебютант 4–5", "Любитель", "СПШ", "ПРО"]
LEVELS_FOR_GOALIE = LEVELS + ["Любой"]

GOALIE_COUNT_MAIN = ["1 вратарь", "2 вратаря"]
GOALIE_COUNT_MORE = ["3 вратаря", "4 вратаря", "5 вратарей", "6 вратарей"]

USE_BUTTONS_HINT = "Пожалуйста, выбери вариант с помощью кнопок ниже."

STATUS_LABELS = {
    "thinking": "Думаю",
    "ready": "Готов",
    "in_game": "В игре",
}

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

ANNOUNCEMENT_FIELDS = [k for k, _ in EDIT_OPTIONS]


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


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Искать вратаря", callback_data="action:new")
    return builder.as_markup()


async def is_editing(state: FSMContext) -> bool:
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        return True
    return False


def parse_goalie_count(goalie_count_text: str) -> int:
    digits = "".join(c for c in goalie_count_text if c.isdigit())
    return int(digits) if digits else 1


def format_price(price_text: str, goalie_count_text: str) -> str:
    price_clean = price_text.strip()
    digits_only = price_clean.replace(" ", "")
    if digits_only.isdigit():
        formatted = f"{digits_only} руб."
    else:
        formatted = price_clean

    count = parse_goalie_count(goalie_count_text)
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
    in_game = [r for r in reactions.values() if r["status"] == "in_game"]
    ready = [r for r in reactions.values() if r["status"] == "ready"]
    thinking = [r for r in reactions.values() if r["status"] == "thinking"]

    lines = [base_text]
    if in_game:
        lines.append("")
        lines.append(f"В игре ({len(in_game)}):")
        for r in sorted(in_game, key=lambda x: x["timestamp"]):
            lines.append(
                f"• {html.escape(r['name'])} — {r['timestamp'].strftime('%H:%M:%S')}"
            )
    if ready:
        lines.append("")
        lines.append(f"Готов ({len(ready)}):")
        for r in sorted(ready, key=lambda x: x["timestamp"]):
            lines.append(
                f"• {html.escape(r['name'])} — {r['timestamp'].strftime('%H:%M:%S')}"
            )
    if thinking:
        lines.append("")
        lines.append(f"Думаю ({len(thinking)}):")
        for r in sorted(thinking, key=lambda x: x["timestamp"]):
            lines.append(
                f"• {html.escape(r['name'])} — {r['timestamp'].strftime('%H:%M:%S')}"
            )
    return "\n".join(lines)


def render_group_text(ann: dict) -> str:
    if ann.get("closed"):
        base = f"<s>{ann['base_text']}</s>"
        text = render_announcement_with_reactions(base, ann["reactions"])
        text += "\n\n<b>ЗАКРЫТО</b>"
    else:
        text = render_announcement_with_reactions(
            ann["base_text"], ann["reactions"]
        )
    return text


def render_management_panel(ann: dict) -> str:
    reactions = ann["reactions"]
    in_game = sorted(
        [r for r in reactions.values() if r["status"] == "in_game"],
        key=lambda x: x["timestamp"],
    )
    ready = sorted(
        [r for r in reactions.values() if r["status"] == "ready"],
        key=lambda x: x["timestamp"],
    )
    thinking = sorted(
        [r for r in reactions.values() if r["status"] == "thinking"],
        key=lambda x: x["timestamp"],
    )

    header = "Управление твоим объявлением"
    if ann.get("closed"):
        header += " (ЗАКРЫТО)"

    base = (
        f"<s>{ann['base_text']}</s>" if ann.get("closed") else ann["base_text"]
    )

    lines = [
        header,
        "",
        base,
        "",
        "Чтобы связаться с откликнувшимся — нажми на его @username в списке ниже.",
        "",
    ]

    if in_game:
        lines.append(f"В игре ({len(in_game)}):")
        for r in in_game:
            lines.append(
                f"• {html.escape(r['name'])} — {r['timestamp'].strftime('%H:%M:%S')}"
            )
        lines.append("")
    if ready:
        lines.append(f"Готов ({len(ready)}):")
        for r in ready:
            lines.append(
                f"• {html.escape(r['name'])} — {r['timestamp'].strftime('%H:%M:%S')}"
            )
        lines.append("")
    if thinking:
        lines.append(f"Думаю ({len(thinking)}):")
        for r in thinking:
            lines.append(
                f"• {html.escape(r['name'])} — {r['timestamp'].strftime('%H:%M:%S')}"
            )
        lines.append("")

    if not (in_game or ready or thinking):
        lines.append("Откликов пока нет.")

    return "\n".join(lines).rstrip()


def build_management_keyboard(ann_id: int, ann: dict):
    if ann.get("closed"):
        return None

    reactions = ann["reactions"]
    pending = [
        (uid, r)
        for uid, r in reactions.items()
        if r["status"] in ("ready", "thinking")
    ]
    in_game_count = sum(1 for r in reactions.values() if r["status"] == "in_game")
    max_count = ann.get("goalie_count_max", 1)
    can_approve_more = in_game_count < max_count

    has_buttons = False
    builder = InlineKeyboardBuilder()
    if can_approve_more:
        for uid, r in sorted(pending, key=lambda x: x[1]["timestamp"]):
            builder.row(
                InlineKeyboardButton(
                    text=f"Утвердить {r['name']}",
                    callback_data=f"approve:{ann_id}:{uid}",
                )
            )
            has_buttons = True

    if in_game_count > 0:
        builder.row(
            InlineKeyboardButton(
                text="Закрыть объявление",
                callback_data=f"close:{ann_id}",
            )
        )
        has_buttons = True

    builder.row(
        InlineKeyboardButton(
            text="Редактировать объявление",
            callback_data=f"manage_edit:{ann_id}",
        )
    )
    has_buttons = True

    return builder.as_markup() if has_buttons else None


async def refresh_organizer_panel(ann_id: int, ann: dict) -> None:
    panel_msg_id = ann.get("organizer_dm_message_id")
    if not panel_msg_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=ann["organizer_id"],
            message_id=panel_msg_id,
            text=render_management_panel(ann),
            reply_markup=build_management_keyboard(ann_id, ann),
        )
    except TelegramBadRequest:
        pass


def display_user(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name


async def request_phone(user_id: int, prompt_text: str) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поделиться номером", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    try:
        await bot.send_message(user_id, prompt_text, reply_markup=keyboard)
    except Exception:
        pass


async def execute_phone_task(task: dict, phone: str) -> None:
    try:
        if task["type"] == "share_organizer_phone":
            await bot.send_message(
                chat_id=task["player_id"],
                text=f"Номер телефона организатора для связи: {phone}",
            )
        elif task["type"] == "share_player_phone":
            await bot.send_message(
                chat_id=task["organizer_id"],
                text=(
                    f"Номер телефона {task['player_name']} для связи: {phone}"
                ),
            )
    except Exception:
        pass


def build_announcement_text(data: dict) -> str:
    formatted_price = format_price(data["price"], data["goalie_count"])

    def label(word: str) -> str:
        return f"<b>{word}</b>"

    event_type_upper = html.escape((data["event_type"] or "").upper())

    lines = [
        f"<b>{event_type_upper}</b>",
        f"🏟 {label('Адрес')}: {html.escape(data['address'] or '')}",
        f"⏳ {label('Продолжительность')}: {html.escape(data['duration'] or '')}",
        f"🕰 {label('Начало')}: {html.escape(data['event_time'] or '')}",
        f"🏒 {label('Уровень игроков')}: {html.escape(data['player_level'] or '')}",
        f"🥅 {label('Желаемый уровень вратаря')}: {html.escape(data['goalie_level'] or '')}",
        f"💳 {label('Стоимость')}: {html.escape(data['goalie_count'] or '')}, {html.escape(formatted_price)}",
    ]
    text = "\n".join(lines)
    if data.get("comment"):
        text += f"\n\n{label('Комментарий')}: {html.escape(data['comment'])}"
    return text


async def show_preview(target_msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("editing_published_ann_id"):
        await finish_published_edit(target_msg, state)
        return
    preview = build_announcement_text(data)
    await state.set_state(NewAnnouncement.confirmation)
    await target_msg.answer(
        f"Превью объявления:\n\n{preview}",
        reply_markup=build_preview_keyboard(),
    )


async def finish_published_edit(target_msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    ann_id = data.get("editing_published_ann_id")
    ann = announcements.get(ann_id) if ann_id else None
    if not ann:
        await target_msg.answer("Объявление не найдено.")
        await state.clear()
        return

    for field in ANNOUNCEMENT_FIELDS:
        if field in data:
            ann["data"][field] = data[field]

    ann["base_text"] = (
        build_announcement_text(ann["data"])
        + f"\n\n👤 <b>{html.escape(ann['organizer_tag'])} - организатор</b>"
    )
    ann["goalie_count_max"] = parse_goalie_count(ann["data"]["goalie_count"])

    reactions = ann["reactions"]
    thinking_count = sum(1 for r in reactions.values() if r["status"] == "thinking")
    ready_count = sum(1 for r in reactions.values() if r["status"] == "ready")

    try:
        await bot.edit_message_text(
            chat_id=GROUP_CHAT_ID,
            message_id=ann_id,
            text=render_group_text(ann),
            reply_markup=(
                None
                if ann.get("closed")
                else build_reactions_keyboard(thinking_count, ready_count)
            ),
        )
    except TelegramBadRequest:
        pass

    await refresh_organizer_panel(ann_id, ann)
    await target_msg.answer("Изменения опубликованы в группе.")
    await state.clear()


@dp.message(F.contact)
async def on_contact_received(message: Message) -> None:
    contact = message.contact
    user_id = message.from_user.id

    if contact.user_id and contact.user_id != user_id:
        await message.answer(
            "Пожалуйста, поделись своим номером, а не чужим контактом.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    phone = contact.phone_number
    user_phones[user_id] = phone

    await message.answer(
        "Спасибо, номер получен. Передам его второй стороне.",
        reply_markup=ReplyKeyboardRemove(),
    )

    tasks = pending_phone_tasks.pop(user_id, [])
    for task in tasks:
        await execute_phone_task(task, phone)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я бот для поиска игроков.",
        reply_markup=build_main_menu_keyboard(),
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
    organizer_tag = display_user(callback.from_user)
    announcement_text = (
        build_announcement_text(data)
        + f"\n\n👤 <b>{html.escape(organizer_tag)} - организатор</b>"
    )

    try:
        sent_msg = await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=announcement_text,
            reply_markup=build_reactions_keyboard(0, 0),
        )
        ann = {
            "organizer_id": callback.from_user.id,
            "organizer_tag": organizer_tag,
            "data": {f: data.get(f) for f in ANNOUNCEMENT_FIELDS},
            "base_text": announcement_text,
            "reactions": {},
            "organizer_dm_message_id": None,
            "goalie_count_max": parse_goalie_count(data["goalie_count"]),
            "closed": False,
        }
        announcements[sent_msg.message_id] = ann

        panel_msg = await bot.send_message(
            chat_id=callback.from_user.id,
            text=render_management_panel(ann),
            reply_markup=build_management_keyboard(sent_msg.message_id, ann),
        )
        ann["organizer_dm_message_id"] = panel_msg.message_id

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
    data = await state.get_data()
    if data.get("editing_published_ann_id"):
        await callback.message.edit_text("Редактирование отменено.")
        await state.clear()
    else:
        await callback.message.edit_reply_markup(reply_markup=build_preview_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("manage_edit:"))
async def on_manage_edit_click(callback: CallbackQuery, state: FSMContext) -> None:
    ann_id = int(callback.data.split(":", 1)[1])
    ann = announcements.get(ann_id)
    if not ann:
        await callback.answer("Объявление не найдено.", show_alert=True)
        return
    if callback.from_user.id != ann["organizer_id"]:
        await callback.answer(
            "Только организатор может редактировать.", show_alert=True
        )
        return
    if ann.get("closed"):
        await callback.answer("Объявление закрыто.", show_alert=True)
        return

    await state.set_state(NewAnnouncement.confirmation)
    await state.update_data(
        **{f: ann["data"].get(f) for f in ANNOUNCEMENT_FIELDS},
        editing_published_ann_id=ann_id,
    )

    await callback.message.answer(
        "Что меняем?",
        reply_markup=build_edit_menu_keyboard(),
    )
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

    if ann.get("closed"):
        await callback.answer("Объявление закрыто.", show_alert=True)
        return

    if user_id == ann["organizer_id"]:
        await callback.answer(
            "На своё объявление откликнуться нельзя.", show_alert=True
        )
        return

    reactions = ann["reactions"]
    user_tag = display_user(callback.from_user)
    user_tag_safe = html.escape(user_tag)

    if user_id in reactions and reactions[user_id]["status"] == new_status:
        old_status = reactions[user_id]["status"]
        del reactions[user_id]
        notify_organizer = (
            f"{user_tag_safe} отменил отклик («{STATUS_LABELS[old_status]}»)."
        )
    elif user_id in reactions:
        old_status = reactions[user_id]["status"]
        notify_organizer = (
            f"{user_tag_safe} сменил статус с "
            f"«{STATUS_LABELS.get(old_status, old_status)}» "
            f"на «{STATUS_LABELS[new_status]}»."
        )
        reactions[user_id] = {
            "name": user_tag,
            "username": callback.from_user.username,
            "status": new_status,
            "timestamp": datetime.now(MSK),
        }
    else:
        notify_organizer = (
            f"{user_tag_safe} откликнулся: «{STATUS_LABELS[new_status]}»."
        )
        reactions[user_id] = {
            "name": user_tag,
            "username": callback.from_user.username,
            "status": new_status,
            "timestamp": datetime.now(MSK),
        }

    thinking_count = sum(1 for r in reactions.values() if r["status"] == "thinking")
    ready_count = sum(1 for r in reactions.values() if r["status"] == "ready")
    new_text = render_group_text(ann)
    new_kb = build_reactions_keyboard(thinking_count, ready_count)

    try:
        await callback.message.edit_text(new_text, reply_markup=new_kb)
    except TelegramBadRequest:
        pass

    await refresh_organizer_panel(msg_id, ann)

    try:
        await bot.send_message(
            chat_id=ann["organizer_id"],
            text=notify_organizer,
        )
    except Exception:
        pass

    await callback.answer()


@dp.callback_query(F.data.startswith("approve:"))
async def on_approve_click(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, ann_id_str, user_id_str = parts
    ann_id = int(ann_id_str)
    user_id = int(user_id_str)

    ann = announcements.get(ann_id)
    if not ann:
        await callback.answer("Объявление не найдено.", show_alert=True)
        return

    if callback.from_user.id != ann["organizer_id"]:
        await callback.answer("Утверждать может только организатор.", show_alert=True)
        return

    if ann.get("closed"):
        await callback.answer("Объявление уже закрыто.", show_alert=True)
        return

    reactions = ann["reactions"]
    if user_id not in reactions:
        await callback.answer("Этот пользователь не откликался.", show_alert=True)
        return

    if reactions[user_id]["status"] == "in_game":
        await callback.answer("Этот пользователь уже утверждён.", show_alert=True)
        return

    in_game_count = sum(1 for r in reactions.values() if r["status"] == "in_game")
    max_count = ann.get("goalie_count_max", 1)
    if in_game_count >= max_count:
        await callback.answer(
            f"Уже утверждено {in_game_count} — это максимум по объявлению.",
            show_alert=True,
        )
        return

    reactions[user_id]["status"] = "in_game"
    reactions[user_id]["timestamp"] = datetime.now(MSK)
    approved_name = reactions[user_id]["name"]

    thinking_count = sum(1 for r in reactions.values() if r["status"] == "thinking")
    ready_count = sum(1 for r in reactions.values() if r["status"] == "ready")
    try:
        await bot.edit_message_text(
            chat_id=GROUP_CHAT_ID,
            message_id=ann_id,
            text=render_group_text(ann),
            reply_markup=build_reactions_keyboard(thinking_count, ready_count),
        )
    except TelegramBadRequest:
        pass

    await refresh_organizer_panel(ann_id, ann)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"Вас утвердил {html.escape(ann['organizer_tag'])} на:\n\n"
                f"{ann['base_text']}"
            ),
            reply_markup=build_main_menu_keyboard(),
        )
    except Exception:
        pass

    organizer_has_username = bool(callback.from_user.username)
    player_has_username = bool(ann["reactions"][user_id].get("username"))
    organizer_id = ann["organizer_id"]
    player_name = approved_name

    if not organizer_has_username:
        if organizer_id in user_phones:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        "Номер телефона организатора для связи: "
                        f"{user_phones[organizer_id]}"
                    ),
                )
            except Exception:
                pass
        else:
            pending_phone_tasks.setdefault(organizer_id, []).append(
                {"type": "share_organizer_phone", "player_id": user_id}
            )
            await request_phone(
                organizer_id,
                (
                    f"Игроку {player_name}, которого ты только что утвердил, "
                    "нужно с тобой связаться. У тебя в Telegram не задан "
                    "@username — поделись номером, бот передаст его игроку."
                ),
            )

    if not player_has_username:
        if user_id in user_phones:
            try:
                await bot.send_message(
                    chat_id=organizer_id,
                    text=(
                        f"Номер телефона {player_name} для связи: "
                        f"{user_phones[user_id]}"
                    ),
                )
            except Exception:
                pass
        else:
            pending_phone_tasks.setdefault(user_id, []).append(
                {
                    "type": "share_player_phone",
                    "organizer_id": organizer_id,
                    "player_name": player_name,
                }
            )
            await request_phone(
                user_id,
                (
                    "Тебя утвердил организатор. Чтобы он с тобой связался — "
                    "поделись номером (у тебя в Telegram не задан @username)."
                ),
            )

    if not ann.get("reminder_started"):
        ann["reminder_started"] = True
        asyncio.create_task(remind_to_close(ann_id))

    await callback.answer(f"{approved_name} утверждён.")


async def close_announcement(ann_id: int, ann: dict) -> None:
    if ann.get("closed"):
        return
    ann["closed"] = True

    try:
        await bot.edit_message_text(
            chat_id=GROUP_CHAT_ID,
            message_id=ann_id,
            text=render_group_text(ann),
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass

    await refresh_organizer_panel(ann_id, ann)

    reason = (
        f"Объявление закрыто организатором {html.escape(ann['organizer_tag'])} — "
        "согласован другой."
    )

    for uid, r in ann["reactions"].items():
        if r["status"] == "in_game":
            continue
        try:
            await bot.send_message(
                chat_id=uid,
                text=f"{reason}\n\n{ann['base_text']}",
            )
        except Exception:
            pass


async def remind_to_close(ann_id: int) -> None:
    while True:
        await asyncio.sleep(600)
        ann = announcements.get(ann_id)
        if not ann or ann.get("closed"):
            return
        has_in_game = any(
            r["status"] == "in_game" for r in ann["reactions"].values()
        )
        if not has_in_game:
            return
        try:
            await bot.send_message(
                chat_id=ann["organizer_id"],
                text=(
                    "Напоминание: ты утвердил игроков по объявлению, "
                    "но оно ещё не закрыто. Когда состав собран, нажми "
                    "«Закрыть объявление» в кабинете управления.\n\n"
                    f"{ann['base_text']}"
                ),
            )
        except Exception:
            pass


@dp.callback_query(F.data.startswith("close:"))
async def on_close_click(callback: CallbackQuery) -> None:
    ann_id = int(callback.data.split(":", 1)[1])
    ann = announcements.get(ann_id)
    if not ann:
        await callback.answer("Объявление не найдено.", show_alert=True)
        return

    if callback.from_user.id != ann["organizer_id"]:
        await callback.answer("Закрыть может только организатор.", show_alert=True)
        return

    if ann.get("closed"):
        await callback.answer("Уже закрыто.")
        return

    await close_announcement(ann_id, ann)
    try:
        await bot.send_message(
            chat_id=ann["organizer_id"],
            text="Объявление закрыто.",
            reply_markup=build_main_menu_keyboard(),
        )
    except Exception:
        pass
    await callback.answer("Объявление закрыто.")


async def main() -> None:
    print("Бот запущен. Останови его нажатием Ctrl+C в этом терминале.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
