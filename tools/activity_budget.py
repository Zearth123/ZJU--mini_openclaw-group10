"""活动预算计算 Tool：只做确定性计算，不替 Agent 决定采购内容。"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .base import Tool


CENT = Decimal("0.01")


def _money(value: Any, field: str) -> Decimal:
    """把输入转换为非负金额，并统一保留两位小数。"""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} 必须是有效数字") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} 必须是非负有限数字")
    return number.quantize(CENT, rounding=ROUND_HALF_UP)


def _ratio(value: Any) -> Decimal:
    try:
        ratio = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("reserve_ratio 必须是有效数字") from exc
    if not ratio.is_finite() or ratio < 0 or ratio > 1:
        raise ValueError("reserve_ratio 必须在 0 到 1 之间")
    return ratio


def _quantity(value: Any) -> Decimal:
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("quantity 必须是有效数字") from exc
    if not quantity.is_finite() or quantity < 0:
        raise ValueError("quantity 必须是非负有限数字")
    return quantity


def _json_number(value: Decimal) -> int | float:
    """整数金额输出 int，其余输出两位小数 float，保持 JSON 易读。"""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def calculate_budget_data(
    budget_limit: Any,
    items: list[dict[str, Any]],
    reserve_ratio: Any = 0.1,
) -> dict[str, Any]:
    """计算预算明细、分类合计、备用金、总额和余额。"""
    limit = _money(budget_limit, "budget_limit")
    ratio = _ratio(reserve_ratio)
    if not isinstance(items, list):
        raise ValueError("items 必须是数组")

    normalized_items: list[dict[str, Any]] = []
    category_totals: dict[str, Decimal] = {}
    warnings: list[str] = []

    for index, raw in enumerate(items, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"items[{index - 1}] 必须是对象")

        name = str(raw.get("name", "")).strip()
        category = str(raw.get("category", "")).strip()
        priority = str(raw.get("priority", "required")).strip()
        price_status = str(raw.get("price_status", "estimated")).strip()
        if not name:
            raise ValueError(f"第 {index} 个预算项缺少 name")
        if not category:
            raise ValueError(f"预算项 {name} 缺少 category")
        if priority not in {"required", "optional"}:
            raise ValueError(f"预算项 {name} 的 priority 必须是 required 或 optional")
        if price_status not in {"confirmed", "estimated", "pending_quote"}:
            raise ValueError(
                f"预算项 {name} 的 price_status 必须是 confirmed、estimated 或 pending_quote"
            )

        unit_price = _money(raw.get("unit_price"), f"预算项 {name} 的 unit_price")
        quantity = _quantity(raw.get("quantity"))
        subtotal = (unit_price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        category_totals[category] = category_totals.get(category, Decimal("0")) + subtotal

        item = dict(raw)
        item.update({
            "item_id": str(raw.get("item_id") or f"budget-{index:03d}"),
            "name": name,
            "category": category,
            "unit_price": _json_number(unit_price),
            "quantity": _json_number(quantity),
            "subtotal": _json_number(subtotal),
            "priority": priority,
            "price_status": price_status,
            "notes": str(raw.get("notes", "")),
        })
        normalized_items.append(item)

        if price_status == "pending_quote":
            warnings.append(f"预算项“{name}”尚未询价")
        elif price_status == "estimated":
            warnings.append(f"预算项“{name}”使用估算价格")

    subtotal = sum(category_totals.values(), Decimal("0")).quantize(CENT)
    reserve = (subtotal * ratio).quantize(CENT, rounding=ROUND_HALF_UP)
    total = subtotal + reserve
    remaining = limit - total
    over_budget = total > limit
    if over_budget:
        warnings.append(f"预算超出上限 {_json_number(total - limit)} 元")

    return {
        "budget_limit": _json_number(limit),
        "reserve_ratio": float(ratio),
        "items": normalized_items,
        "category_totals": {
            category: _json_number(amount.quantize(CENT))
            for category, amount in sorted(category_totals.items())
        },
        "subtotal": _json_number(subtotal),
        "reserve": _json_number(reserve),
        "total": _json_number(total),
        "remaining": _json_number(remaining),
        "over_budget": over_budget,
        "warnings": warnings,
    }


def _calculate_budget(**kwargs: Any) -> str:
    try:
        result = calculate_budget_data(**kwargs)
    except ValueError as exc:
        result = {"ok": False, "error": str(exc)}
    return json.dumps(result, ensure_ascii=False, indent=2)


calculate_budget_tool = Tool(
    name="calculate_budget",
    description=(
        "根据预算上限、备用金比例和预算项目进行确定性计算，返回单项小计、"
        "分类汇总、备用金、总预算、余额及是否超预算。该工具不决定购买什么。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "budget_limit": {"type": "number", "minimum": 0},
            "reserve_ratio": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.1},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "name": {"type": "string"},
                        "category": {"type": "string"},
                        "unit_price": {"type": "number", "minimum": 0},
                        "quantity": {"type": "number", "minimum": 0},
                        "priority": {"type": "string", "enum": ["required", "optional"]},
                        "price_status": {
                            "type": "string",
                            "enum": ["confirmed", "estimated", "pending_quote"],
                        },
                        "notes": {"type": "string"},
                    },
                    "required": ["name", "category", "unit_price", "quantity"],
                },
            },
        },
        "required": ["budget_limit", "items"],
    },
    run=_calculate_budget,
)