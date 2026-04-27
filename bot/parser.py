import re
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ParsedMessage:
    type: Literal["gasto_variable", "gasto_fijo", "ingreso", "unknown"]
    amount: Optional[float] = None
    concept: Optional[str] = None
    person: Optional[str] = None


def _parse_amount(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse_message(text: str) -> ParsedMessage:
    text = text.strip()

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

    return ParsedMessage(type="unknown")
