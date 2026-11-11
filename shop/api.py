from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from shop import services
from shop.filters import OrderFilter, ProductFilter
from shop.models import Category, Order, OrderItem, Product
from shop.permissions import IsStaffOrReadOnly
from shop.serializers import (
    CategorySerializer,
    OrderCreateSerializer,
    OrderSerializer,
    OrderStatusSerializer,
    ProductSerializer,
    RegisterSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"
    search_fields = ["name"]


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsStaffOrReadOnly]
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "name"]

    def get_queryset(self):
        qs = Product.objects.select_related("category")
        # Покупатели не видят снятые с продажи товары, сотрудники видят всё
        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)
        return qs


class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = OrderFilter
    ordering_fields = ["created_at", "total"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # генерация схемы Swagger
            return Order.objects.none()
        qs = Order.objects.select_related("user").prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.select_related("product"))
        )
        # Покупатель видит только свои заказы, сотрудник — все
        return qs if self.request.user.is_staff else qs.filter(user=self.request.user)

    def get_serializer_class(self):
        return OrderCreateSerializer if self.action == "create" else OrderSerializer

    @extend_schema(request=OrderCreateSerializer, responses={201: OrderSerializer})
    def create(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.create_order(user=request.user, **serializer.validated_data)
        return Response(
            OrderSerializer(self.get_queryset().get(pk=order.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Покупатель может отменить свой заказ, пока он не отправлен."""
        order = services.change_status(self.get_object(), Order.Status.CANCELLED)
        return Response(OrderSerializer(self.get_queryset().get(pk=order.pk)).data)

    @extend_schema(request=OrderStatusSerializer, responses=OrderSerializer)
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def set_status(self, request, pk=None):
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.change_status(self.get_object(), serializer.validated_data["status"])
        return Response(OrderSerializer(self.get_queryset().get(pk=order.pk)).data)
