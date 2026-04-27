import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.parser import MONTH_NAMES, parse_message
from bot.sheets import (
    add_gasto_variable,
    get_anual_concepto,
    get_resumen,
    get_valor_concepto_mes,
    set_gasto_fijo,
    set_ingreso,
    subtract_gasto_fijo,
    subtract_gasto_variable,
)
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
    "*Registrar en un mes específico:*\n"
    "  `85 variable ropa enero`\n"
    "  `737 fijo hipoteca marzo`\n"
    "  `Pere cobrado 1478 enero`\n\n"
    "*Revertir un error:*\n"
    "  `140 variable restaurante deshacer`\n"
    "  `50 variable gasolina marzo deshacer`\n\n"
    "*Consultar concepto en un mes:*\n"
    "  `coche marzo`  |  `restaurante abril`\n\n"
    "*Consultas generales:*\n"
    "  /resumen — resumen del mes actual\n"
    "  /resumen marzo — resumen de un mes específico\n"
    "  /anual coche — desglose anual de un concepto\n"
    "  /saldo   — ahorro del mes actual\n"
    "  /ayuda   — este mensaje"
)


def _is_allowed(update: Update) -> bool:
    if not ALLOWED_CHAT_IDS:
        return True
    return update.effective_chat.id in ALLOWED_CHAT_IDS


def _fmt(value: float) -> str:
    return f"{value:,.2f}€".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_short(value: float) -> str:
    """Formato compacto sin decimales si son cero."""
    if value == int(value):
        return f"{int(value):,}€".replace(",", ".")
    return _fmt(value)


def _parse_month_arg(args: list[str]) -> tuple[str | None, str | None]:
    """Devuelve (abbr, error_msg) a partir de los args del comando."""
    if not args:
        return None, None
    abbr = MONTH_NAMES.get(args[0].lower())
    if not abbr:
        return None, f"❌ Mes '{args[0]}' no reconocido. Escribe p.ej. `marzo` o `mar`."
    return abbr, None


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

    month_abbr, err = _parse_month_arg(context.args)
    if err:
        await update.message.reply_text(err, parse_mode="Markdown")
        return

    await update.message.reply_text("⏳ Obteniendo datos…")

    try:
        data = get_resumen(month_abbr)
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

    lines.append("🔄 *GASTOS RECURRENTES*")
    for concept, val in data["gastos_recurrentes"]:
        if val > 0:
            lines.append(f"  {concept}: {_fmt(val)}")
    lines.append(f"  *Total: {_fmt(data['total_recurrentes'])}*\n")

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


async def anual_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Indica el concepto. Ejemplo: `/anual coche`", parse_mode="Markdown"
        )
        return

    concept = " ".join(context.args)
    await update.message.reply_text("⏳ Obteniendo datos…")

    try:
        data = get_anual_concepto(concept)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
        return
    except Exception as e:
        logger.error("anual error: %s", e)
        await update.message.reply_text(f"❌ Error inesperado: {e}")
        return

    values = data["values"]
    total = sum(v for v in values.values() if v is not None)

    # Formato: 4 meses por línea
    months_order = list(values.keys())
    rows = []
    for i in range(0, 12, 4):
        chunk = months_order[i:i + 4]
        parts = []
        for m in chunk:
            v = values[m]
            parts.append(f"{m}: {_fmt_short(v) if v is not None else '—'}")
        rows.append(" | ".join(parts))

    msg = (
        f"📊 *{data['concept']} — Resumen anual {data['year']}*\n\n"
        + "\n".join(rows)
        + f"\n\n*Total año: {_fmt(total)}*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return

    text = update.message.text or ""
    parsed = parse_message(text)

    if parsed.type == "gasto_variable":
        try:
            r = add_gasto_variable(parsed.concept, parsed.amount, parsed.month)
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
            r = set_gasto_fijo(parsed.concept, parsed.amount, parsed.month)
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
            r = set_ingreso(parsed.person, parsed.amount, parsed.month)
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

    elif parsed.type == "gasto_variable_deshacer":
        try:
            r = subtract_gasto_variable(parsed.concept, parsed.amount, parsed.month)
            await update.message.reply_text(
                f"✅ *Gasto revertido*\n"
                f"📌 {r['concept']} — {r['month']}\n"
                f"{_fmt(r['old'])} → *{_fmt(r['new'])}* (-{_fmt(r['delta'])})",
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            logger.error("gasto_variable_deshacer error: %s", e)
            await update.message.reply_text(f"❌ Error inesperado: {e}")

    elif parsed.type == "gasto_fijo_deshacer":
        try:
            r = subtract_gasto_fijo(parsed.concept, parsed.amount, parsed.month)
            await update.message.reply_text(
                f"✅ *Gasto revertido*\n"
                f"📌 {r['concept']} — {r['month']}\n"
                f"{_fmt(r['old'])} → *{_fmt(r['new'])}* (-{_fmt(r['delta'])})",
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            logger.error("gasto_fijo_deshacer error: %s", e)
            await update.message.reply_text(f"❌ Error inesperado: {e}")

    elif parsed.type == "consulta_concepto_mes":
        try:
            r = get_valor_concepto_mes(parsed.concept, parsed.month)
            await update.message.reply_text(
                f"📊 *{r['concept']} — {r['month']}*\n{_fmt(r['value'])}",
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
        except Exception as e:
            logger.error("consulta_concepto_mes error: %s", e)
            await update.message.reply_text(f"❌ Error inesperado: {e}")

    # Si es desconocido, no respondemos para no generar ruido.
