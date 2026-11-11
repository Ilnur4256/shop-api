import django_filters

from shop.models import Order, Product


class ProductFilter(django_filters.FilterSet):
    price_min = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    category = django_filters.CharFilter(field_name="category__slug")

    class Meta:
        model = Product
        fields = ["category", "price_min", "price_max", "in_stock"]

    def filter_in_stock(self, queryset, name, value):
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)


class OrderFilter(django_filters.FilterSet):
    class Meta:
        model = Order
        fields = ["status"]
