from celery import shared_task
from django.utils import timezone
from .models import Task

@shared_task
def check_due_tasks():
    """
    Проверяет задачи, у которых подходит срок выполнения
    """
    now = timezone.now()
    due_tasks = Task.objects.filter(
        due_date__date=now.date(),
        completed=False
    ).select_related('user')
    
    for task in due_tasks:
        # В реальном приложении здесь была бы логика отправки уведомлений
        # Например, через email или push-уведомления
        print(f"Task {task.title} for user {task.user.username} is due today!") 