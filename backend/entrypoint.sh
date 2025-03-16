#!/bin/bash

# Ждем, пока PostgreSQL будет готов
echo "Waiting for PostgreSQL..."
while ! nc -z postgres 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

# Применяем миграции
echo "Applying migrations..."
python manage.py makemigrations
python manage.py migrate

# Создаем суперпользователя, если его нет
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'admin') if not User.objects.filter(username='admin').exists() else None" | python manage.py shell

# Запускаем сервер
echo "Starting server..."
gunicorn todo.wsgi:application --bind 0.0.0.0:8000 --workers 2 