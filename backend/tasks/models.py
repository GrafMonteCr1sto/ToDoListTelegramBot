from django.db import models
from django.contrib.auth.models import User
import time
from django.utils import timezone

class CustomPrimaryKeyField(models.BigIntegerField):
    def __init__(self, *args, **kwargs):
        kwargs['primary_key'] = True
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        if add and getattr(model_instance, self.attname) is None:
            # Используем timestamp в микросекундах как основу для PK
            setattr(model_instance, self.attname, int(time.time() * 1000000))
        return super().pre_save(model_instance, add)

class Category(models.Model):
    id = CustomPrimaryKeyField()
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

class Task(models.Model):
    id = CustomPrimaryKeyField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    categories = models.ManyToManyField(Category, related_name='tasks')
    
    def __str__(self):
        return self.title
    
    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['-created_at']
        
    def is_overdue(self):
        """Проверяет, просрочена ли задача."""
        if self.due_date and not self.completed:
            return timezone.now() > self.due_date
        return False 