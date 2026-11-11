"""Бизнес-логика заказов. Всё, что меняет остатки, выполняется в транзакции с блокировкой строк."""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from shop.models import Order, OrderItem, Product


@transaction.atomic
def create_order(*, user, address: str, comment: str, items: list[dict]) -> Order:
    """items: [{"product_id": 1, "quantity": 2}, ...]"""
    quantities: dict[int, int] = {}
    for item in items:  # одинаковые товары в запросе складываем в одну позицию
        quantities[item["product_id"]] = quantities.get(item["product_id"], 0) + item["quantity"]

    # select_for_update блокирует строки товаров до конца транзакции:
    # два одновременных заказа не смогут продать один и тот же последний товар
    products = {
        p.id: p
        for p in Product.objects.select_for_update()
        .filter(id__in=quantities, is_active=True)
        .order_by("id")
    }

    errors = {}
    for product_id, qty in quantities.items():
        product = products.get(product_id)
        if product is None:
            errors[str(product_id)] = "Product not found or not available."
        elif product.stock < qty:
            errors[str(product_id)] = f"Only {product.stock} left in stock."
    if errors:
        raise ValidationError({"items": errors})

    order = Order.objects.create(user=user, address=address, comment=comment)
    total = Decimal("0")
    order_items = []
    for product_id, qty in quantities.items():
        product = products[product_id]
        product.stock -= qty
        product.save(update_fields=["stock"])
        order_items.append(
            OrderItem(order=order, product=product, quantity=qty, price=product.price)
        )
        total += product.price * qty
    OrderItem.objects.bulk_create(order_items)
    order.total = total
    order.save(update_fields=["total"])
    return order


@transaction.atomic
def change_status(order: Order, new_status: str) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_change_to(new_status):
        raise ValidationError(
            {"status": f"Cannot change status from {order.status} to {new_status}."}
        )
    if new_status == Order.Status.CANCELLED:
        # Возвращаем товары на склад
        for item in order.items.select_related("product").select_for_update():
            item.product.stock += item.quantity
            item.product.save(update_fields=["stock"])
    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    return order
