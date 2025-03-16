"""
Сервис комментариев для ToDo приложения.
Обеспечивает создание, получение и удаление комментариев к задачам.
Использует PostgreSQL для хранения данных и Redis для кэширования.
"""

from datetime import datetime
import json
import logging
import os
from typing import List

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, constr
import redis
from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройка подключения к базе данных PostgreSQL
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://todo_user:todo_password@postgres/todo_db"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Подключение к Redis для кэширования
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=1,
    decode_responses=True  # Автоматически декодировать ответы из bytes в str
)

class Comment(Base):
    """Модель комментария в базе данных."""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, nullable=False)
    text = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

# Создаем таблицы при запуске приложения
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {e}")
    raise

class CommentBase(BaseModel):
    """Базовая Pydantic модель для валидации комментариев."""
    text: constr(min_length=1, max_length=500)

class CommentCreate(CommentBase):
    """Модель для создания нового комментария."""
    task_id: int

class CommentResponse(CommentBase):
    """Модель для ответа с данными комментария."""
    id: int
    task_id: int
    created_at: datetime

    class Config:
        from_attributes = True

def get_db() -> Session:
    """
    Зависимость для получения сессии базы данных.
    Автоматически закрывает сессию после использования.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(
    title="Comments Service",
    description="Сервис для управления комментариями к задачам",
    version="1.0.0"
)

@app.post("/comments/", response_model=CommentResponse)
def create_comment(comment: CommentCreate, db: Session = Depends(get_db)):
    try:
        logger.info(f"Creating comment for task {comment.task_id}: {comment.text}")
        db_comment = Comment(
            task_id=comment.task_id,
            text=comment.text
        )
        db.add(db_comment)
        db.commit()
        db.refresh(db_comment)
        
        # Инвалидируем кэш для этой задачи
        redis_client.delete(f"comments:task:{comment.task_id}")
        
        logger.info(f"Comment created successfully: {db_comment.id}")
        return db_comment
    except Exception as e:
        logger.error(f"Error creating comment: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create comment: {str(e)}"
        )

@app.get("/comments/task/{task_id}", response_model=List[CommentResponse])
def get_task_comments(task_id: int, db: Session = Depends(get_db)):
    try:
        # Пробуем получить комментарии из кэша
        cached_comments = redis_client.get(f"comments:task:{task_id}")
        if cached_comments:
            return json.loads(cached_comments)
        
        # Если нет в кэше, получаем из БД
        comments = db.query(Comment).filter(Comment.task_id == task_id).all()
        
        # Сохраняем в кэш на 5 минут
        comments_data = [
            {
                "id": c.id,
                "task_id": c.task_id,
                "text": c.text,
                "created_at": c.created_at.isoformat()
            }
            for c in comments
        ]
        redis_client.setex(
            f"comments:task:{task_id}",
            300,  # 5 минут
            json.dumps(comments_data)
        )
        
        return comments
    except Exception as e:
        logger.error(f"Error getting comments for task {task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get comments: {str(e)}"
        )

@app.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db)):
    try:
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        
        # Инвалидируем кэш для этой задачи
        redis_client.delete(f"comments:task:{comment.task_id}")
        
        db.delete(comment)
        db.commit()
        return {"message": "Comment deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting comment {comment_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete comment: {str(e)}"
        ) 