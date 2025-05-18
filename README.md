# Notification Service

A robust Flask-based Notification Service that sends email, SMS, and in-app notifications to users, leveraging RabbitMQ for asynchronous queuing and retry mechanisms for failed deliveries. The service provides a RESTful API and a user-friendly web interface, with persistent storage in MongoDB.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3.3-green)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-yellow)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.8%2B-orange)
![Twilio](https://img.shields.io/badge/Twilio-SMS-red)
![License](https://img.shields.io/badge/License-MIT-blue)

## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Setup Instructions](#setup-instructions)
- [Dependencies](#dependencies)
- [Web Interface](#web-interface)
- [Challenges Faced](#challenges-faced)
- [Future Improvements](#future-improvements)


## Features
- **Notification Types**: Supports email (via Gmail SMTP), SMS (via Twilio), and in-app notifications (stored in MongoDB).
- **Asynchronous Queuing**: Uses RabbitMQ to queue notifications for reliable, scalable processing.
- **Retry Mechanism**: Automatically retries failed notifications up to 5 times with exponential backoff (30s, 2m, 10m, 30m, 1h).
- **Manual Retry**: Allows manual retry of failed notifications via API.
- **RESTful API**: Provides endpoints to send notifications, retrieve user notifications, and view statistics.
- **Web Interface**: User-friendly form to send notifications and view status.
- **Persistent Storage**: Stores notification data in MongoDB with indexes for performance.
- **Monitoring**: Offers a `/stats` endpoint to track notification statuses (sent, failed, pending, etc.).
- **Robust Error Handling**: Includes environment variable validation and detailed logging.

## Architecture
The Notification Service follows a modular, event-driven architecture:
- **Flask**: Handles HTTP requests and serves the API and web interface.
- **MongoDB**: Stores notification records with indexes on `user_id`, `status`, and `next_retry_time`.
- **RabbitMQ**: Queues notifications in a durable `notifications` queue, with a `notifications_dlq` for permanently failed messages.
- **Twilio**: Sends SMS notifications.
- **Gmail SMTP**: Sends email notifications via Flask-Mail.
- **APScheduler**: Schedules retries for failed notifications.
- **Pika**: Manages RabbitMQ connections for producing and consuming messages.

### Approach
1. **Notification Creation**:
   - Notifications are created with a unique ID, user ID, type (email, SMS, in-app), message, and optional email/phone.
   - Stored in MongoDB with initial status `pending`.
2. **Queuing**:
   - Notifications are published to RabbitMQ’s `notifications` queue using `pika`.
   - Durable queues ensure messages persist across server restarts.
3. **Processing**:
   - A background consumer thread processes messages from the queue.
   - Email notifications use Flask-Mail, SMS uses Twilio, and in-app notifications are marked `sent` in MongoDB.
4. **Retries**:
   - Failed notifications increment `retry_count` and schedule a retry with exponential backoff.
   - After 5 retries, notifications move to `failed_permanently` and are published to `notifications_dlq`.
   - A scheduler checks MongoDB every 30 seconds for retry-eligible notifications.
5. **API and Web Interface**:
   - RESTful endpoints handle notification creation, retrieval, retries, and stats.
   - A web form allows manual notification sending with real-time feedback.

## File Structure
prepsales/
├── notification_service.py      # Main Flask application
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
├── templates/
│   ├── index.html              # Home page
│   └── send_notification.html  # Notification form
└── venv/                       # Virtual environment


## Setup Instructions
### Prerequisites
- Python 3.8+
- MongoDB Atlas account ([cloud.mongodb.com](https://cloud.mongodb.com))
- RabbitMQ server ([rabbitmq.com](https://www.rabbitmq.com/install-windows.html))
- Erlang ([erlang.org](https://www.erlang.org/downloads))
- Twilio account ([twilio.com](https://www.twilio.com))
- Gmail account with App Password

### Installation
1. **Clone the Repository**:
   git clone https://github.com/Bytemaster121/Prepsales-Notification-Service
   cd notification-service
   
2. **Create and Activate Virtual Environment**
python -m venv venv

.\venv\Scripts\Activate  # Windows

source venv/bin/activate  # Linux/Mac

3.**Install Dependencies**:

pip install -r requirements.txt

4:**Set Up RabbitMQ**:
Install RabbitMQ and Erlang.
Start the server:
rabbitmq-server
Enable management plugin:

rabbitmq-plugins enable rabbitmq_management
Access UI at http://localhost:15672 (username: guest, password: guest).

5:**Run the Application**:

python notification_service.py
Access API at http://localhost:5000 or http://192.168.29.238:5000.
Web interface at http://localhost:5000.
## Sample .env
Flask application secret key

SECRET_KEY=5f3523797c241b77a8a0b8c1a6b5851f4b1d5f33d81a8e4b

FLASK_DEBUG=true

MongoDB configuration

MONGO_URI=mongodb+srv://<username>:<password>@cluster0.jhdxcyy.mongodb.net/flaskdb?retryWrites=true&w=majority&appName=Cluster0

Email configuration (Gmail SMTP)

MAIL_USERNAME=your.email@gmail.com

MAIL_PASSWORD=your_app_password

Twilio configuration (SMS)
TWILIO_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

TWILIO_PHONE_NUMBER=+1234567890

RabbitMQ configuration

RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F

# Sample requirements.txt
flask==2.3.3

pymongo==4.8.0

flask-mail==0.10.0

python-dotenv==1.0.1

twilio==9.3.0

pika==1.3.2

apscheduler==3.10.4

## Dependencies
flask (2.3.3): Web framework for API and web interface.

pymongo (4.8.0): MongoDB driver for notification storage.

flask-mail (0.10.0): Email sending via Gmail SMTP.

python-dotenv (1.0.1): Loads environment variables from .env.

twilio (9.3.0): SMS sending via Twilio API.

pika (1.3.2): RabbitMQ client for queuing.

apscheduler (3.10.4): Schedules retry tasks.


## Web Interface
Home (/): Displays a welcome message and link to send notifications.
Send Notification (/send-notification): Form to input user ID, notification type, message, email, and phone. Shows success/error messages.

## Challenges Faced


1:RabbitMQ Setup:

Issue: Local RabbitMQ server not running or misconfigured.

Solution: Provided detailed setup instructions and fallback URL in code.

2:Retry Logic Complexity:

Issue: Ensuring reliable retries without message loss.

Solution: Used APScheduler and RabbitMQ’s durable queues with a dead letter queue.


## Future Improvements

1:Authentication: Add JWT or OAuth2 for secure API access.

2:Notification Templates: Support customizable templates for emails and SMS.

3:Distributed Queuing: Use Kafka for higher throughput in production.

4:Dockerization: Containerize the app for easier deployment.
