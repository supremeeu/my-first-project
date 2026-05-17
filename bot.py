import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer("Привет! Я бот для поиска игроков. Пока умею только здороваться.")


async def main() -> None:
    print("Бот запущен. Останови его нажатием Ctrl+C в этом терминале.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
