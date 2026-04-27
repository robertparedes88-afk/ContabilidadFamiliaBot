import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.handlers import (
    ayuda_handler,
    message_handler,
    resumen_handler,
    saldo_handler,
    start_handler,
)
from config import TELEGRAM_TOKEN

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("ayuda", ayuda_handler))
    app.add_handler(CommandHandler("resumen", resumen_handler))
    app.add_handler(CommandHandler("saldo", saldo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot iniciado. Esperando mensajes…")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
