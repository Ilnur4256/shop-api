from django.contrib import admin

from shop.models import Category, Order, OrderItem, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "price", "stock", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]
    list_editable = ["price", "stock", "is_active"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "quantity", "price"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "total", "created_at"]
    list_filter = ["status"]
    inlines = [OrderItemInline]
    readonly_fields = ["total"]
