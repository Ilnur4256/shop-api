from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from shop.models import Category, Order, Product

User = get_user_model()


class BaseAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.buyer = User.objects.create_user("buyer", password="pass-12345-x")
        self.other = User.objects.create_user("other", password="pass-12345-x")
        self.staff = User.objects.create_user("staff", password="pass-12345-x", is_staff=True)
        self.cat = Category.objects.create(name="Phones", slug="phones")
        self.phone = Product.objects.create(
            category=self.cat, name="Phone X", price=Decimal("100.00"), stock=5
        )
        self.case = Product.objects.create(
            category=self.cat, name="Case", price=Decimal("9.50"), stock=10
        )
        self.hidden = Product.objects.create(
            category=self.cat, name="Old phone", price=Decimal("50"), stock=3, is_active=False
        )

    def order(self, user, items, address="Karakol, Toktogul 1"):
        self.client.force_authenticate(user)
        return self.client.post("/api/orders/", {"address": address, "items": items}, format="json")


class AuthTests(BaseAPITest):
    def test_register_and_get_jwt(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "new", "email": "n@example.com", "password": "Strong-pass-123"},
        )
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("password", r.data)
        r = self.client.post("/api/auth/token/", {"username": "new", "password": "Strong-pass-123"})
        self.assertEqual(r.status_code, 200)
        token = r.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/orders/").status_code, 200)

    def test_weak_password_rejected(self):
        r = self.client.post("/api/auth/register/", {"username": "x", "password": "123"})
        self.assertEqual(r.status_code, 400)


class ProductTests(BaseAPITest):
    def test_anonymous_can_read_active_products_only(self):
        r = self.client.get("/api/products/")
        self.assertEqual(r.status_code, 200)
        names = {p["name"] for p in r.data["results"]}
        self.assertEqual(names, {"Phone X", "Case"})

    def test_staff_sees_hidden_products(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/products/").data["count"], 3)

    def test_filters_search_ordering(self):
        r = self.client.get("/api/products/?price_max=50")
        self.assertEqual([p["name"] for p in r.data["results"]], ["Case"])
        r = self.client.get("/api/products/?search=phone")
        self.assertEqual([p["name"] for p in r.data["results"]], ["Phone X"])
        r = self.client.get("/api/products/?ordering=price")
        self.assertEqual([p["name"] for p in r.data["results"]], ["Case", "Phone X"])
        r = self.client.get("/api/products/?category=phones&in_stock=true")
        self.assertEqual(r.data["count"], 2)

    def test_only_staff_can_create_products(self):
        payload = {"category": self.cat.id, "name": "New", "price": "1.00", "stock": 1}
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.post("/api/products/", payload).status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post("/api/products/", payload).status_code, 201)

    def test_price_must_be_positive(self):
        self.client.force_authenticate(self.staff)
        payload = {"category": self.cat.id, "name": "Bad", "price": "0", "stock": 1}
        self.assertEqual(self.client.post("/api/products/", payload).status_code, 400)


class OrderTests(BaseAPITest):
    def test_create_order_decrements_stock_and_counts_total(self):
        r = self.order(
            self.buyer,
            [
                {"product_id": self.phone.id, "quantity": 2},
                {"product_id": self.case.id, "quantity": 1},
                {"product_id": self.case.id, "quantity": 1},  # дубль складывается
            ],
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Decimal(r.data["total"]), Decimal("219.00"))
        self.assertEqual(len(r.data["items"]), 2)
        self.phone.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual((self.phone.stock, self.case.stock), (3, 8))

    def test_not_enough_stock_creates_nothing(self):
        r = self.order(
            self.buyer,
            [
                {"product_id": self.case.id, "quantity": 1},
                {"product_id": self.phone.id, "quantity": 6},
            ],
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn(str(self.phone.id), r.data["items"])
        self.case.refresh_from_db()
        self.assertEqual(self.case.stock, 10)  # транзакция откатилась целиком
        self.assertEqual(Order.objects.count(), 0)

    def test_hidden_or_missing_product_rejected(self):
        r = self.order(self.buyer, [{"product_id": self.hidden.id, "quantity": 1}])
        self.assertEqual(r.status_code, 400)
        r = self.order(self.buyer, [{"product_id": 9999, "quantity": 1}])
        self.assertEqual(r.status_code, 400)

    def test_empty_items_and_anonymous_rejected(self):
        self.assertEqual(self.order(self.buyer, []).status_code, 400)
        self.client.force_authenticate(None)
        r = self.client.post("/api/orders/", {"address": "x", "items": []}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_price_is_fixed_at_order_time(self):
        order_id = self.order(self.buyer, [{"product_id": self.phone.id, "quantity": 1}]).data["id"]
        self.phone.price = Decimal("150")
        self.phone.save()
        r = self.client.get(f"/api/orders/{order_id}/")
        self.assertEqual(Decimal(r.data["total"]), Decimal("100.00"))

    def test_users_see_only_own_orders(self):
        self.order(self.buyer, [{"product_id": self.case.id, "quantity": 1}])
        own_id = Order.objects.get().id
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/orders/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/orders/{own_id}/").status_code, 404)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/orders/").data["count"], 1)

    def test_cancel_returns_stock(self):
        order_id = self.order(self.buyer, [{"product_id": self.phone.id, "quantity": 2}]).data["id"]
        r = self.client.post(f"/api/orders/{order_id}/cancel/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "cancelled")
        self.phone.refresh_from_db()
        self.assertEqual(self.phone.stock, 5)
        # повторная отмена запрещена и не возвращает товар второй раз
        self.assertEqual(self.client.post(f"/api/orders/{order_id}/cancel/").status_code, 400)
        self.phone.refresh_from_db()
        self.assertEqual(self.phone.stock, 5)

    def test_status_flow_staff_only(self):
        order_id = self.order(self.buyer, [{"product_id": self.case.id, "quantity": 1}]).data["id"]
        url = f"/api/orders/{order_id}/set_status/"
        self.assertEqual(self.client.post(url, {"status": "paid"}).status_code, 403)

        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(url, {"status": "shipped"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"status": "paid"}).data["status"], "paid")
        self.assertEqual(self.client.post(url, {"status": "shipped"}).data["status"], "shipped")
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.post(f"/api/orders/{order_id}/cancel/").status_code, 400)


class DocsTests(TestCase):
    def test_openapi_schema_and_swagger(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)
