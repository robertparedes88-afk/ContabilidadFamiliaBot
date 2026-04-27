"""
Google Sheets integration.

Estructura esperada de la hoja:
  Fila 1 (cabecera): Concepto | Enero | Febrero | ... | Diciembre
  Filas siguientes:  una fila por concepto, agrupadas por secciones.

Las secciones se detectan por el contenido de la columna A:
  - Filas que contengan "ingreso"  → sección INGRESOS
  - Filas que contengan "fijo"     → sección GASTOS FIJOS
  - Filas que contengan "variable" → sección GASTOS VARIABLES

Ejemplo de hoja válida:
  A               B       C        ...
  Concepto        Enero   Febrero
  ── INGRESOS ──
  Pere            0       0
  Alícia          0       0
  ── GASTOS FIJOS ──
  Hipoteca        737     737
  Coche           235     235
  ── GASTOS VARIABLES ──
  Restaurante     0       0
  Gasolina        0       0
"""

import difflib
import json
import logging
import unicodedata
from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_CREDENTIALS_JSON, SHEET_NAME, SPREADSHEET_ID

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_MONTHS_ES = {
    1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR",
    5: "MAY", 6: "JUN", 7: "JUL", 8: "AGO",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC",
}

# Orden completo de meses para el resumen anual
_MONTHS_ORDER = [_MONTHS_ES[i] for i in range(1, 13)]

# Palabras que identifican filas de cabecera/total (se ignoran como conceptos)
_SECTION_KEYWORDS = (
    "total", "gastos", "ingresos", "ingreso", "fijo", "variable",
    "concepto", "resumen", "persona", "ahorro", "---", "==="
)

# Fila 5 del sheet (índice 4 en base 0): cabecera real con los meses ENE..DIC
_HEADER_ROW_IDX = 4

# Rangos de filas por sección (1-indexed, inclusivos)
_ROWS_INGRESOS         = (6,  7)
_ROWS_GASTOS_FIJOS     = (12, 16)
_ROWS_RECURRENTES      = (21, 32)
_ROWS_GASTOS_VARIABLES = (37, 43)


def _get_sheet() -> gspread.Worksheet:
    creds = Credentials.from_service_account_info(
        json.loads(GOOGLE_CREDENTIALS_JSON), scopes=_SCOPES
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)


def _current_month_name() -> str:
    return _MONTHS_ES[datetime.now().month]


def _find_month_col(header_row: list[str], month_name: str) -> int:
    """Returns 1-indexed column for the given month name."""
    for i, cell in enumerate(header_row):
        if cell.strip().lower() == month_name.lower():
            return i + 1
    raise ValueError(f"Mes '{month_name}' no encontrado en la cabecera de la hoja.")


def _is_section_header(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _SECTION_KEYWORDS)


def _norm(text: str) -> str:
    """Lowercase + strip accents for flexible matching."""
    return unicodedata.normalize("NFD", text.lower()).encode("ascii", "ignore").decode().strip()


def _find_concept_row(all_values: list[list[str]], concept: str) -> tuple[int, str]:
    """
    Returns (1-indexed row number, matched concept label).
    Reads labels from column B (index 1).
    Search order: exact → substring → fuzzy. All comparisons are
    case-insensitive and accent-insensitive.
    """
    candidates: list[tuple[int, str]] = []
    for i, row in enumerate(all_values):
        label = row[1].strip() if len(row) > 1 else ""
        if not label or _is_section_header(label):
            continue
        candidates.append((i + 1, label))

    needle = _norm(concept)

    # 1) Exact match
    for row_num, label in candidates:
        if _norm(label) == needle:
            return row_num, label

    # 2) Substring match: "restaurante" → "Restaurantes", "super" → "Comida / Supermercado"
    for row_num, label in candidates:
        if needle in _norm(label):
            return row_num, label

    # 3) Fuzzy match as last resort
    norms = [_norm(label) for _, label in candidates]
    matches = difflib.get_close_matches(needle, norms, n=1, cutoff=0.5)
    if matches:
        idx = norms.index(matches[0])
        return candidates[idx]

    raise ValueError(
        f"Concepto '{concept}' no encontrado en la hoja. "
        f"Comprueba que el nombre coincide con una fila existente."
    )


def _cell_float(value: str) -> float:
    try:
        return float(str(value).replace(",", ".").replace("€", "").strip())
    except (ValueError, AttributeError):
        return 0.0


# ── Public API ────────────────────────────────────────────────────────────────


def add_gasto_variable(concept: str, amount: float) -> dict:
    """Suma `amount` al valor actual de la celda del mes corriente."""
    sheet = _get_sheet()
    month = _current_month_name()
    all_values = sheet.get_all_values()
    col = _find_month_col(all_values[_HEADER_ROW_IDX], month)
    row, matched = _find_concept_row(all_values, concept)

    current = _cell_float(all_values[row - 1][col - 1] if len(all_values[row - 1]) >= col else "")
    new_value = round(current + amount, 2)
    sheet.update_cell(row, col, new_value)

    return {"concept": matched, "month": month, "old": current, "new": new_value, "delta": amount}


def set_gasto_fijo(concept: str, amount: float) -> dict:
    """Reemplaza el valor de la celda del mes corriente."""
    sheet = _get_sheet()
    month = _current_month_name()
    all_values = sheet.get_all_values()
    col = _find_month_col(all_values[_HEADER_ROW_IDX], month)
    row, matched = _find_concept_row(all_values, concept)

    current = _cell_float(all_values[row - 1][col - 1] if len(all_values[row - 1]) >= col else "")
    sheet.update_cell(row, col, round(amount, 2))

    return {"concept": matched, "month": month, "old": current, "new": amount}


def set_ingreso(person: str, amount: float) -> dict:
    """Reemplaza el ingreso de la persona en el mes corriente."""
    return set_gasto_fijo(person, amount)


def subtract_gasto_variable(concept: str, amount: float) -> dict:
    """Resta `amount` del valor actual (revertir un gasto variable)."""
    sheet = _get_sheet()
    month = _current_month_name()
    all_values = sheet.get_all_values()
    col = _find_month_col(all_values[_HEADER_ROW_IDX], month)
    row, matched = _find_concept_row(all_values, concept)

    current = _cell_float(all_values[row - 1][col - 1] if len(all_values[row - 1]) >= col else "")
    new_value = round(current - amount, 2)
    sheet.update_cell(row, col, new_value)

    return {"concept": matched, "month": month, "old": current, "new": new_value, "delta": amount}


def subtract_gasto_fijo(concept: str, amount: float) -> dict:
    """Resta `amount` del valor actual (revertir un gasto fijo)."""
    sheet = _get_sheet()
    month = _current_month_name()
    all_values = sheet.get_all_values()
    col = _find_month_col(all_values[_HEADER_ROW_IDX], month)
    row, matched = _find_concept_row(all_values, concept)

    current = _cell_float(all_values[row - 1][col - 1] if len(all_values[row - 1]) >= col else "")
    new_value = round(current - amount, 2)
    sheet.update_cell(row, col, new_value)

    return {"concept": matched, "month": month, "old": current, "new": new_value, "delta": amount}


def get_valor_concepto_mes(concept: str, month: str) -> dict:
    """Devuelve el valor de un concepto en un mes específico."""
    sheet = _get_sheet()
    all_values = sheet.get_all_values()
    col = _find_month_col(all_values[_HEADER_ROW_IDX], month)
    row, matched = _find_concept_row(all_values, concept)
    val = _cell_float(all_values[row - 1][col - 1] if len(all_values[row - 1]) >= col else "")
    return {"concept": matched, "month": month, "value": val}


def get_anual_concepto(concept: str) -> dict:
    """Devuelve el valor de un concepto en cada mes del año y el total."""
    sheet = _get_sheet()
    all_values = sheet.get_all_values()
    header = all_values[_HEADER_ROW_IDX]
    row, matched = _find_concept_row(all_values, concept)
    row_data = all_values[row - 1]

    values: dict[str, Optional[float]] = {}
    for month in _MONTHS_ORDER:
        try:
            col = _find_month_col(header, month)
            values[month] = _cell_float(row_data[col - 1] if len(row_data) >= col else "")
        except ValueError:
            values[month] = None  # columna no existe en la hoja

    return {"concept": matched, "year": datetime.now().year, "values": values}


def _read_rows(
    all_values: list[list[str]], start_row: int, end_row: int, col: int
) -> list[tuple[str, float]]:
    """Lee labels (col B) y valores (col `col`) de un rango de filas 1-indexed."""
    result = []
    for i in range(start_row - 1, end_row):
        if i >= len(all_values):
            break
        row = all_values[i]
        label = row[1].strip() if len(row) > 1 else ""
        if not label:
            continue
        val = _cell_float(row[col - 1] if len(row) >= col else "")
        result.append((label, val))
    return result


def get_resumen(month: Optional[str] = None) -> dict:
    """
    Lee toda la hoja y devuelve un resumen estructurado.
    Usa rangos de fila fijos para cada sección.
    Si no se indica mes, usa el mes actual.
    """
    sheet = _get_sheet()
    month = month or _current_month_name()
    all_values = sheet.get_all_values()
    col = _find_month_col(all_values[_HEADER_ROW_IDX], month)

    # DEBUG TEMP
    logger.warning("DEBUG col=%d | fila6=%s | fila7=%s", col, all_values[5], all_values[6])

    ingresos         = _read_rows(all_values, *_ROWS_INGRESOS,         col)
    gastos_fijos     = _read_rows(all_values, *_ROWS_GASTOS_FIJOS,     col)
    recurrentes      = _read_rows(all_values, *_ROWS_RECURRENTES,       col)
    gastos_variables = _read_rows(all_values, *_ROWS_GASTOS_VARIABLES,  col)

    total_ingresos    = sum(v for _, v in ingresos)
    total_fijos       = sum(v for _, v in gastos_fijos)
    total_recurrentes = sum(v for _, v in recurrentes)
    total_variables   = sum(v for _, v in gastos_variables)
    total_gastos      = total_fijos + total_recurrentes + total_variables
    ahorro            = total_ingresos - total_gastos

    return {
        "month":              month,
        "ingresos":           ingresos,
        "gastos_fijos":       gastos_fijos,
        "gastos_recurrentes": recurrentes,
        "gastos_variables":   gastos_variables,
        "total_ingresos":     total_ingresos,
        "total_fijos":        total_fijos,
        "total_recurrentes":  total_recurrentes,
        "total_variables":    total_variables,
        "total_gastos":       total_gastos,
        "ahorro":             ahorro,
    }
