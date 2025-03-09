import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
from flask import Flask, request
import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
import re
import time

# --- إعدادات MongoDB ---
MONGO_URI = "mongodb+srv://azal12345zz:KhKZxYFldC2Uz5BC@cluster0.fruat.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["Vbot"]
admins = db["admins"]
merchants = db["merchants"]  # تجار مع حساباتهم الخاصة
users = db["users"]          # مستخدمي التجار مع الحسابات المرتبطة

app = Flask(__name__)

# --- إعدادات البوت ---
TOKEN = "7615349663:AAG9KHPexx9IVs48ayCEJ0st7vgBmEqZxpY"
bot = telebot.TeleBot(TOKEN)

# --- إعدادات البريد الإلكتروني ---
EMAIL = "azal12345zz@gmail.com"
PASSWORD = "noph rexm qifb kvog"
IMAP_SERVER = "imap.gmail.com"
mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL, PASSWORD)

# --- دوال مساعدة ---
def clean_text(text):
    return text.strip()

def retry_imap_connection():
    global mail
    for attempt in range(3):
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER)
            mail.login(EMAIL, PASSWORD)
            return
        except Exception as e:
            time.sleep(2)
    print("❌ فشل الاتصال بالبريد")

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

def init_db():
    admins.create_index("username", unique=True)
    merchants.create_index("username", unique=True)
    users.create_index("username", unique=True)

# --- التحقق من الصلاحيات ---
def is_admin(username):
    return admins.find_one({"username": username}) is not None

def is_merchant(username):
    return merchants.find_one({"username": username}) is not None

# --- لوحة التحكم ---
def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        "إضافة تاجر ➕",
        "حذف تاجر ❌",
        "إضافة حسابات لتاجر 📥",
        "حذف حسابات من تاجر 🗑",
        "إرسال رسالة جماعية 📢"
    ]
    return markup.add(*buttons)

def merchant_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        "إضافة مستخدم ➕",
        "حذف مستخدم ❌",
        "إضافة حسابات للمستخدم 📥",
        "حذف حسابات من المستخدم 🗑",
        "طلب رمز السكن 🔑"
    ]
    return markup.add(*buttons)

def user_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    buttons = ["طلب رمز السكن 🔑"]
    return markup.add(*buttons)

# --- وظائف الأدمن ---
@bot.message_handler(func=lambda msg: msg.text == "إضافة تاجر ➕" and is_admin(msg.from_user.username))
def add_merchant(msg):
    bot.send_message(msg.chat.id, "أرسل اسم التاجر:")
    bot.register_next_step_handler(msg, process_add_merchant)

def process_add_merchant(msg):
    merchant_name = clean_text(msg.text)
    merchants.insert_one({
        "username": merchant_name,
        "accounts": []
    })
    bot.send_message(msg.chat.id, f"✅ تم إضافة التاجر {merchant_name}")

@bot.message_handler(func=lambda msg: msg.text == "حذف تاجر ❌" and is_admin(msg.from_user.username))
def remove_merchant(msg):
    bot.send_message(msg.chat.id, "أرسل اسم التاجر:")
    bot.register_next_step_handler(msg, process_remove_merchant)

def process_remove_merchant(msg):
    merchant_name = clean_text(msg.text)
    merchants.delete_one({"username": merchant_name})
    users.delete_many({"merchant": merchant_name})
    bot.send_message(msg.chat.id, f"✅ تم حذف التاجر {merchant_name}")

@bot.message_handler(func=lambda msg: msg.text == "إضافة حسابات لتاجر 📥" and is_admin(msg.from_user.username))
def add_merchant_accounts(msg):
    bot.send_message(msg.chat.id, "أرسل اسم التاجر:")
    bot.register_next_step_handler(msg, process_merchant_account_step1)

def process_merchant_account_step1(msg):
    merchant_username = clean_text(msg.text)
    bot.send_message(msg.chat.id, "أرسل الحسابات (كل حساب في سطر):")
    bot.register_next_step_handler(msg, process_merchant_account_step2, merchant_username)

def process_merchant_account_step2(msg, merchant_username):
    accounts = msg.text.split("\n")
    merchants.update_one(
        {"username": merchant_username},
        {"$addToSet": {"accounts": {"$each": accounts}}}
    )
    bot.send_message(msg.chat.id, f"✅ تم إضافة الحسابات للتاجر {merchant_username}")

@bot.message_handler(func=lambda msg: msg.text == "حذف حسابات من تاجر 🗑" and is_admin(msg.from_user.username))
def remove_merchant_accounts(msg):
    bot.send_message(msg.chat.id, "أرسل اسم التاجر:")
    bot.register_next_step_handler(msg, process_remove_merchant_account_step1)

def process_remove_merchant_account_step1(msg):
    merchant_username = clean_text(msg.text)
    bot.send_message(msg.chat.id, "أرسل الحسابات التي تريد حذفها:")
    bot.register_next_step_handler(msg, process_remove_merchant_account_step2, merchant_username)

def process_remove_merchant_account_step2(msg, merchant_username):
    accounts = msg.text.split("\n")
    merchants.update_one(
        {"username": merchant_username},
        {"$pull": {"accounts": {"$in": accounts}}}
    )
    bot.send_message(msg.chat.id, f"✅ تم حذف الحسابات من التاجر {merchant_username}")

# --- وظائف التاجر ---
@bot.message_handler(func=lambda msg: msg.text == "إضافة مستخدم ➕" and is_merchant(msg.from_user.username))
def add_user(msg):
    bot.send_message(msg.chat.id, "أرسل اسم المستخدم:")
    bot.register_next_step_handler(msg, process_add_user)

def process_add_user(msg):
    user_name = clean_text(msg.text)
    merchants_username = msg.from_user.username
    users.insert_one({
        "username": user_name,
        "merchant": merchants_username,
        "accounts": []
    })
    bot.send_message(msg.chat.id, f"✅ تم إضافة المستخدم {user_name}")

@bot.message_handler(func=lambda msg: msg.text == "إضافة حسابات للمستخدم 📥" and is_merchant(msg.from_user.username))
def add_user_accounts(msg):
    bot.send_message(msg.chat.id, "أرسل اسم المستخدم:")
    bot.register_next_step_handler(msg, process_add_user_account_step1)

def process_add_user_account_step1(msg):
    user_username = clean_text(msg.text)
    bot.send_message(msg.chat.id, "أرسل الحسابات (كل حساب في سطر):")
    bot.register_next_step_handler(msg, process_add_user_account_step2, user_username)

def process_add_user_account_step2(msg, user_username):
    merchant_username = msg.from_user.username
    accounts = msg.text.split("\n")
    
    # التأكد من أن الحسابات موجودة لدى التاجر
    merchant_doc = merchants.find_one({"username": merchant_username})
    merchant_accounts = merchant_doc.get("accounts", [])
    valid_accounts = list(set(accounts) & set(merchant_accounts))
    
    if not valid_accounts:
        bot.send_message(msg.chat.id, "❌ لا توجد حسابات صالحة لدى التاجر")
        return
    
    users.update_one(
        {"username": user_username, "merchant": merchant_username},
        {"$addToSet": {"accounts": {"$each": valid_accounts}}}
    )
    merchants.update_one(
        {"username": merchant_username},
        {"$pull": {"accounts": {"$in": valid_accounts}}}
    )
    bot.send_message(msg.chat.id, f"✅ تم إضافة الحسابات للمستخدم {user_username}")

@bot.message_handler(func=lambda msg: msg.text == "حذف حسابات من المستخدم 🗑" and is_merchant(msg.from_user.username))
def remove_user_accounts(msg):
    bot.send_message(msg.chat.id, "أرسل اسم المستخدم:")
    bot.register_next_step_handler(msg, process_remove_user_account_step1)

def process_remove_user_account_step1(msg):
    user_username = clean_text(msg.text)
    bot.send_message(msg.chat.id, "أرسل الحسابات التي تريد حذفها:")
    bot.register_next_step_handler(msg, process_remove_user_account_step2, user_username)

def process_remove_user_account_step2(msg, user_username):
    merchant_username = msg.from_user.username
    accounts = msg.text.split("\n")
    
    users.update_one(
        {"username": user_username, "merchant": merchant_username},
        {"$pull": {"accounts": {"$in": accounts}}}
    )
    merchants.update_one(
        {"username": merchant_username},
        {"$addToSet": {"accounts": {"$each": accounts}}}
    )
    bot.send_message(msg.chat.id, f"✅ تم إرجاع الحسابات إلى التاجر")

@bot.message_handler(func=lambda msg: msg.text == "حذف مستخدم ❌" and is_merchant(msg.from_user.username))
def delete_user(msg):
    bot.send_message(msg.chat.id, "أرسل اسم المستخدم:")
    bot.register_next_step_handler(msg, process_delete_user)

def process_delete_user(msg):
    user_username = clean_text(msg.text)
    merchant_username = msg.from_user.username
    user_doc = users.find_one_and_delete({
        "username": user_username,
        "merchant": merchant_username
    })
    
    if user_doc:
        # إرجاع الحسابات إلى التاجر
        merchant_doc = merchants.find_one({"username": merchant_username})
        current_merchant_accounts = merchant_doc["accounts"] if merchant_doc else []
        new_merchant_accounts = current_merchant_accounts + user_doc.get("accounts", [])
        
        merchants.update_one(
            {"username": merchant_username},
            {"$set": {"accounts": new_merchant_accounts}}
        )
        bot.send_message(msg.chat.id, f"✅ تم حذف المستخدم {user_username} وتم إرجاع حساباته إلى التاجر")
    else:
        bot.send_message(msg.chat.id, "❌ المستخدم غير موجود")

# --- وظائف الأدمن: إرسال رسالة جماعية ---
@bot.message_handler(func=lambda msg: msg.text == "إرسال رسالة جماعية 📢" and is_admin(msg.from_user.username))
def send_broadcast(msg):
    bot.send_message(msg.chat.id, "اكتب نص الرسالة:")
    bot.register_next_step_handler(msg, process_send_broadcast)

def process_send_broadcast(msg):
    text = msg.text
    for user in users.find():
        bot.send_message(user["username"], f"📢 {text}")
    for merchant in merchants.find():
        bot.send_message(merchant["username"], f"📢 {text}")
    bot.send_message(msg.chat.id, "✅ تم الإرسال لجميع المستخدمين والتجار")

# --- وظائف المستخدم ---
@bot.message_handler(func=lambda msg: msg.text == "طلب رمز السكن 🔑")
def request_code(msg):
    username = msg.from_user.username
    user_doc = users.find_one({"username": username})
    if not user_doc or not user_doc.get("accounts", []):
        bot.send_message(msg.chat.id, "❌ ليس لديك حسابات مُرتبطة")
        return
    
    bot.send_message(msg.chat.id, "اختر الحساب:")
    keyboard = types.ReplyKeyboardMarkup(row_width=1)
    keyboard.add(*[types.KeyboardButton(acc) for acc in user_doc["accounts"]])
    bot.register_next_step_handler(msg, process_code_request, user_doc["accounts"])

def process_code_request(msg, accounts):
    selected_account = msg.text
    if selected_account not in accounts:
        bot.send_message(msg.chat.id, "❌ الحساب غير صحيح")
        return
    code = fetch_email_with_link(selected_account, ["رمز الوصول المؤقت"], "الحصول على الرمز")
    bot.send_message(msg.chat.id, f"رمز السكن: {code}")

# --- وظائف التاجر: عرض حساباته ---
@bot.message_handler(func=lambda msg: msg.text == "عرض حساباتي 📋" and is_merchant(msg.from_user.username))
def show_merchant_accounts(msg):
    merchant_username = msg.from_user.username
    merchant_doc = merchants.find_one({"username": merchant_username})
    accounts = merchant_doc.get("accounts", [])
    bot.send_message(msg.chat.id, f"حساباتك المتاحة: {', '.join(accounts)}")

# --- وظائف البدء ---
@bot.message_handler(commands=['start'])
def start_message(message):
    username = message.from_user.username
    if is_admin(username):
        bot.send_message(message.chat.id, "مرحباً الأدمن!", reply_markup=admin_keyboard())
    elif is_merchant(username):
        bot.send_message(message.chat.id, "مرحباً التاجر!", reply_markup=merchant_keyboard())
        show_merchant_accounts(message)
    else:
        bot.send_message(message.chat.id, "مرحباً المستخدم!", reply_markup=user_keyboard())

# --- Webhook ---
@app.route('/webhook', methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200

# --- تشغيل البوت ---
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
