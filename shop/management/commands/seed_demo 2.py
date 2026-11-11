from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from shop.models import Category, Product

DEMO = {
    "Phones": [("Phone X", "499.00", 10), ("Phone Mini", "299.00", 0)],
    "Laptops": [("Laptop Pro 14", "1299.00", 5), ("Laptop Air", "899.00", 7)],
    "Accessories": [("USB-C cable", "9.90", 100), ("Wireless mouse", "24.50", 30)],
}


class Command(BaseCommand):
    help = "Создаёт демо-категории, товары и пользователей admin/admin12345, buyer/buyer12345"

    def handle(self, *args, **options):
        for cat_name, products in DEMO.items():
            category, _ = Category.objects.get_or_create(
                slug=cat_name.lower(), defaults={"name": cat_name}
            )
            for name, price, stock in products:
                Product.objects.get_or_create(
                    name=name,
                    defaults={"category": category, "price": Decimal(price), "stock": stock},
                )
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin12345")
        if not User.objects.filter(username="buyer").exists():
            User.objects.create_user("buyer", "buyer@example.com", "buyer12345")
        self.stdout.write(self.style.SUCCESS("Demo data created"))
