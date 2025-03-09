import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
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
merchants = db["merchants"]
users = db["users"]
accounts_for_sale = db["accounts_for_sale"]
purchase_requests = db["purchase_requests"]

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
        "عرض الحسابات للبيع 📦",
        "إرسال رسالة جماعية 📢"
    ]
    return markup.add(*buttons)

def merchant_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        "إضافة مستخدم ➕",
        "حذف مستخدم ❌",
        "إضافة حسابات 📥",
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
    merchants.insert_one({"username": merchant_name})
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

# --- وظائف التاجر ---
@bot.message_handler(func=lambda msg: msg.text == "إضافة مستخدم ➕" and is_merchant(msg.from_user.username))
def add_user(msg):
    bot.send_message(msg.chat.id, "أرسل اسم المستخدم:")
    bot.register_next_step_handler(msg, process_add_user)

def process_add_user(msg):
    user_name = clean_text(msg.text)
    users.insert_one({
        "username": user_name,
        "merchant": msg.from_user.username,
        "accounts": []
    })
    bot.send_message(msg.chat.id, f"✅ تم إضافة المستخدم {user_name}")

@bot.message_handler(func=lambda msg: msg.text == "إضافة حسابات 📥" and is_merchant(msg.from_user.username))
def add_accounts(msg):
    bot.send_message(msg.chat.id, "أرسل الحسابات (كل حساب في سطر):")
    bot.register_next_step_handler(msg, process_add_accounts)

def process_add_accounts(msg):
    accounts = msg.text.split("\n")
    users.update_many(
        {"merchant": msg.from_user.username},
        {"$addToSet": {"accounts": {"$each": accounts}}}
    )
    bot.send_message(msg.chat.id, "✅ تم إضافة الحسابات")

# --- وظائف المستخدم ---
@bot.message_handler(func=lambda msg: msg.text == "طلب رمز السكن 🔑")
def request_code(msg):
    username = msg.from_user.username
    user_doc = users.find_one({"username": username})
    if not user_doc or not user_doc["accounts"]:
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

# --- وظائف الأدمن الأخرى ---
@bot.message_handler(func=lambda msg: msg.text == "إرسال رسالة جماعية 📢" and is_admin(msg.from_user.username))
def send_broadcast(msg):
    bot.send_message(msg.chat.id, "اكتب نص الرسالة:")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(msg):
    text = msg.text
    for user in users.find():
        bot.send_message(user["username"], f"📢 {text}")
    bot.send_message(msg.chat.id, "✅ تم الإرسال لجميع المستخدمين")

# --- وظائف البدء ---
@bot.message_handler(commands=['start'])
def start_message(message):
    username = message.from_user.username
    if is_admin(username):
        bot.send_message(message.chat.id, "مرحباً الأدمن!", reply_markup=admin_keyboard())
    elif is_merchant(username):
        bot.send_message(message.chat.id, "مرحباً التاجر!", reply_markup=merchant_keyboard())
    else:
        bot.send_message(message.chat.id, "مرحباً المستخدم!", reply_markup=user_keyboard())

@app.route('/webhook', methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    print("DEBUG: Received an update from Telegram Webhook:", json_string)
    return '', 200

# --- تشغيل البوت ---
if __name__ == "__main__":
    bot.polling(none_stop=True)
