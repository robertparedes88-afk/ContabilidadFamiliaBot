import re
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ParsedMessage:
    type: Literal[
        "gasto_variable", "gasto_fijo",
        "gasto_variable_deshacer", "gasto_fijo_deshacer",
        "ingreso", "consulta_concepto_mes", "unknown"
    ]
    amount: Optional[float] = None
    concept: Optional[str] = None
    person: Optional[str] = None
    month: Optional[str] = None  # abreviatura normalizada: ENE, FEB, …


# Meses en español (completo y abreviado) → abreviatura de la hoja
MONTH_NAMES: dict[str, str] = {
    "enero": "ENE", "ene": "ENE",
    "febrero": "FEB", "feb": "FEB",
    "marzo": "MAR", "mar": "MAR",
    "abril": "ABR", "abr": "ABR",
    "mayo": "MAY", "may": "MAY",
    "junio": "JUN", "jun": "JUN",
    "julio": "JUL", "jul": "JUL",
    "agosto": "AGO", "ago": "AGO",
    "septiembre": "SEP", "sep": "SEP",
    "octubre": "OCT", "oct": "OCT",
    "noviembre": "NOV", "nov": "NOV",
    "diciembre": "DIC", "dic": "DIC",
}


def _parse_amount(raw: str) -> float:
    return float(raw.replace(",", "."))


def _split_month(text: str) -> tuple[str, Optional[str]]:
    """
    Si la última palabra de `text` es un mes conocido, lo separa y devuelve
    (concepto, abreviatura). Si no, devuelve (text, None).
    """
    words = text.split()
    if len(words) >= 2:
        abbr = MONTH_NAMES.get(words[-1].lower())
        if abbr:
            return " ".join(words[:-1]).strip(), abbr
    return text, None


def parse_message(text: str) -> ParsedMessage:
    text = text.strip()

    # "[importe] variable [concepto] [mes?] deshacer"  — antes que el patrón sin deshacer
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+variable\s+(.+?)\s+deshacer$", text, re.IGNORECASE)
    if m:
        concept, month = _split_month(m.group(2).strip())
        return ParsedMessage(
            type="gasto_variable_deshacer",
            amount=_parse_amount(m.group(1)),
            concept=concept,
            month=month,
        )

    # "[importe] fijo [concepto] [mes?] deshacer"
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+fijo\s+(.+?)\s+deshacer$", text, re.IGNORECASE)
    if m:
        concept, month = _split_month(m.group(2).strip())
        return ParsedMessage(
            type="gasto_fijo_deshacer",
            amount=_parse_amount(m.group(1)),
            concept=concept,
            month=month,
        )

    # "[importe] variable [concepto] [mes?]"
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+variable\s+(.+)$", text, re.IGNORECASE)
    if m:
        concept, month = _split_month(m.group(2).strip())
        return ParsedMessage(
            type="gasto_variable",
            amount=_parse_amount(m.group(1)),
            concept=concept,
            month=month,
        )

    # "[importe] fijo [concepto] [mes?]"
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+fijo\s+(.+)$", text, re.IGNORECASE)
    if m:
        concept, month = _split_month(m.group(2).strip())
        return ParsedMessage(
            type="gasto_fijo",
            amount=_parse_amount(m.group(1)),
            concept=concept,
            month=month,
        )

    # "Pere cobrado 1500 [mes?]"
    m = re.match(r"^(pere)\s+cobrado\s+(\d+(?:[.,]\d+)?)(?:\s+(\w+))?$", text, re.IGNORECASE)
    if m:
        raw_month = m.group(3)
        month = MONTH_NAMES.get(raw_month.lower()) if raw_month else None
        return ParsedMessage(
            type="ingreso",
            amount=_parse_amount(m.group(2)),
            person="Pere",
            month=month,
        )

    # "Alicia cobrada 3800 [mes?]" / "Alícia cobrada 3800 [mes?]"
    m = re.match(r"^(alici[aá])\s+cobrada\s+(\d+(?:[.,]\d+)?)(?:\s+(\w+))?$", text, re.IGNORECASE)
    if m:
        raw_month = m.group(3)
        month = MONTH_NAMES.get(raw_month.lower()) if raw_month else None
        return ParsedMessage(
            type="ingreso",
            amount=_parse_amount(m.group(2)),
            person="Alícia",
            month=month,
        )

    # "[concepto] [mes]" — último token es un mes conocido (consulta)
    words = text.split()
    if len(words) >= 2:
        abbr = MONTH_NAMES.get(words[-1].lower())
        if abbr:
            return ParsedMessage(
                type="consulta_concepto_mes",
                concept=" ".join(words[:-1]).strip(),
                month=abbr,
            )

    return ParsedMessage(type="unknown")
