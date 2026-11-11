from django.urls import include, path
from rest_framework.routers import DefaultRouter

from shop.api import CategoryViewSet, OrderViewSet, ProductViewSet, RegisterView

router = DefaultRouter()
router.register("categories", CategoryViewSet)
router.register("products", ProductViewSet, basename="product")
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("", include(router.urls)),
]
