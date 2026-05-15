from __future__ import annotations

from cash_flow_forecast.contracts.enums import DataType
from cash_flow_forecast.contracts.schema import ColumnSchema, TableSchema


def build_default_schema() -> TableSchema:
    """Return the default schema for cash movement CSV extracts."""

    definitions = [
        ("ID", DataType.STRING, True),
        ("ENTITY_SHORTNAME", DataType.CATEGORY, True),
        ("ENTITY_NAME", DataType.STRING, False),
        ("SCOPE_NAME", DataType.STRING, True),
        ("APPLICATIVE_STATUS_SHORTNAME", DataType.CATEGORY, True),
        ("EXTERNAL_REFERENCE", DataType.STRING, False),
        ("CAPTURE_DATE", DataType.DATE, False),
        ("CASH_MOVEMENT_TYPE_SHORTNAME", DataType.CATEGORY, True),
        ("CASH_MOVEMENT_TYPE_NAME", DataType.STRING, False),
        ("CURRENCY_SHORTNAME", DataType.CATEGORY, True),
        ("ACCOUNT_SHORTNAME", DataType.CATEGORY, True),
        ("ACCOUNT_NAME", DataType.STRING, False),
        ("IS_INTERNAL", DataType.STRING, False),
        ("COUNTRY_SHORTNAME", DataType.CATEGORY, False),
        ("BANK_SHORTNAME", DataType.CATEGORY, True),
        ("BANK_NAME", DataType.STRING, False),
        ("CPTY_SHORTNAME", DataType.STRING, False),
        ("CPTY_NAME", DataType.STRING, False),
        ("CPTY_ACCOUNT_SHORTNAME", DataType.STRING, False),
        ("CPTY_ACCOUNT_NAME", DataType.STRING, False),
        ("ANALYTIC_TYPE_SHORTNAME", DataType.CATEGORY, True),
        ("ANALYTIC_TYPE_NAME", DataType.STRING, False),
        ("ISSUE_DATE", DataType.DATE, False),
        ("TRADE_DATE", DataType.DATE, True),
        ("VALUE_DATE", DataType.DATE, True),
        ("MATCH_DATE", DataType.DATE, False),
        ("AMOUNT", DataType.FLOAT, True),
        ("SIGN", DataType.INTEGER, True),
        ("SIGNED_AMOUNT", DataType.FLOAT, False),
        ("ORIGIN_AMOUNT", DataType.FLOAT, False),
        ("ORIGIN_CURRENCY_SHORTNAME", DataType.STRING, False),
        ("IS_REVERSAL", DataType.CATEGORY, False),
        ("DESCRIPTION", DataType.STRING, True),
    ]
    columns = [
        ColumnSchema(name=name, dtype=dtype, required=required)
        for name, dtype, required in definitions
    ]
    return TableSchema(name="cash_movements", columns=columns)