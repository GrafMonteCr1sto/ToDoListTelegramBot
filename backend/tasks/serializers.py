from rest_framework import serializers
from .models import Task, Category
from django.contrib.auth.models import User
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_name(self, value):
        if not value:
            raise serializers.ValidationError("Название категории не может быть пустым")
        return value

    def create(self, validated_data):
        logger.info(f"Creating category with data: {validated_data}")
        try:
            category = Category.objects.create(**validated_data)
            logger.info(f"Category created successfully: {category.id}")
            return category
        except Exception as e:
            logger.error(f"Error creating category: {str(e)}")
            raise

class TaskSerializer(serializers.ModelSerializer):
    categories = CategorySerializer(many=True, read_only=True)
    category_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    due_date = serializers.DateTimeField(required=False, allow_null=True)
    
    class Meta:
        model = Task
        fields = ['id', 'title', 'description', 'created_at', 'due_date', 
                 'completed', 'user', 'categories', 'category_ids']
        read_only_fields = ['user', 'id', 'created_at']
    
    def validate_due_date(self, value):
        """Валидация срока выполнения."""
        if value and value < timezone.now():
            raise serializers.ValidationError("Срок выполнения не может быть в прошлом")
        return value
    
    def create(self, validated_data):
        category_ids = validated_data.pop('category_ids', [])
        task = Task.objects.create(**validated_data)
        task.categories.set(Category.objects.filter(id__in=category_ids))
        return task
    
    def update(self, instance, validated_data):
        category_ids = validated_data.pop('category_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if category_ids is not None:
            instance.categories.set(Category.objects.filter(id__in=category_ids))
        
        return instance 