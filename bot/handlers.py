import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.parser import parse_message
from bot.sheets import add_gasto_variable, get_resumen, set_gasto_fijo, set_ingreso
from config import ALLOWED_CHAT_IDS

logger = logging.getLogger(__name__)

_HELP_TEXT = (
    "📒 *Bot de Contabilidad Familiar*\n\n"
    "*Registrar gasto variable:*\n"
    "  `140 variable restaurante`\n"
    "  `30 variable pasteleria`\n\n"
    "*Registrar gasto fijo:*\n"
    "  `737 fijo hipoteca`\n"
    "  `235 fijo coche`\n\n"
    "*Registrar ingreso:*\n"
    "  `Pere cobrado 1500`\n"
    "  `Alicia cobrada 3800`\n\n"
    "*Consultas:*\n"
    "  /resumen — resumen completo del mes\n"
    "  /saldo   — ahorro del mes\n"
    "  /ayuda   — este mensaje"
)


def _is_allowed(update: Update) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    return update.effective_chat.id in ALLOWED_CHAT_IDS


def _fmt(value: float) -> str:
    return f"{value:,.2f}€".replace(",", "X").replace(".", ",").replace("X", ".")


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(_HELP_TEXT, parse_mode="Markdown")


async def ayuda_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(_HELP_TEXT, parse_mode="Markdown")


async def resumen_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return

    await update.message.reply_text("⏳ Obteniendo datos…")

    try:
        data = get_resumen()
    except Exception as e:
        logger.error("resumen error: %s", e)
        await update.message.reply_text(f"❌ Error al leer la hoja: {e}")
        return

    lines = [f"📊 *Resumen {data['month']}*\n"]

    lines.append("💰 *INGRESOS*")
    for concept, val in data["ingresos"]:
        lines.append(f"  {concept}: {_fmt(val)}")
    lines.append(f"  *Total: {_fmt(data['total_ingresos'])}*\n")

    lines.append("🏠 *GASTOS FIJOS*")
    for concept, val in data["gastos_fijos"]:
        lines.append(f"  {concept}: {_fmt(val)}")
    lines.append(f"  *Total: {_fmt(data['total_fijos'])}*\n")

    lines.append("🛒 *GASTOS VARIABLES*")
    for concept, val in data["gastos_variables"]:
        if val > 0:
            lines.append(f"  {concept}: {_fmt(val)}")
    lines.append(f"  *Total: {_fmt(data['total_variables'])}*\n")

    lines.append(f"📤 *Total gastos: {_fmt(data['total_gastos'])}*")

    emoji = "✅" if data["ahorro"] >= 0 else "⚠️"
    lines.append(f"{emoji} *Ahorro: {_fmt(data['ahorro'])}*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def saldo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return

    try:
        data = get_resumen()
    except Exception as e:
        logger.error("saldo error: %s", e)
        await update.message.reply_text(f"❌ Error al leer la hoja: {e}")
        return

    emoji = "✅" if data["ahorro"] >= 0 else "⚠️"
    msg = (
        f"📊 *Saldo {data['month']}*\n\n"
        f"💰 Ingresos:  {_fmt(data['total_ingresos'])}\n"
        f"📤 Gastos:    {_fmt(data['total_gastos'])}\n"
        f"{'─' * 24}\n"
        f"{emoji} Ahorro:   {_fmt(data['ahorro'])}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return

    text = update.message.text or ""
    parsed = parse_message(text)

    if parsed.type == "gasto_variable":
        try:
            r = add_gasto_variable(parsed.concept, parsed.amount)
            await update.message.reply_text(
                f"✅ *Gasto variable registrado*\n"
                f"📌 {r['concept']} — {r['month']}\n"
                f"{_fmt(r['old'])} → *{_fmt(r['new'])}* (+{_fmt(r['delta'])})",
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            logger.error("gasto_variable error: %s", e)
            await update.message.reply_text(f"❌ Error inesperado: {e}")

    elif parsed.type == "gasto_fijo":
        try:
            r = set_gasto_fijo(parsed.concept, parsed.amount)
            await update.message.reply_text(
                f"✅ *Gasto fijo actualizado*\n"
                f"📌 {r['concept']} — {r['month']}\n"
                f"{_fmt(r['old'])} → *{_fmt(r['new'])}*",
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            logger.error("gasto_fijo error: %s", e)
            await update.message.reply_text(f"❌ Error inesperado: {e}")

    elif parsed.type == "ingreso":
        try:
            r = set_ingreso(parsed.person, parsed.amount)
            await update.message.reply_text(
                f"✅ *Ingreso registrado*\n"
                f"👤 {r['concept']} — {r['month']}\n"
                f"{_fmt(r['old'])} → *{_fmt(r['new'])}*",
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            logger.error("ingreso error: %s", e)
            await update.message.reply_text(f"❌ Error inesperado: {e}")

    # Si es desconocido, no respondemos para no generar ruido.
