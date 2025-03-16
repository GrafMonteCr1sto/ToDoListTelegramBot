"""
Telegram бот для управления задачами.
Позволяет создавать задачи, добавлять к ним комментарии и управлять категориями.
Взаимодействует с Django и FastAPI сервисами.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Конфигурация
logger.info("Starting bot initialization...")
logger.info(f"Environment variables: {dict(os.environ)}")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
logger.info(f"Raw TELEGRAM_TOKEN from env: {TELEGRAM_TOKEN}")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable is not set!")
    raise ValueError("TELEGRAM_TOKEN environment variable is not set!")

try:
    logger.info(f"Bot token prefix: {TELEGRAM_TOKEN.split(':')[0]}")
    logger.info(f"Bot token length: {len(TELEGRAM_TOKEN)}")
except Exception as e:
    logger.error(f"Error parsing token: {e}")

DJANGO_SERVICE_URL = os.environ.get("DJANGO_SERVICE_URL", "http://django:8000")
FASTAPI_SERVICE_URL = os.environ.get("FASTAPI_SERVICE_URL", "http://fastapi:8001")

logger.info(f"Django service URL: {DJANGO_SERVICE_URL}")
logger.info(f"FastAPI service URL: {FASTAPI_SERVICE_URL}")

# Клавиатуры для категорий
category_keyboard = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [
            types.InlineKeyboardButton(text="📝 Создать категорию", callback_data="create_category"),
            types.InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="delete_category")
        ],
        [
            types.InlineKeyboardButton(text="📋 Список категорий", callback_data="list_categories"),
            types.InlineKeyboardButton(text="🔍 Задачи по категории", callback_data="tasks_by_category")
        ],
        [
            types.InlineKeyboardButton(text="◀️ Назад к задачам", callback_data="back_to_tasks")
        ]
    ]
)

try:
    logger.info("Creating bot instance...")
    bot = Bot(token=TELEGRAM_TOKEN)
    logger.info("Bot instance created successfully")
    dp = Dispatcher()
    logger.info("Dispatcher created successfully")

    # Создаем основное меню бота
    main_menu_commands = [
        types.BotCommand(command="start", description="🚀 Запустить бота"),
        types.BotCommand(command="tasks", description="📋 Список задач"),
        types.BotCommand(command="add", description="➕ Добавить задачу"),
        types.BotCommand(command="categories", description="📁 Управление категориями"),
        types.BotCommand(command="search", description="🔍 Поиск по задачам"),
        types.BotCommand(command="stats", description="📊 Статистика"),
        types.BotCommand(command="deadlines", description="🔔 Дедлайны"),
        types.BotCommand(command="archive", description="📦 Архив задач"),
        types.BotCommand(command="help", description="❓ Помощь")
    ]

except Exception as e:
    logger.error(f"Error creating bot: {e}")
    raise

class TaskStates(StatesGroup):
    """Состояния для управления диалогом создания и редактирования задач."""
    selecting_action = State()
    adding_task = State()
    adding_task_description = State()
    selecting_category = State()
    adding_comment = State()
    setting_due_date = State()
    searching = State()

class CategoryStates(StatesGroup):
    """Состояния для управления диалогом работы с категориями."""
    selecting_action = State()
    adding_category = State()
    deleting_category = State()
    viewing_tasks = State()

async def get_tasks(user_id: int):
    async with aiohttp.ClientSession() as session:
        headers = {"X-Bot-Access": "true"}
        async with session.get(
            f"{DJANGO_SERVICE_URL}/api/tasks/",
            headers=headers
        ) as response:
            return await response.json()

async def get_categories():
    """Получение списка всех категорий."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DJANGO_SERVICE_URL}/api/categories/",
            headers={"X-Bot-Access": "true"}
        ) as response:
            if response.status == 200:
                return await response.json()
            logger.error(f"Error getting categories: {response.status}")
            return []

async def create_category(name: str):
    """Создание новой категории."""
    try:
        logger.info(f"Creating category with name: {name}")
        async with aiohttp.ClientSession() as session:
            headers = {
                "X-Bot-Access": "true",
                "Content-Type": "application/json"
            }
            data = {"name": name}
            url = f"{DJANGO_SERVICE_URL}/api/categories/"
            logger.info(f"Making request to: {url}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Data: {data}")
            
            async with session.post(
                url,
                json=data,
                headers=headers
            ) as response:
                response_text = await response.text()
                logger.info(f"Response status: {response.status}")
                logger.info(f"Response headers: {response.headers}")
                logger.info(f"Response text: {response_text}")
                
                if response.status != 201:
                    logger.error(f"Error creating category. Status: {response.status}")
                    logger.error(f"Response text: {response_text}")
                    return None
                
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing response JSON: {e}")
                    logger.error(f"Raw response text: {response_text}")
                    return None
    except Exception as e:
        logger.error(f"Error in create_category: {str(e)}")
        logger.exception("Full traceback:")
        return None

async def delete_category(category_id: int):
    """Удаление категории."""
    async with aiohttp.ClientSession() as session:
        async with session.delete(
            f"{DJANGO_SERVICE_URL}/api/categories/{category_id}/",
            headers={"X-Bot-Access": "true"}
        ) as response:
            return response.status == 204

async def get_tasks_by_category(category_id: int):
    """Получение списка задач в категории."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DJANGO_SERVICE_URL}/api/tasks/",
            headers={"X-Bot-Access": "true"}
        ) as response:
            if response.status == 200:
                tasks = await response.json()
                return [task for task in tasks if category_id in [cat['id'] for cat in task['categories']]]
            logger.error(f"Error getting tasks: {response.status}")
            return []

async def create_task(user_id: int, title: str, description: str, category_ids: list, due_date: str = None):
    try:
        logger.info(f"Creating task with data: user_id={user_id}, title={title}, description={description}, category_ids={category_ids}, due_date={due_date}")
        async with aiohttp.ClientSession() as session:
            headers = {
                "X-Bot-Access": "true",
                "Content-Type": "application/json"
            }
            data = {
                "title": title,
                "description": description or "",  # Убеждаемся, что description не будет None
                "category_ids": category_ids or [],  # Убеждаемся, что category_ids не будет None
                "completed": False,  # Добавляем статус по умолчанию
                "due_date": due_date
            }
            logger.info(f"Sending request to {DJANGO_SERVICE_URL}/api/tasks/ with data: {data}")
            async with session.post(
                f"{DJANGO_SERVICE_URL}/api/tasks/",
                json=data,
                headers=headers
            ) as response:
                logger.info(f"Received response with status: {response.status}")
                response_text = await response.text()
                logger.info(f"Response text: {response_text}")
                
                if response.status != 201 and response.status != 200:
                    logger.error(f"Error creating task. Status: {response.status}, Response: {response_text}")
                    raise ValueError(f"Failed to create task: {response_text}")
                
                try:
                    response_data = json.loads(response_text)
                    logger.info(f"Task created successfully: {response_data}")
                    return response_data
                except json.JSONDecodeError as json_error:
                    logger.error(f"Error parsing response JSON: {json_error}")
                    raise ValueError(f"Invalid response format: {response_text}")
    except Exception as e:
        logger.error(f"Error in create_task: {str(e)}")
        raise

async def get_comments(task_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{FASTAPI_SERVICE_URL}/comments/task/{task_id}"
        ) as response:
            return await response.json()

async def add_comment(task_id: int, text: str):
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "X-Bot-Access": "true",
                "Content-Type": "application/json"
            }
            data = {"task_id": task_id, "text": text}
            logger.info(f"Sending comment data: {data}")
            async with session.post(
                f"{FASTAPI_SERVICE_URL}/comments/",
                json=data,
                headers=headers
            ) as response:
                response_text = await response.text()
                logger.info(f"Comment creation response: {response_text}")
                
                if response.status != 201 and response.status != 200:
                    logger.error(f"Error creating comment. Status: {response.status}, Response: {response_text}")
                    raise ValueError(f"Failed to create comment: {response_text}")
                
                return await response.json()
    except Exception as e:
        logger.error(f"Error in add_comment: {str(e)}")
        raise

# Диалог для работы с задачами
async def get_tasks_keyboard():
    try:
        tasks = await get_tasks(0)  # 0 временно, нужно передавать реальный user_id
        keyboard = []
        
        if not tasks:
            keyboard.append([
                types.InlineKeyboardButton(
                    text="✨ Создать первую задачу",
                    callback_data="add_task"
                )
            ])
        else:
            for task in tasks:
                keyboard.append([
                    types.InlineKeyboardButton(
                        text=f"📝 {task['title']} ({task['created_at']})",
                        callback_data=f"task:{task['id']}"
                    )
                ])
            keyboard.append([
                types.InlineKeyboardButton(
                    text="➕ Добавить задачу",
                    callback_data="add_task"
                )
            ])
        
        keyboard.append([
            types.InlineKeyboardButton(
                text="❓ Помощь",
                callback_data="help"
            )
        ])
        
        keyboard.append([
            types.InlineKeyboardButton(
                text="◀️ Назад в меню",
                callback_data="back_to_menu"
            )
        ])
        
        return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        keyboard = [
            [types.InlineKeyboardButton(
                text="🔄 Попробовать снова",
                callback_data="retry_tasks"
            )],
            [types.InlineKeyboardButton(
                text="❓ Помощь",
                callback_data="help"
            )],
            [types.InlineKeyboardButton(
                text="◀️ Назад в меню",
                callback_data="back_to_menu"
            )]
        ]
        return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Активные задачи", callback_data="back_to_tasks")],
        [types.InlineKeyboardButton(text="📦 Архив задач", callback_data="show_archive")],
        [types.InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")],
        [types.InlineKeyboardButton(text="📁 Категории", callback_data="categories")],
        [types.InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

    await message.answer(
        "👋 Добро пожаловать в ToDo бот!\n\n"
        "🤖 Основные возможности:\n"
        "📝 Создание и управление задачами\n"
        "📦 Архив выполненных задач\n"
        "🏷 Работа с категориями\n"
        "🔍 Поиск по задачам\n"
        "📅 Установка сроков выполнения\n"
        "🔔 Уведомления о дедлайнах\n"
        "📊 Статистика выполнения\n\n"
        "Используйте команды:\n"
        "/tasks - список активных задач\n"
        "/archive - архив выполненных задач\n"
        "/add - добавить задачу\n"
        "/categories - управление категориями\n"
        "/search - поиск по задачам\n"
        "/stats - статистика\n"
        "/deadlines - приближающиеся дедлайны\n"
        "/help - помощь",
        reply_markup=keyboard
    )

@dp.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    try:
        keyboard = await get_tasks_keyboard()
        tasks = await get_tasks(0)
        
        if not tasks:
            text = "📋 У вас пока нет задач.\nНажмите кнопку ниже, чтобы создать первую задачу!"
        else:
            text = "📋 Ваши задачи:\nВыберите задачу, чтобы просмотреть комментарии или добавить новую"
        
        await message.answer(text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error in cmd_tasks: {e}")
        await message.answer(
            "😔 Извините, произошла ошибка при получении списка задач.\n"
            "Пожалуйста, попробуйте позже или нажмите кнопку 'Попробовать снова'",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="🔄 Попробовать снова",
                    callback_data="retry_tasks"
                )]
            ])
        )

@dp.callback_query(lambda c: c.data == "retry_tasks")
async def retry_tasks(callback_query: types.CallbackQuery):
    await cmd_tasks(callback_query.message)
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "help")
async def show_help(callback_query: types.CallbackQuery):
    help_text = (
        "🤖 *Как пользоваться ботом:*\n\n"
        "*Основные команды:*\n"
        "📋 */tasks* - просмотр и управление задачами\n"
        "➕ */add* - создание новой задачи\n"
        "📁 */categories* - управление категориями\n"
        "🔍 */search* - поиск по задачам\n"
        "📊 */stats* - статистика выполнения\n"
        "🔔 */deadlines* - приближающиеся дедлайны\n\n"
        "*Управление задачами:*\n"
        "✅ Отметить как выполненную\n"
        "🗑 Удалить задачу\n"
        "📝 Добавить комментарий\n"
        "📅 Установить срок выполнения\n\n"
        "*Категории:*\n"
        "📝 Создать категорию\n"
        "🗑 Удалить категорию\n"
        "📋 Просмотреть список\n"
        "🔍 Фильтровать задачи по категории\n\n"
        "❓ Если возникли проблемы:\n"
        "• Используйте /start для перезапуска\n"
        "• Нажмите 'Отмена' в любом диалоге\n"
        "• Обновите список задач через /tasks"
    )
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Мои задачи", callback_data="back_to_tasks")],
        [types.InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")],
        [types.InlineKeyboardButton(text="📁 Категории", callback_data="categories")]
    ])
    
    await callback_query.message.edit_text(
        help_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("task:"))
async def process_task(callback_query: types.CallbackQuery):
    try:
        task_id = int(callback_query.data.split(":")[1])
        comments = await get_comments(task_id)
        
        text = "💬 *Комментарии к задаче:*\n\n"
        if not comments:
            text += "Пока нет комментариев. Будьте первым!\n"
        else:
            for comment in comments:
                text += f"• _{comment['text']}_\n"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Выполнено", callback_data=f"complete_task:{task_id}"),
                types.InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_task:{task_id}")
            ],
            [types.InlineKeyboardButton(text="✏️ Добавить комментарий", callback_data=f"add_comment:{task_id}")],
            [types.InlineKeyboardButton(text="◀️ Назад к задачам", callback_data="back_to_tasks")]
        ])
        
        await callback_query.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error processing task: {e}")
        await callback_query.message.edit_text(
            "😔 Извините, произошла ошибка при получении комментариев.\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="◀️ Вернуться к задачам", callback_data="back_to_tasks")]
            ])
        )

@dp.callback_query(lambda c: c.data.startswith("complete_task:"))
async def complete_task(callback_query: types.CallbackQuery):
    """Обработчик отметки задачи как выполненной."""
    try:
        task_id = int(callback_query.data.split(":")[1])
        updated_task = await update_task(task_id, {"completed": True})
        
        if updated_task:
            await callback_query.answer("✅ Задача перемещена в архив!")
            keyboard = await get_tasks_keyboard()
            await callback_query.message.edit_text(
                "Ваши активные задачи:",
                reply_markup=keyboard
            )
        else:
            await callback_query.answer("❌ Не удалось обновить задачу")
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        await callback_query.answer("❌ Произошла ошибка")

@dp.callback_query(lambda c: c.data.startswith("delete_task:"))
async def confirm_delete_task(callback_query: types.CallbackQuery):
    """Обработчик подтверждения удаления задачи."""
    task_id = int(callback_query.data.split(":")[1])
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete:{task_id}"),
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_tasks")
        ]
    ])
    await callback_query.message.edit_text(
        "❗️ Вы уверены, что хотите удалить эту задачу?",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith("confirm_delete:"))
async def delete_task_handler(callback_query: types.CallbackQuery):
    """Обработчик удаления задачи."""
    try:
        task_id = int(callback_query.data.split(":")[1])
        if await delete_task(task_id):
            await callback_query.answer("✅ Задача успешно удалена!")
            keyboard = await get_tasks_keyboard()
            await callback_query.message.edit_text(
                "Ваши задачи:",
                reply_markup=keyboard
            )
        else:
            await callback_query.answer("❌ Не удалось удалить задачу")
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        await callback_query.answer("❌ Произошла ошибка")

@dp.callback_query(lambda c: c.data == "add_task")
async def process_add_task(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(TaskStates.adding_task)
    await callback_query.message.edit_text(
        "📝 *Создание новой задачи*\n\n"
        "Введите название задачи.\n"
        "Например: '_Купить продукты_' или '_Позвонить маме_'",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel"
            )]
        ]),
        parse_mode="Markdown"
    )

@dp.message(TaskStates.adding_task)
async def process_task_title(message: types.Message, state: FSMContext):
    """Обработчик ввода названия задачи."""
    await state.update_data(title=message.text)
    await state.set_state(TaskStates.adding_task_description)
    
    # Создаем клавиатуру с кнопкой пропуска описания
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Пропустить", callback_data="skip_description")]
    ])
    
    await message.answer(
        "Введите описание задачи или нажмите 'Пропустить':",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "skip_description")
async def skip_description(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик пропуска описания задачи."""
    await callback_query.answer()
    await state.update_data(description="")
    
    # Запрашиваем срок выполнения
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Сегодня", callback_data="due_today")],
        [types.InlineKeyboardButton(text="Завтра", callback_data="due_tomorrow")],
        [types.InlineKeyboardButton(text="Через неделю", callback_data="due_week")],
        [types.InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_due_date")]
    ])
    
    await state.set_state(TaskStates.setting_due_date)
    await callback_query.message.answer(
        "📅 Выберите срок выполнения задачи:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith("due_"))
async def process_due_date(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора срока выполнения."""
    await callback_query.answer()
    
    today = datetime.now()
    if callback_query.data == "due_today":
        due_date = today
    elif callback_query.data == "due_tomorrow":
        due_date = today + timezone.timedelta(days=1)
    elif callback_query.data == "due_week":
        due_date = today + timezone.timedelta(days=7)
    else:  # skip_due_date
        due_date = None
    
    await state.update_data(due_date=due_date.isoformat() if due_date else None)
    
    # Переходим к выбору категории
    categories = await get_categories()
    if categories:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text=cat['name'],
                callback_data=f"cat_{cat['id']}"
            )] for cat in categories
        ] + [[types.InlineKeyboardButton(
            text="➡️ Без категории",
            callback_data="skip_category"
        )]])
        
        await state.set_state(TaskStates.selecting_category)
        await callback_query.message.edit_text(
            "Выберите категорию для задачи:",
            reply_markup=keyboard
        )
    else:
        # Если категорий нет, создаем задачу без категории
        data = await state.get_data()
        task = await create_task(
            callback_query.from_user.id,
            data['title'],
            data['description'],
            [],
            data.get('due_date')
        )
        if task:
            text = f"✅ Задача '{task['title']}' успешно создана!"
            if task.get('due_date'):
                text += f"\n📅 Срок выполнения: {task['due_date']}"
            await callback_query.message.edit_text(text)
        else:
            await callback_query.message.edit_text(
                "❌ Не удалось создать задачу. Попробуйте позже."
            )
        await state.clear()

@dp.message(TaskStates.adding_task_description)
async def process_task_description(message: types.Message, state: FSMContext):
    """Обработчик ввода описания задачи."""
    await state.update_data(description=message.text)
    
    # Запрашиваем срок выполнения
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Сегодня", callback_data="due_today")],
        [types.InlineKeyboardButton(text="Завтра", callback_data="due_tomorrow")],
        [types.InlineKeyboardButton(text="Через неделю", callback_data="due_week")],
        [types.InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_due_date")]
    ])
    
    await state.set_state(TaskStates.setting_due_date)
    await message.answer(
        "📅 Выберите срок выполнения задачи:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith("cat_"))
async def process_category_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора категории при создании задачи."""
    await callback_query.answer()
    category_id = int(callback_query.data.split("_")[1])
    data = await state.get_data()
    
    task = await create_task(
        callback_query.from_user.id,
        data['title'],
        data['description'],
        [category_id],
        data.get('due_date')
    )
    
    if task:
        await callback_query.message.answer(
            f"✅ Задача '{task['title']}' успешно создана и добавлена в выбранную категорию!"
        )
    else:
        await callback_query.message.answer(
            "❌ Не удалось создать задачу. Попробуйте позже."
        )
    await state.clear()

@dp.callback_query(lambda c: c.data == "skip_category")
async def skip_category(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик пропуска выбора категории."""
    await callback_query.answer()
    data = await state.get_data()
    
    task = await create_task(
        callback_query.from_user.id,
        data['title'],
        data['description'],
        [],
        data.get('due_date')
    )
    
    if task:
        await callback_query.message.answer(
            f"✅ Задача '{task['title']}' успешно создана!"
        )
    else:
        await callback_query.message.answer(
            "❌ Не удалось создать задачу. Попробуйте позже."
        )
    await state.clear()

@dp.callback_query(lambda c: c.data == "back_to_tasks")
async def back_to_tasks(callback_query: types.CallbackQuery):
    keyboard = await get_tasks_keyboard()
    await callback_query.message.edit_text("Ваши задачи:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_operation(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    keyboard = await get_tasks_keyboard()
    await callback_query.message.edit_text("Операция отменена. Ваши задачи:", reply_markup=keyboard)

@dp.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
    """Обработчик команды /add."""
    await state.set_state(TaskStates.adding_task)
    await message.answer("Введите название задачи:")

@dp.message(Command("categories"))
async def cmd_categories(message: types.Message, state: FSMContext):
    """Обработчик команды /categories."""
    await state.set_state(CategoryStates.selecting_action)
    await message.answer(
        "📁 Управление категориями\n\n"
        "Выберите действие:",
        reply_markup=category_keyboard
    )

@dp.callback_query(lambda c: c.data == "create_category")
async def process_create_category(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик нажатия кнопки создания категории."""
    await callback_query.answer()
    await state.set_state(CategoryStates.adding_category)
    await callback_query.message.answer("Введите название новой категории:")

@dp.message(CategoryStates.adding_category)
async def add_category(message: types.Message, state: FSMContext):
    """Обработчик ввода названия новой категории."""
    category = await create_category(message.text)
    if category:
        await message.answer(f"✅ Категория '{category['name']}' успешно создана!")
    else:
        await message.answer("❌ Не удалось создать категорию. Попробуйте позже.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "list_categories")
async def process_list_categories(callback_query: types.CallbackQuery):
    """Обработчик нажатия кнопки просмотра списка категорий."""
    await callback_query.answer()
    categories = await get_categories()
    if categories:
        text = "📁 Список категорий:\n\n"
        for cat in categories:
            text += f"• {cat['name']}\n"
        await callback_query.message.answer(text)
    else:
        await callback_query.message.answer("Список категорий пуст.")

@dp.callback_query(lambda c: c.data == "delete_category")
async def process_delete_category(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик нажатия кнопки удаления категории."""
    await callback_query.answer()
    categories = await get_categories()
    if not categories:
        await callback_query.message.answer("Нет доступных категорий для удаления.")
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text=cat['name'],
            callback_data=f"del_cat_{cat['id']}"
        )] for cat in categories
    ])
    await state.set_state(CategoryStates.deleting_category)
    await callback_query.message.answer(
        "Выберите категорию для удаления:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith("del_cat_"))
async def delete_category_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора категории для удаления."""
    await callback_query.answer()
    category_id = int(callback_query.data.split("_")[2])
    if await delete_category(category_id):
        await callback_query.message.answer("✅ Категория успешно удалена!")
    else:
        await callback_query.message.answer("❌ Не удалось удалить категорию. Попробуйте позже.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "tasks_by_category")
async def process_tasks_by_category(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик нажатия кнопки просмотра задач по категории."""
    await callback_query.answer()
    categories = await get_categories()
    if not categories:
        await callback_query.message.answer("Нет доступных категорий.")
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text=cat['name'],
            callback_data=f"view_cat_{cat['id']}"
        )] for cat in categories
    ])
    await state.set_state(CategoryStates.viewing_tasks)
    await callback_query.message.answer(
        "Выберите категорию для просмотра задач:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith("view_cat_"))
async def view_category_tasks(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора категории для просмотра задач."""
    await callback_query.answer()
    category_id = int(callback_query.data.split("_")[2])
    tasks = await get_tasks_by_category(category_id)
    
    if tasks:
        text = "📋 Задачи в выбранной категории:\n\n"
        for task in tasks:
            status = "✅" if task['completed'] else "⏳"
            text += f"{status} {task['title']}\n"
            if task['description']:
                text += f"📝 {task['description']}\n"
            text += "\n"
        await callback_query.message.answer(text)
    else:
        await callback_query.message.answer("В этой категории нет задач.")
    await state.clear()

@dp.message(Command("search"))
async def cmd_search(message: types.Message, state: FSMContext):
    """Обработчик команды /search."""
    await state.set_state(TaskStates.searching)
    await message.answer(
        "🔍 Введите текст для поиска по задачам:\n"
        "(поиск будет выполнен по названию и описанию задач)",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])
    )

@dp.message(TaskStates.searching)
async def process_search(message: types.Message, state: FSMContext):
    """Обработчик поискового запроса."""
    tasks = await search_tasks(message.text)
    if tasks:
        text = "🔍 Результаты поиска:\n\n"
        for task in tasks:
            status = "✅" if task['completed'] else "⏳"
            text += f"{status} {task['title']}\n"
            if task['description']:
                text += f"📝 {task['description']}\n"
            if task['due_date']:
                text += f"📅 Срок: {task['due_date']}\n"
            text += "\n"
    else:
        text = "😔 Ничего не найдено"
    
    await message.answer(text)
    await state.clear()

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Обработчик команды /stats."""
    stats = await get_statistics()
    if stats:
        text = (
            "📊 Статистика по задачам:\n\n"
            f"Всего задач: {stats['total_tasks']}\n"
            f"Выполнено: {stats['completed_tasks']}\n"
            f"Процент выполнения: {stats['completion_rate']}\n"
            f"Просрочено: {stats['overdue_tasks']}"
        )
    else:
        text = "😔 Не удалось получить статистику"
    
    await message.answer(text)

@dp.message(Command("deadlines"))
async def cmd_deadlines(message: types.Message):
    """Обработчик команды /deadlines."""
    tasks = await get_upcoming_deadlines()
    if tasks:
        text = "🔔 Приближающиеся дедлайны:\n\n"
        for task in tasks:
            text += f"📅 {task['due_date']}\n"
            text += f"📝 {task['title']}\n"
            if task['description']:
                text += f"ℹ️ {task['description']}\n"
            text += "\n"
    else:
        text = "🎉 Нет приближающихся дедлайнов"
    
    await message.answer(text)

@dp.message(Command("archive"))
async def cmd_archive(message: types.Message):
    """Обработчик команды /archive."""
    tasks = await get_archived_tasks()
    if tasks:
        text = "📦 *Архив выполненных задач:*\n\n"
        for task in tasks:
            text += f"✅ *{task['title']}*\n"
            if task['description']:
                text += f"📝 {task['description']}\n"
            if task['due_date']:
                text += f"📅 Выполнено: {task['due_date']}\n"
            text += "\n"
    else:
        text = "📦 Архив пуст"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Активные задачи", callback_data="back_to_tasks")]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "show_archive")
async def show_archive(callback_query: types.CallbackQuery):
    """Обработчик кнопки просмотра архива."""
    tasks = await get_archived_tasks()
    if tasks:
        text = "📦 *Архив выполненных задач:*\n\n"
        for task in tasks:
            text += f"✅ *{task['title']}*\n"
            if task['description']:
                text += f"📝 {task['description']}\n"
            if task['due_date']:
                text += f"📅 Выполнено: {task['due_date']}\n"
            text += "\n"
    else:
        text = "📦 Архив пуст"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Активные задачи", callback_data="back_to_tasks")]
    ])
    
    await callback_query.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    """Обработчик возврата в главное меню."""
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Активные задачи", callback_data="back_to_tasks")],
        [types.InlineKeyboardButton(text="📦 Архив задач", callback_data="show_archive")],
        [types.InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task")],
        [types.InlineKeyboardButton(text="📁 Категории", callback_data="categories")],
        [types.InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

    await callback_query.message.edit_text(
        "🤖 Главное меню\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

async def search_tasks(query: str):
    """Поиск задач по запросу."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"X-Bot-Access": "true"}
            params = {"search": query}
            async with session.get(
                f"{DJANGO_SERVICE_URL}/api/tasks/search/",
                headers=headers,
                params=params
            ) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Error searching tasks: {response.status}")
                return []
    except Exception as e:
        logger.error(f"Error in search_tasks: {str(e)}")
        return []

async def get_statistics():
    """Получение статистики по задачам."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"X-Bot-Access": "true"}
            params = {"show_completed": "true"}  # Добавляем параметр для получения всех задач
            async with session.get(
                f"{DJANGO_SERVICE_URL}/api/tasks/",
                headers=headers,
                params=params
            ) as response:
                if response.status == 200:
                    tasks = await response.json()
                    total_tasks = len(tasks)
                    completed_tasks = len([task for task in tasks if task['completed']])
                    completion_rate = f"{(completed_tasks / total_tasks * 100):.1f}%" if total_tasks > 0 else "0%"
                    overdue_tasks = len([
                        task for task in tasks 
                        if not task['completed'] 
                        and task.get('due_date') 
                        and datetime.fromisoformat(task['due_date'].replace('Z', '+00:00')) < datetime.now(timezone.utc)
                    ])
                    
                    return {
                        'total_tasks': total_tasks,
                        'completed_tasks': completed_tasks,
                        'completion_rate': completion_rate,
                        'overdue_tasks': overdue_tasks
                    }
                logger.error(f"Error getting tasks for statistics: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error in get_statistics: {str(e)}")
        return None

async def get_upcoming_deadlines():
    """Получение списка приближающихся дедлайнов."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"X-Bot-Access": "true"}
            async with session.get(
                f"{DJANGO_SERVICE_URL}/api/tasks/upcoming_deadlines/",
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Error getting deadlines: {response.status}")
                return []
    except Exception as e:
        logger.error(f"Error in get_upcoming_deadlines: {str(e)}")
        return []

async def update_task(task_id: int, data: dict):
    """Обновление задачи."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "X-Bot-Access": "true",
                "Content-Type": "application/json"
            }
            async with session.patch(
                f"{DJANGO_SERVICE_URL}/api/tasks/{task_id}/",
                json=data,
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Error updating task: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error in update_task: {str(e)}")
        return None

async def delete_task(task_id: int):
    """Удаление задачи."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"X-Bot-Access": "true"}
            async with session.delete(
                f"{DJANGO_SERVICE_URL}/api/tasks/{task_id}/",
                headers=headers
            ) as response:
                return response.status == 204
    except Exception as e:
        logger.error(f"Error in delete_task: {str(e)}")
        return False

async def get_archived_tasks():
    """Получение списка выполненных задач."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"X-Bot-Access": "true"}
            params = {"show_completed": "true"}
            async with session.get(
                f"{DJANGO_SERVICE_URL}/api/tasks/",
                headers=headers,
                params=params
            ) as response:
                if response.status == 200:
                    tasks = await response.json()
                    # Фильтруем только выполненные задачи
                    return [task for task in tasks if task['completed']]
                logger.error(f"Error getting archived tasks: {response.status}")
                return []
    except Exception as e:
        logger.error(f"Error in get_archived_tasks: {str(e)}")
        return []

async def main():
    # Устанавливаем команды в меню
    try:
        await bot.set_my_commands(main_menu_commands)
        logger.info("Bot commands set successfully")
    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")

    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 