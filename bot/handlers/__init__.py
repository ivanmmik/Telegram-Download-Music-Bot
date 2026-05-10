from aiogram import Router

from bot.handlers import commands, links


def setup_routers() -> Router:
    root = Router()
    root.include_router(commands.router)
    root.include_router(links.router)
    return root
