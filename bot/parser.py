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


def parse_message(text: str) -> ParsedMessage:
    text = text.strip()

    # "140 variable restaurante deshacer"  — antes que el patrón sin deshacer
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+variable\s+(.+?)\s+deshacer$", text, re.IGNORECASE)
    if m:
        return ParsedMessage(
            type="gasto_variable_deshacer",
            amount=_parse_amount(m.group(1)),
            concept=m.group(2).strip(),
        )

    # "737 fijo hipoteca deshacer"
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+fijo\s+(.+?)\s+deshacer$", text, re.IGNORECASE)
    if m:
        return ParsedMessage(
            type="gasto_fijo_deshacer",
            amount=_parse_amount(m.group(1)),
            concept=m.group(2).strip(),
        )

    # "140 variable restaurante"
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+variable\s+(.+)$", text, re.IGNORECASE)
    if m:
        return ParsedMessage(
            type="gasto_variable",
            amount=_parse_amount(m.group(1)),
            concept=m.group(2).strip(),
        )

    # "737 fijo hipoteca"
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s+fijo\s+(.+)$", text, re.IGNORECASE)
    if m:
        return ParsedMessage(
            type="gasto_fijo",
            amount=_parse_amount(m.group(1)),
            concept=m.group(2).strip(),
        )

    # "Pere cobrado 1500"
    m = re.match(r"^(pere)\s+cobrado\s+(\d+(?:[.,]\d+)?)$", text, re.IGNORECASE)
    if m:
        return ParsedMessage(
            type="ingreso",
            amount=_parse_amount(m.group(2)),
            person="Pere",
        )

    # "Alicia cobrada 3800" / "Alícia cobrada 3800"
    m = re.match(r"^(alici[aá])\s+cobrada\s+(\d+(?:[.,]\d+)?)$", text, re.IGNORECASE)
    if m:
        return ParsedMessage(
            type="ingreso",
            amount=_parse_amount(m.group(2)),
            person="Alícia",
        )

    # "[concepto] [mes]" — último token es un mes conocido
    # Se comprueba al final para no interferir con los patrones anteriores
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
