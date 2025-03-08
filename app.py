import telebot
from telebot import types
from flask import Flask, request
import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
import re
import time
import threading
from pymongo import MongoClient
from bson import ObjectId

# إعدادات MongoDB
MONGO_URI = "mongodb+srv://azal12345zz:KhKZxYFldC2Uz5BC@cluster0.fruat.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["Vbot"]
admins_coll = db["admins"]
users_coll = db["users"]
merchants_coll = db["merchants"]  # قائمة التجار الجدد
accounts_for_sale_coll = db["accounts_for_sale"]
purchase_requests_coll = db["purchase_requests"]
subscribers_coll = db["subscribers"]

# إعدادات البوت
TOKEN = "7615349663:AAG9KHPexx9IVs48ayCEJ0st7vgBmEqZxpY"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# إعدادات البريد الإلكتروني
EMAIL = "azal12345zz@gmail.com"
PASSWORD = "noph rexm qifb kvog"
IMAP_SERVER = "imap.gmail.com"

user_accounts = {}  # لتخزين الحساب المحدد لكل مستخدم مؤقتًا

mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL, PASSWORD)

# -------- دوال مساعدة ---------

def clean_text(text):
    return text.strip()

def retry_imap_connection():
    global mail
    for attempt in range(3):
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER)
            mail.login(EMAIL, PASSWORD)
            print("✅ اتصال IMAP ناجح.")
            return
        except Exception as e:
            print(f"❌ فشل الاتصال (المحاولة {attempt + 1}): {e}")
            time.sleep(2)
    print("❌ فشل إعادة الاتصال بعد عدة محاولات.")

def retry_on_error(func):
    def wrapper(*args, **kwargs):
        retries = 3
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if "EOF occurred" in str(e) or "socket" in str(e):
                    time.sleep(2)
                    print(f"Retrying... Attempt {attempt + 1}/{retries}")
                else:
                    return f"Error fetching emails: {e}"
        return "Error: Failed after multiple retries."
    return wrapper

@retry_on_error
def fetch_email_with_link(account, subject_keywords, button_text):
    retry_imap_connection()
    mail.select("inbox")
    _, data = mail.search(None, 'ALL')
    mail_ids = data[0].split()[-35:]
    for mail_id in reversed(mail_ids):
        _, msg_data = mail.fetch(mail_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject, encoding = decode_header(msg["Subject"])[0]
        subject = subject.decode(encoding if encoding else "utf-8") if isinstance(subject, bytes) else subject

        if any(keyword in subject for keyword in subject_keywords):
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    if account in html_content:
                        soup = BeautifulSoup(html_content, 'html.parser')
                        for a in soup.find_all('a', href=True):
                            if button_text in a.get_text():
                                return a['href']
    return "❌ طلبك غير موجود."

@retry_on_error
def fetch_email_with_code(account, subject_keywords):
    retry_imap_connection()
    mail.select("inbox")
    _, data = mail.search(None, 'ALL')
    mail_ids = data[0].split()[-35:]
    for mail_id in reversed(mail_ids):
        _, msg_data = mail.fetch(mail_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject, encoding = decode_header(msg["Subject"])[0]
        subject = subject.decode(encoding if encoding else "utf-8") if isinstance(subject, bytes) else subject

        if any(keyword in subject for keyword in subject_keywords):
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    if account in html_content:
                        code_match = re.search(r'\b\d{4}\b', BeautifulSoup(html_content, 'html.parser').get_text())
                        if code_match:
                            return code_match.group(0)
    return "❌ طلبك غير موجود."

# -------- وظائف MongoDB ---------

def init_db():
    admins_coll.create_index("username", unique=True)
    users_coll.create_index("username", unique=True)
    merchants_coll.create_index("username", unique=True)
    accounts_for_sale_coll.create_index("account", unique=True)
    subscribers_coll.create_index("chat_id", unique=True)

def add_admin(username):
    try:
        admins_coll.insert_one({"username": username})
    except:
        pass

def is_admin(username):
    return admins_coll.find_one({"username": username}) is not None

def add_merchant(username):
    try:
        merchants_coll.insert_one({"username": username})
    except:
        pass

def is_merchant(username):
    return merchants_coll.find_one({"username": username}) is not None

def create_user_if_not_exists(username):
    if not users_coll.find_one({"username": username}):
        users_coll.insert_one({
            "username": username,
            "accounts": []
        })

def add_allowed_account(username, account):
    create_user_if_not_exists(username)
    users_coll.update_one(
        {"username": username},
        {"$addToSet": {"accounts": account}}  # استخدام addToSet لتجنب التكرار
    )

def get_allowed_accounts(username):
    user = users_coll.find_one({"username": username})
    return user.get("accounts", []) if user else []

def remove_allowed_accounts(username, accounts=None):
    user = users_coll.find_one({"username": username})
    if not user:
        return
    
    if accounts:
        users_coll.update_one(
            {"username": username},
            {"$pull": {"accounts": {"$in": accounts}}}
        )
    else:
        users_coll.update_one(
            {"username": username},
            {"$set": {"accounts": []}}
        )

def add_accounts_for_sale(accounts):
    docs = [{"account": acc} for acc in accounts]
    accounts_for_sale_coll.insert_many(docs)

def get_accounts_for_sale():
    return [doc["account"] for doc in accounts_for_sale_coll.find()]

def remove_accounts_from_sale(accounts):
    for acc in accounts:
        accounts_for_sale_coll.delete_one({"account": acc})

def add_purchase_request(username, count):
    purchase_requests_coll.insert_one({
        "username": username,
        "count": count,
        "status": "pending",
        "timestamp": time.time()
    })

def get_pending_requests():
    return list(purchase_requests_coll.find({"status": "pending"}))

def approve_request(req_id):
    purchase_requests_coll.update_one(
        {"_id": ObjectId(req_id)},
        {"$set": {"status": "approved"}}
    )

def reject_request(req_id):
    purchase_requests_coll.update_one(
        {"_id": ObjectId(req_id)},
        {"$set": {"status": "rejected"}}
    )

def get_request_by_id(req_id):
    return purchase_requests_coll.find_one({"_id": ObjectId(req_id)})

# -------- واجهة البوت ---------

@bot.message_handler(commands=['start'])
def start_message(message):
    username = clean_text(message.from_user.username)
    create_user_if_not_exists(username)
    
    user_type = "admin" if is_admin(username) else "merchant" if is_merchant(username) else "customer"
    
    if user_type == "admin":
        bot.send_message(message.chat.id, "مرحباً أيها الأدمن! اختر العملية:", reply_markup=admin_keyboard())
    elif user_type == "merchant":
        bot.send_message(message.chat.id, "مرحباً أيها التاجر! اختر العملية:", reply_markup=merchant_keyboard())
    else:
        bot.send_message(message.chat.id, "مرحباً! اختر العملية:", reply_markup=customer_keyboard())

# أزرار لوحة التحكم
def admin_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2)
    buttons = [
        "إضافة تاجر",
        "حذف تاجر",
        "إرسال رسالة جماعية",
        "عرض عدد المستخدمين"
    ]
    return keyboard.add(*[types.KeyboardButton(b) for b in buttons])

def merchant_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2)
    buttons = [
        "إضافة مستخدم",
        "حذف مستخدم",
        "عرض حسابات المستخدم",
        "إضافة حسابات",
        "حذف حسابات",
        "طلب رمز السكن"
    ]
    return keyboard.add(*[types.KeyboardButton(b) for b in buttons])

def customer_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=1)
    buttons = [
        "عرض الحسابات",
     
        "طلب تحديث السكن",
   
    ]
    return keyboard.add(*[types.KeyboardButton(b) for b in buttons])

# -------- وظائف الأدمن ---------

@bot.message_handler(func=lambda msg: msg.text == "إضافة تاجر")
def add_merchant_handler(msg):
    if not is_admin(clean_text(msg.from_user.username)):
        return bot.send_message(msg.chat.id, "❌ ليس لديك صلاحيات الأدمن.")
    bot.send_message(msg.chat.id, "أرسل اسم التاجر:")
    bot.register_next_step_handler(msg, process_add_merchant)

def process_add_merchant(msg):
    merchant_name = clean_text(msg.text)
    add_merchant(merchant_name)
    bot.send_message(msg.chat.id, f"✅ تم إضافة التاجر {merchant_name} بنجاح.")

@bot.message_handler(func=lambda msg: msg.text == "حذف تاجر")
def remove_merchant_handler(msg):
    if not is_admin(clean_text(msg.from_user.username)):
        return bot.send_message(msg.chat.id, "❌ ليس لديك صلاحيات الأدمن.")
    bot.send_message(msg.chat.id, "أرسل اسم التاجر:")
    bot.register_next_step_handler(msg, process_remove_merchant)

def process_remove_merchant(msg):
    merchant_name = clean_text(msg.text)
    merchants_coll.delete_one({"username": merchant_name})
    bot.send_message(msg.chat.id, f"✅ تم حذف التاجر {merchant_name} بنجاح.")

# -------- وظائف التاجر ---------

@bot.message_handler(func=lambda msg: msg.text == "إضافة مستخدم")
def add_user_handler(msg):
    if not is_merchant(clean_text(msg.from_user.username)):
        return bot.send_message(msg.chat.id, "❌ ليس لديك صلاحيات التاجر.")
    bot.send_message(msg.chat.id, "أرسل اسم المستخدم:")
    bot.register_next_step_handler(msg, process_add_user)

def process_add_user(msg):
    username = clean_text(msg.text)
    create_user_if_not_exists(username)
    # ربط المستخدم بالتاجر في قاعدة البيانات
    users_coll.update_one(
        {"username": username},
        {"$set": {"merchant": msg.from_user.username}}
    )
    bot.send_message(msg.chat.id, f"✅ تم إضافة المستخدم {username} بنجاح.")

# -------- وظائف المستخدم العادي ---------

@bot.message_handler(func=lambda msg: msg.text == "طلب رمز السكن")
def request_access_code(msg):
    username = clean_text(msg.from_user.username)
    accounts = get_allowed_accounts(username)
    if not accounts:
        return bot.send_message(msg.chat.id, "❌ ليس لديك حسابات مُرتبطة.")
    
    bot.send_message(msg.chat.id, "اختر الحساب:")
    keyboard = types.ReplyKeyboardMarkup(row_width=1)
    keyboard.add(*[types.KeyboardButton(acc) for acc in accounts])
    bot.register_next_step_handler(msg, process_access_code, accounts)

def process_access_code(msg, accounts):
    selected_account = msg.text
    if selected_account not in accounts:
        return bot.send_message(msg.chat.id, "❌ الحساب غير صحيح.")
    
    code = fetch_email_with_code(selected_account, ["رمز الوصول المؤقت"])
    bot.send_message(msg.chat.id, f"رمز السكن: {code}")

# -------- وظائف أخرى (مثل إضافة حسابات للبيع، إرسال الرسائل الجماعية، إلخ) --------
# يمكنك إضافة باقي الوظائف بنفس الطريقة بناءً على الكود الأصلي مع التعديلات

# -------- تشغيل البوت --------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)