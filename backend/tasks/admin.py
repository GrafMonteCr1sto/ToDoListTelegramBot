from django.contrib import admin
from .models import Task, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at', 'due_date', 'completed')
    list_filter = ('completed', 'categories')
    search_fields = ('title', 'description')
    raw_id_fields = ('user',)
    filter_horizontal = ('categories',) 