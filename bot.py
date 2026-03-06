import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Any
from enum import Enum
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
)

# --- Состояния для разговоров ---
(PHONE_NUMBER, SELECT_CATEGORY, SELECT_PRODUCT, SELECT_QUANTITY, 
 CONFIRM_ORDER, ADMIN_MENU, ADMIN_CATEGORY, ADMIN_PRODUCT_NAME,
 ADMIN_PRODUCT_PRICE, ADMIN_PRODUCT_EXPIRY, ADMIN_PRODUCT_PHOTO) = range(11)

# --- Настройки ---
TOKEN = "8557367254:AAFV2Tg9mVuv5qSPu1-LKrDHKAVJLZ" Твой токен
ADMIN_IDS = [190416203]  # Замени на свой ID

# Файлы для хранения данных
USERS_FILE = "users.json"
CATEGORIES_FILE = "categories.json"
PRODUCTS_FILE = "products.json"
ORDERS_FILE = "orders.json"

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Классы данных ---
class User:
    def __init__(self, user_id: int, phone: str, name: str = "", username: str = ""):
        self.user_id = user_id
        self.phone = phone
        self.name = name
        self.username = username
        self.registered_at = datetime.now().isoformat()
        self.cart = {}  # {product_id: quantity}

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "phone": self.phone,
            "name": self.name,
            "username": self.username,
            "registered_at": self.registered_at,
            "cart": self.cart
        }

    @classmethod
    def from_dict(cls, data):
        user = cls(data["user_id"], data["phone"], data.get("name", ""), data.get("username", ""))
        user.registered_at = data.get("registered_at", datetime.now().isoformat())
        user.cart = data.get("cart", {})
        return user

class Category:
    def __init__(self, cat_id: str, name: str):
        self.id = cat_id
        self.name = name

    def to_dict(self):
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, data):
        return cls(data["id"], data["name"])

class Product:
    def __init__(self, product_id: str, category_id: str, name: str, 
                 price: float, expiry_date: str, photo_id: str = None):
        self.id = product_id
        self.category_id = category_id
        self.name = name
        self.price = price
        self.expiry_date = expiry_date
        self.photo_id = photo_id

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "name": self.name,
            "price": self.price,
            "expiry_date": self.expiry_date,
            "photo_id": self.photo_id
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["id"],
            data["category_id"],
            data["name"],
            data["price"],
            data["expiry_date"],
            data.get("photo_id")
        )

class Order:
    def __init__(self, order_id: str, user_id: int, items: Dict, 
                 total: float, phone: str, status: str = "new"):
        self.id = order_id
        self.user_id = user_id
        self.items = items  # {product_id: {"name": str, "quantity": int, "price": float}}
        self.total = total
        self.phone = phone
        self.status = status
        self.created_at = datetime.now().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "items": self.items,
            "total": self.total,
            "phone": self.phone,
            "status": self.status,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data):
        order = cls(
            data["id"],
            data["user_id"],
            data["items"],
            data["total"],
            data["phone"],
            data.get("status", "new")
        )
        order.created_at = data.get("created_at", datetime.now().isoformat())
        return order

# --- Работа с данными ---
def load_data(file_path: str, default: Any = None) -> Any:
    if default is None:
        if file_path == USERS_FILE:
            default = {}
        elif file_path == CATEGORIES_FILE:
            default = {}
        elif file_path == PRODUCTS_FILE:
            default = {}
        elif file_path == ORDERS_FILE:
            default = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка загрузки {file_path}: {e}")
            return default
    return default

def save_data(file_path: str, data: Any) -> None:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Ошибка сохранения {file_path}: {e}")

def get_user(user_id: int) -> User:
    users_data = load_data(USERS_FILE, {})
    user_data = users_data.get(str(user_id))
    if user_data:
        return User.from_dict(user_data)
    return None

def save_user(user: User) -> None:
    users_data = load_data(USERS_FILE, {})
    users_data[str(user.user_id)] = user.to_dict()
    save_data(USERS_FILE, users_data)

def save_user_cart(user: User) -> None:
    users_data = load_data(USERS_FILE, {})
    if str(user.user_id) in users_data:
        users_data[str(user.user_id)]["cart"] = user.cart
        save_data(USERS_FILE, users_data)

# --- Обработчики команд ---

async def start(update: Update, context: CallbackContext) -> int:
    """Начало работы - запрос номера телефона"""
    user_id = update.effective_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    user = get_user(user_id)
    if user:
        # Если уже зарегистрирован, показываем главное меню
        await show_main_menu(update, context)
        return SELECT_CATEGORY
    
    # Запрашиваем номер телефона
    reply_keyboard = [[KeyboardButton("📱 Отправить номер телефона", request_contact=True)]]
    await update.message.reply_text(
        "Добро пожаловать! Для продолжения нужна регистрация.\n"
        "Нажми кнопку ниже, чтобы отправить свой номер телефона:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PHONE_NUMBER

async def phone_handler(update: Update, context: CallbackContext) -> int:
    """Обработка полученного номера телефона"""
    contact = update.message.contact
    user_id = update.effective_user.id
    
    if contact and contact.user_id == user_id:
        phone = contact.phone_number
        user = User(
            user_id=user_id,
            phone=phone,
            name=update.effective_user.full_name,
            username=update.effective_user.username
        )
        save_user(user)
        
        await update.message.reply_text(
            f"✅ Регистрация успешна!\n"
            f"Ваш номер: {phone}",
            reply_markup=ReplyKeyboardMarkup.remove_keyboard()
        )
        
        await show_main_menu(update, context)
        return SELECT_CATEGORY
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопку 'Отправить номер телефона'"
        )
        return PHONE_NUMBER

async def show_main_menu(update: Update, context: CallbackContext) -> None:
    """Показывает главное меню с категориями"""
    categories_data = load_data(CATEGORIES_FILE, {})
    
    if not categories_data:
        keyboard = [[InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "Пока нет доступных категорий. Загляните позже!",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "Пока нет доступных категорий. Загляните позже!",
                reply_markup=reply_markup
            )
        return
    
    # Создаем кнопки категорий
    keyboard = []
    for cat_id, cat_name in categories_data.items():
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=f"cat_{cat_id}")])
    
    # Добавляем кнопку корзины
    keyboard.append([InlineKeyboardButton("🛒 Моя корзина", callback_data="view_cart")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Проверяем, откуда пришел вызов
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Выбери категорию:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Выбери категорию:",
            reply_markup=reply_markup
        )

async def show_category_products(update: Update, context: CallbackContext, category_id: str) -> None:
    """Показывает товары в выбранной категории"""
    products_data = load_data(PRODUCTS_FILE, {})
    category_products = {pid: p for pid, p in products_data.items() 
                        if p.get("category_id") == category_id}
    
    if not category_products:
        keyboard = [[InlineKeyboardButton("◀️ Назад к категориям", callback_data="back_to_categories")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            "В этой категории пока нет товаров",
            reply_markup=reply_markup
        )
        return
    
    # Показываем товары по одному с навигацией
    context.user_data["current_category"] = category_id
    context.user_data["category_products"] = list(category_products.keys())
    context.user_data["current_product_index"] = 0
    
    await show_product(update, context)

async def show_product(update: Update, context: CallbackContext) -> None:
    """Показывает конкретный товар"""
    products_data = load_data(PRODUCTS_FILE, {})
    product_ids = context.user_data.get("category_products", [])
    index = context.user_data.get("current_product_index", 0)
    
    if not product_ids or index >= len(product_ids):
        return
    
    product_id = product_ids[index]
    product_data = products_data.get(product_id)
    
    if not product_data:
        return
    
    product = Product.from_dict(product_data)
    
    # Создаем клавиатуру для товара
    keyboard = [
        [
            InlineKeyboardButton("⬅️", callback_data="prev_product"),
            InlineKeyboardButton(f"{index+1}/{len(product_ids)}", callback_data="noop"),
            InlineKeyboardButton("➡️", callback_data="next_product")
        ],
        [InlineKeyboardButton("➕ Добавить в корзину", callback_data=f"add_{product_id}")],
        [InlineKeyboardButton("◀️ Назад к категориям", callback_data="back_to_categories")],
        [InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем текст товара
    product_text = (
        f"📦 *{product.name}*\n\n"
        f"💰 Цена: {product.price} ₽\n"
        f"📅 Годен до: {product.expiry_date}\n\n"
        f"Выбери действие:"
    )
    
    # Отправляем фото, если есть
    if product.photo_id:
        await update.callback_query.message.delete()
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=product.photo_id,
            caption=product_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            product_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def add_to_cart(update: Update, context: CallbackContext, product_id: str) -> int:
    """Добавление товара в корзину с выбором количества"""
    context.user_data["adding_product"] = product_id
    keyboard = [
        [InlineKeyboardButton("1", callback_data="qty_1"),
         InlineKeyboardButton("2", callback_data="qty_2"),
         InlineKeyboardButton("3", callback_data="qty_3")],
        [InlineKeyboardButton("5", callback_data="qty_5"),
         InlineKeyboardButton("10", callback_data="qty_10")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_qty")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "Выбери количество:",
        reply_markup=reply_markup
    )
    return SELECT_QUANTITY

async def quantity_handler(update: Update, context: CallbackContext) -> int:
    """Обработка выбора количества"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_qty":
        # Возвращаемся к товару
        await show_product(update, context)
        return SELECT_PRODUCT
    
    # Получаем количество из callback_data
    quantity = int(query.data.split("_")[1])
    product_id = context.user_data.get("adding_product")
    
    if not product_id:
        return SELECT_CATEGORY
    
    # Получаем пользователя и добавляем товар в корзину
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if user:
        if product_id in user.cart:
            user.cart[product_id] += quantity
        else:
            user.cart[product_id] = quantity
        save_user_cart(user)
    
    await query.edit_message_text(
        f"✅ Товар добавлен в корзину!\nКоличество: {quantity}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🛒 В корзину", callback_data="view_cart"),
            InlineKeyboardButton("◀️ Назад к товарам", callback_data="back_to_products")
        ]])
    )
    return SELECT_PRODUCT

async def view_cart(update: Update, context: CallbackContext) -> None:
    """Просмотр корзины"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user.cart:
        keyboard = [[InlineKeyboardButton("◀️ В категории", callback_data="back_to_categories")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "🛒 Корзина пуста",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "🛒 Корзина пуста",
                reply_markup=reply_markup
            )
        return
    
    # Собираем информацию о товарах в корзине
    products_data = load_data(PRODUCTS_FILE, {})
    cart_items = []
    total = 0
    
    for product_id, quantity in user.cart.items():
        product_data = products_data.get(product_id)
        if product_data:
            product = Product.from_dict(product_data)
            item_total = product.price * quantity
            total += item_total
            cart_items.append(
                f"• {product.name}\n"
                f"  {quantity} шт × {product.price} ₽ = {item_total} ₽"
            )
    
    cart_text = "🛒 *Твоя корзина*\n\n" + "\n".join(cart_items)
    cart_text += f"\n\n💰 *Итого: {total} ₽*"
    
    keyboard = [
        [InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")],
        [InlineKeyboardButton("✏️ Редактировать корзину", callback_data="edit_cart")],
        [InlineKeyboardButton("◀️ В категории", callback_data="back_to_categories")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        cart_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def checkout(update: Update, context: CallbackContext) -> int:
    """Оформление заказа"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user.cart:
        await update.callback_query.edit_message_text("Корзина пуста")
        return SELECT_CATEGORY
    
    # Создаем заказ
    products_data = load_data(PRODUCTS_FILE, {})
    order_items = {}
    total = 0
    
    for product_id, quantity in user.cart.items():
        product_data = products_data.get(product_id)
        if product_data:
            product = Product.from_dict(product_data)
            order_items[product_id] = {
                "name": product.name,
                "quantity": quantity,
                "price": product.price
            }
            total += product.price * quantity
    
    order = Order(
        order_id=str(uuid.uuid4()),
        user_id=user_id,
        items=order_items,
        total=total,
        phone=user.phone
    )
    
    # Сохраняем заказ
    orders_data = load_data(ORDERS_FILE, {})
    orders_data[order.id] = order.to_dict()
    save_data(ORDERS_FILE, orders_data)
    
    # Очищаем корзину пользователя
    user.cart = {}
    save_user_cart(user)
    
    # Отправляем подтверждение
    order_text = (
        f"✅ *Заказ оформлен!*\n\n"
        f"Номер заказа: `{order.id}`\n"
        f"Сумма: {total} ₽\n"
        f"Телефон: {user.phone}\n\n"
        f"С вами свяжутся для подтверждения."
    )
    
    keyboard = [[InlineKeyboardButton("◀️ В категории", callback_data="back_to_categories")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        order_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"🆕 *Новый заказ!*\n\n"
                f"Номер: `{order.id}`\n"
                f"Клиент: {user.name} (@{user.username})\n"
                f"Телефон: {user.phone}\n"
                f"Сумма: {total} ₽\n\n"
                f"*Состав заказа:*\n"
            )
            for item in order_items.values():
                admin_text += f"• {item['name']} - {item['quantity']} шт × {item['price']} ₽\n"
            
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode="Markdown"
            )
        except:
            pass
    
    return SELECT_CATEGORY

# --- Админ-панель ---

async def admin_panel(update: Update, context: CallbackContext) -> int:
    """Панель администратора"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав администратора")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("📁 Управление категориями", callback_data="admin_categories")],
        [InlineKeyboardButton("📦 Управление товарами", callback_data="admin_products")],
        [InlineKeyboardButton("📊 Просмотр заказов", callback_data="admin_orders")],
        [InlineKeyboardButton("👥 Просмотр пользователей", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔧 *Панель администратора*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

async def admin_categories(update: Update, context: CallbackContext) -> int:
    """Управление категориями"""
    query = update.callback_query
    await query.answer()
    
    categories_data = load_data(CATEGORIES_FILE, {})
    
    text = "📁 *Категории*\n\n"
    if categories_data:
        for cat_id, cat_name in categories_data.items():
            text += f"• {cat_name} (ID: `{cat_id}`)\n"
    else:
        text += "Пока нет категорий\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить категорию", callback_data="add_category")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return ADMIN_CATEGORY

async def add_category_start(update: Update, context: CallbackContext) -> int:
    """Начало добавления категории"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Введите название новой категории:"
    )
    return ADMIN_CATEGORY

async def add_category_name(update: Update, context: CallbackContext) -> int:
    """Сохранение новой категории"""
    category_name = update.message.text
    category_id = str(uuid.uuid4())[:8]
    
    categories_data = load_data(CATEGORIES_FILE, {})
    categories_data[category_id] = category_name
    save_data(CATEGORIES_FILE, categories_data)
    
    await update.message.reply_text(f"✅ Категория '{category_name}' добавлена!")
    
    # Возвращаемся в админ-панель
    keyboard = [
        [InlineKeyboardButton("📁 Управление категориями", callback_data="admin_categories")],
        [InlineKeyboardButton("📦 Управление товарами", callback_data="admin_products")],
        [InlineKeyboardButton("📊 Просмотр заказов", callback_data="admin_orders")],
        [InlineKeyboardButton("👥 Просмотр пользователей", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔧 *Панель администратора*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

async def admin_products(update: Update, context: CallbackContext) -> int:
    """Управление товарами"""
    query = update.callback_query
    await query.answer()
    
    categories_data = load_data(CATEGORIES_FILE, {})
    
    if not categories_data:
        keyboard = [[InlineKeyboardButton("➕ Сначала создайте категорию", callback_data="add_category")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Нет категорий. Сначала создайте категорию.",
            reply_markup=reply_markup
        )
        return ADMIN_CATEGORY
    
    # Показываем выбор категории для добавления товара
    keyboard = []
    for cat_id, cat_name in categories_data.items():
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=f"admin_add_product_{cat_id}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите категорию для добавления товара:",
        reply_markup=reply_markup
    )
    return ADMIN_PRODUCT_NAME

async def add_product_category_selected(update: Update, context: CallbackContext) -> int:
    """Выбрана категория для товара"""
    query = update.callback_query
    await query.answer()
    
    category_id = query.data.replace("admin_add_product_", "")
    context.user_data["new_product_category"] = category_id
    
    await query.edit_message_text(
        "Введите название товара:"
    )
    return ADMIN_PRODUCT_NAME

async def add_product_name(update: Update, context: CallbackContext) -> int:
    """Получение названия товара"""
    context.user_data["new_product_name"] = update.message.text
    await update.message.reply_text("Введите цену товара (только число):")
    return ADMIN_PRODUCT_PRICE

async def add_product_price(update: Update, context: CallbackContext) -> int:
    """Получение цены товара"""
    try:
        price = float(update.message.text)
        context.user_data["new_product_price"] = price
        await update.message.reply_text(
            "Введите срок годности (например: 31.12.2024 или 'до 05.2026'):"
        )
        return ADMIN_PRODUCT_EXPIRY
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число (цену):")
        return ADMIN_PRODUCT_PRICE

async def add_product_expiry(update: Update, context: CallbackContext) -> int:
    """Получение срока годности"""
    context.user_data["new_product_expiry"] = update.message.text
    await update.message.reply_text(
        "Отправьте фото товара (или отправьте 'пропустить' без фото):"
    )
    return ADMIN_PRODUCT_PHOTO

async def add_product_photo(update: Update, context: CallbackContext) -> int:
    """Получение фото товара"""
    photo_id = None
    
    if update.message.photo:
        # Берем самое большое фото
        photo_id = update.message.photo[-1].file_id
    elif update.message.text and update.message.text.lower() == "пропустить":
        pass
    else:
        await update.message.reply_text("Отправьте фото или напишите 'пропустить'")
        return ADMIN_PRODUCT_PHOTO
    
    # Создаем товар
    product_id = str(uuid.uuid4())
    product = Product(
        product_id=product_id,
        category_id=context.user_data["new_product_category"],
        name=context.user_data["new_product_name"],
        price=context.user_data["new_product_price"],
        expiry_date=context.user_data["new_product_expiry"],
        photo_id=photo_id
    )
    
    products_data = load_data(PRODUCTS_FILE, {})
    products_data[product_id] = product.to_dict()
    save_data(PRODUCTS_FILE, products_data)
    
    await update.message.reply_text("✅ Товар успешно добавлен!")
    
    # Очищаем временные данные
    for key in ["new_product_category", "new_product_name", 
                "new_product_price", "new_product_expiry"]:
        if key in context.user_data:
            del context.user_data[key]
    
    # Возвращаемся в админ-панель
    keyboard = [
        [InlineKeyboardButton("📁 Управление категориями", callback_data="admin_categories")],
        [InlineKeyboardButton("📦 Управление товарами", callback_data="admin_products")],
        [InlineKeyboardButton("📊 Просмотр заказов", callback_data="admin_orders")],
        [InlineKeyboardButton("👥 Просмотр пользователей", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔧 *Панель администратора*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

async def admin_orders(update: Update, context: CallbackContext) -> int:
    """Просмотр заказов"""
    query = update.callback_query
    await query.answer()
    
    orders_data = load_data(ORDERS_FILE, {})
    users_data = load_data(USERS_FILE, {})
    
    if not orders_data:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Нет заказов",
            reply_markup=reply_markup
        )
        return ADMIN_MENU
    
    # Показываем последние 5 заказов
    text = "📊 *Последние заказы*\n\n"
    sorted_orders = sorted(
        orders_data.values(),
        key=lambda x: x.get("created_at", ""),
        reverse=True
    )[:5]
    
    for order_data in sorted_orders:
        order = Order.from_dict(order_data)
        user_data = users_data.get(str(order.user_id), {})
        phone = user_data.get("phone", order.phone)
        
        text += (
            f"🆔 `{order.id[:8]}...`\n"
            f"📞 {phone}\n"
            f"💰 {order.total} ₽\n"
            f"📅 {order.created_at[:10]}\n"
            f"Статус: {order.status}\n"
            f"---\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

async def admin_users(update: Update, context: CallbackContext) -> int:
    """Просмотр пользователей"""
    query = update.callback_query
    await query.answer()
    
    users_data = load_data(USERS_FILE, {})
    
    if not users_data:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Нет зарегистрированных пользователей",
            reply_markup=reply_markup
        )
        return ADMIN_MENU
    
    text = "👥 *Пользователи*\n\n"
    for user_id, user_data in list(users_data.items())[:10]:  # Показываем первых 10
        text += (
            f"🆔 {user_id}\n"
            f"📞 {user_data.get('phone', 'Нет')}\n"
            f"👤 {user_data.get('name', '')}\n"
            f"📅 {user_data.get('registered_at', '')[:10]}\n"
            f"---\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

# --- Обработчики навигации ---

async def handle_callback(update: Update, context: CallbackContext) -> int:
    """Обработка всех callback-запросов"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "back_to_categories":
        await show_main_menu(update, context)
        return SELECT_CATEGORY
    
    elif data == "back_to_products":
        # Возврат к списку товаров в категории
        if "current_category" in context.user_data:
            await show_category_products(update, context, context.user_data["current_category"])
        return SELECT_PRODUCT
    
    elif data == "view_cart":
        await view_cart(update, context)
        return SELECT_CATEGORY
    
    elif data == "edit_cart":
        # TODO: Редактирование корзины
        await query.edit_message_text("Функция редактирования в разработке")
        return SELECT_CATEGORY
    
    elif data == "checkout":
        return await checkout(update, context)
    
    elif data.startswith("cat_"):
        category_id = data.replace("cat_", "")
        await show_category_products(update, context, category_id)
        return SELECT_PRODUCT
    
    elif data.startswith("add_"):
        product_id = data.replace("add_", "")
        return await add_to_cart(update, context, product_id)
    
    elif data == "next_product":
        if "current_product_index" in context.user_data:
            context.user_data["current_product_index"] += 1
            product_ids = context.user_data.get("category_products", [])
            if context.user_data["current_product_index"] >= len(product_ids):
                context.user_data["current_product_index"] = 0
            await show_product(update, context)
        return SELECT_PRODUCT
    
    elif data == "prev_product":
        if "current_product_index" in context.user_data:
            context.user_data["current_product_index"] -= 1
            if context.user_data["current_product_index"] < 0:
                product_ids = context.user_data.get("category_products", [])
                context.user_data["current_product_index"] = len(product_ids) - 1
            await show_product(update, context)
        return SELECT_PRODUCT
    
    # Админ-панель
    elif data == "admin_categories":
        return await admin_categories(update, context)
    elif data == "admin_products":
        return await admin_products(update, context)
    elif data == "admin_orders":
        return await admin_orders(update, context)
    elif data == "admin_users":
        return await admin_users(update, context)
    elif data == "add_category":
        return await add_category_start(update, context)
    elif data == "back_to_admin":
        keyboard = [
            [InlineKeyboardButton("📁 Управление категориями", callback_data="admin_categories")],
            [InlineKeyboardButton("📦 Управление товарами", callback_data="admin_products")],
            [InlineKeyboardButton("📊 Просмотр заказов", callback_data="admin_orders")],
            [InlineKeyboardButton("👥 Просмотр пользователей", callback_data="admin_users")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🔧 *Панель администратора*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return ADMIN_MENU
    elif data.startswith("admin_add_product_"):
        return await add_product_category_selected(update, context)
    
    return SELECT_CATEGORY

async def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена действия"""
    await update.message.reply_text("Действие отменено")
    return ConversationHandler.END

# --- Основная функция ---
def main() -> None:
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Разговорник для регистрации и покупок
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE_NUMBER: [MessageHandler(filters.CONTACT, phone_handler)],
            SELECT_CATEGORY: [
                CallbackQueryHandler(handle_callback),
                CommandHandler("start", start)
            ],
            SELECT_PRODUCT: [
                CallbackQueryHandler(handle_callback),
                CommandHandler("start", start)
            ],
            SELECT_QUANTITY: [
                CallbackQueryHandler(quantity_handler),
                CommandHandler("start", start)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Разговорник для админ-панели
    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_panel)],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(handle_callback),
                CommandHandler("start", start)
            ],
            ADMIN_CATEGORY: [
                CallbackQueryHandler(handle_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_category_name),
                CommandHandler("start", start)
            ],
            ADMIN_PRODUCT_NAME: [
                CallbackQueryHandler(handle_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name),
                CommandHandler("start", start)
            ],
            ADMIN_PRODUCT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price),
                CommandHandler("start", start)
            ],
            ADMIN_PRODUCT_EXPIRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_expiry),
                CommandHandler("start", start)
            ],
            ADMIN_PRODUCT_PHOTO: [
                MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, add_product_photo),
                CommandHandler("start", start)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(admin_conv_handler)
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()




