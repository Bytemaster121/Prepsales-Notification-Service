# Flask app for a robust notification system with retry logic, email/SMS delivery,
# RabbitMQ integration, MongoDB persistence, and retry scheduling.

from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import uuid
from enum import Enum
from pymongo import MongoClient
from bson import json_util
import json
from flask_mail import Mail, Message
from twilio.rest import Client
import os
from dotenv import load_dotenv
import re
import logging
import pika
import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler

# Logging config
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment vars
load_dotenv()

# Flask app init
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# MongoDB config
mongo_client = MongoClient(os.getenv("MONGO_URL"))
db = mongo_client['flaskdb']
notifications_collection = db['notifications']
notifications_collection.create_index('user_id')
notifications_collection.create_index('status')
notifications_collection.create_index('next_retry_time')

# Email config
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD")
)
mail = Mail(app)

# Twilio config
twilio_client = Client(os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# RabbitMQ config
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
QUEUE_NAME = "notifications"
DLQ_NAME = "notifications_dlq"
MAX_RETRIES = 5

# Enum for notification types
class NotificationType(Enum):
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"

# Notification model
class Notification:
    def __init__(self, user_id, notification_type, message, email="", phone=""):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.notification_type = notification_type
        self.message = message
        self.email = email
        self.phone = phone
        self.created_at = datetime.utcnow()
        self.status = "pending"
        self.last_error = None
        self.retry_count = 0
        self.max_retries = MAX_RETRIES
        self.next_retry_time = None

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, data):
        n = cls(data['user_id'], data['notification_type'], data['message'], data.get('email', ''), data.get('phone', ''))
        n.id = data['id']
        n.created_at = data['created_at']
        n.status = data['status']
        n.last_error = data.get('last_error')
        n.retry_count = data.get('retry_count', 0)
        n.max_retries = data.get('max_retries', MAX_RETRIES)
        n.next_retry_time = data.get('next_retry_time')
        return n

# Validators
def validate_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) if email else False

def validate_phone(phone):
    return re.match(r'^\+\d{10,15}$', phone) if phone else False

def calculate_next_retry_time(retry_count):
    return datetime.utcnow() + timedelta(seconds=min(30 * (2 ** retry_count), 3600))

def publish_notification(notification):
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.queue_declare(queue=DLQ_NAME, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME,
            body=json.dumps(notification.to_dict(), default=str),
            properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
        )
        connection.close()
        return True
    except Exception as e:
        logger.error(f"Failed to publish notification: {e}")
        return False

def send_notification(notification):
    try:
        if notification.notification_type == NotificationType.EMAIL.value:
            if not validate_email(notification.email): raise ValueError("Invalid email")
            msg = Message('Notification', sender=app.config['MAIL_USERNAME'], recipients=[notification.email])
            msg.body = notification.message
            mail.send(msg)
        elif notification.notification_type == NotificationType.SMS.value:
            if not validate_phone(notification.phone): raise ValueError("Invalid phone")
            twilio_client.messages.create(
                body=notification.message,
                from_=TWILIO_PHONE_NUMBER,
                to=notification.phone
            )
        notification.status = "sent"
        return True
    except Exception as e:
        notification.status = "failed"
        notification.last_error = str(e)
        return False

def process_notification(notification_data):
    try:
        notification = Notification.from_dict(json.loads(notification_data))
        if send_notification(notification):
            notifications_collection.update_one({"id": notification.id}, {"$set": {"status": "sent", "last_error": None}})
        else:
            notification.retry_count += 1
            if notification.retry_count >= notification.max_retries:
                notification.status = "failed_permanently"
                notifications_collection.update_one({"id": notification.id}, {"$set": notification.to_dict()})
                connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
                channel = connection.channel()
                channel.basic_publish(
                    exchange='', routing_key=DLQ_NAME,
                    body=json.dumps(notification.to_dict(), default=str),
                    properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
                )
                connection.close()
            else:
                notification.next_retry_time = calculate_next_retry_time(notification.retry_count)
                notifications_collection.update_one({"id": notification.id}, {"$set": notification.to_dict()})
        return True
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return False

def start_consumer():
    def callback(ch, method, props, body):
        logger.info("Received notification")
        if process_notification(body):
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    threading.Thread(target=lambda: pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL)).channel().basic_consume(queue=QUEUE_NAME, on_message_callback=callback, auto_ack=False)).start()

def process_scheduled_retries():
    for doc in notifications_collection.find({"status": "retry_scheduled", "next_retry_time": {"$lte": datetime.utcnow()}}):
        notification = Notification.from_dict(doc)
        notifications_collection.update_one({"id": notification.id}, {"$set": {"status": "retrying"}})
        publish_notification(notification)

# Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(process_scheduled_retries, 'interval', seconds=60)
scheduler.start()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/send-notification', methods=['GET', 'POST'])
def send_notification_form():
    message = None
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        notif_type = request.form.get('type')
        notif_msg = request.form.get('message')
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        if not all([user_id, notif_type, notif_msg]):
            message = "Missing required fields"
        elif notif_type not in [nt.value for nt in NotificationType]:
            message = "Invalid type"
        else:
            n = Notification(user_id, notif_type, notif_msg, email, phone)
            notifications_collection.insert_one(n.to_dict())
            if publish_notification(n):
                message = "Notification queued"
            else:
                message = "Failed to queue"
    return render_template('send_notification.html', message=message)

@app.route('/notifications', methods=['POST'])
def send_notification_api():
    data = request.json
    required = ["user_id", "notification_type", "message"]
    if not all(k in data for k in required):
        return jsonify({"error": "Missing required fields"}), 400
    if data['notification_type'] not in [nt.value for nt in NotificationType]:
        return jsonify({"error": "Invalid notification type"}), 400
    n = Notification(data['user_id'], data['notification_type'], data['message'], data.get('email', ''), data.get('phone', ''))
    notifications_collection.insert_one(n.to_dict())
    if publish_notification(n):
        return jsonify({"message": "Notification queued", "id": n.id}), 201
    return jsonify({"error": "Queueing failed"}), 500

@app.route('/users/<user_id>/notifications', methods=['GET'])
def get_user_notifications(user_id):
    notif_type = request.args.get('type')
    query = {"user_id": user_id}
    if notif_type:
        if notif_type not in [nt.value for nt in NotificationType]:
            return jsonify({"error": "Invalid type"}), 400
        query["notification_type"] = notif_type
    notifications = list(notifications_collection.find(query))
    return jsonify({"notifications": json.loads(json_util.dumps(notifications))})

@app.route('/notifications/<notification_id>/retry', methods=['POST'])
def retry_notification(notification_id):
    doc = notifications_collection.find_one({"id": notification_id})
    if not doc:
        return jsonify({"error": "Not found"}), 404
    n = Notification.from_dict(doc)
    n.retry_count = 0
    n.status = "retrying"
    n.next_retry_time = None
    notifications_collection.update_one({"id": notification_id}, {"$set": n.to_dict()})
    if publish_notification(n):
        return jsonify({"message": "Retry queued"})
    return jsonify({"error": "Retry failed"}), 500

if __name__ == '__main__':
    threading.Thread(target=start_consumer).start()
    app.run(debug=True, port=5000)
