from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import Task, Category
from .serializers import TaskSerializer, CategorySerializer
from django.db.models import Prefetch, Q
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import User
import logging
from django.db import models

logger = logging.getLogger(__name__)

class IsAuthenticatedOrBot(permissions.BasePermission):
    def has_permission(self, request, view):
        # Проверяем, является ли запрос от бота (по специальному заголовку)
        is_bot = request.headers.get('X-Bot-Access') == 'true'
        if is_bot:
            # Добавляем системного пользователя в request
            try:
                request.user = User.objects.get_or_create(
                    username='telegram_bot',
                    defaults={'is_active': True}
                )[0]
                logger.info(f"Bot user authenticated: {request.user.username}")
            except Exception as e:
                logger.error(f"Error getting/creating bot user: {e}")
                return False
        return is_bot or request.user.is_authenticated

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrBot]

    def create(self, request, *args, **kwargs):
        logger.info(f"Incoming category creation request data: {request.data}")
        logger.info(f"Request headers: {request.headers}")
        response = super().create(request, *args, **kwargs)
        logger.info(f"Category creation response data: {response.data}")
        return response

class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrBot]
    
    def get_queryset(self):
        queryset = Task.objects.all().prefetch_related('categories').select_related('user')
        
        if not self.request.headers.get('X-Bot-Access') == 'true':
            queryset = queryset.filter(user=self.request.user)
        
        # Фильтруем по статусу completed, если не указан параметр show_completed
        show_completed = self.request.query_params.get('show_completed', 'false').lower() == 'true'
        if not show_completed:
            queryset = queryset.filter(completed=False)
        
        # Поиск по названию и описанию
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                models.Q(title__icontains=search_query) |
                models.Q(description__icontains=search_query)
            )
        
        # Фильтрация по срокам
        due_filter = self.request.query_params.get('due', None)
        if due_filter:
            today = timezone.now().date()
            if due_filter == 'today':
                queryset = queryset.filter(due_date__date=today)
            elif due_filter == 'week':
                week_later = today + timezone.timedelta(days=7)
                queryset = queryset.filter(due_date__date__range=[today, week_later])
            elif due_filter == 'overdue':
                queryset = queryset.filter(due_date__date__lt=today, completed=False)
        
        return queryset

    def create(self, request, *args, **kwargs):
        logger.info(f"Incoming task creation request data: {request.data}")
        response = super().create(request, *args, **kwargs)
        logger.info(f"Task creation response data: {response.data}")
        return response
    
    def perform_create(self, serializer):
        if self.request.headers.get('X-Bot-Access') == 'true':
            try:
                bot_user = User.objects.get(username='telegram_bot')
                logger.info(f"Creating task for bot user: {bot_user.username}")
                serializer.save(user=bot_user)
            except User.DoesNotExist:
                bot_user = User.objects.create(
                    username='telegram_bot',
                    is_active=True
                )
                logger.info(f"Created new bot user and task: {bot_user.username}")
                serializer.save(user=bot_user)
        else:
            logger.info(f"Creating task for authenticated user: {self.request.user.username}")
            serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def due_today(self, request):
        today = timezone.now()
        tasks = self.get_queryset().filter(
            due_date__date=today.date(),
            completed=False
        )
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Поиск задач по названию и описанию."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Получение статистики по задачам."""
        queryset = self.get_queryset()
        total_tasks = queryset.count()
        completed_tasks = queryset.filter(completed=True).count()
        overdue_tasks = queryset.filter(
            due_date__date__lt=timezone.now().date(),
            completed=False
        ).count()
        
        return Response({
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': f"{(completed_tasks/total_tasks*100):.1f}%" if total_tasks > 0 else "0%",
            'overdue_tasks': overdue_tasks
        })

    @action(detail=False, methods=['get'])
    def upcoming_deadlines(self, request):
        """Получение списка приближающихся дедлайнов."""
        today = timezone.now().date()
        week_later = today + timezone.timedelta(days=7)
        
        queryset = self.get_queryset().filter(
            due_date__date__range=[today, week_later],
            completed=False
        ).order_by('due_date')
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def archive(self, request):
        """Получение списка выполненных задач."""
        queryset = self.get_queryset().filter(completed=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data) 