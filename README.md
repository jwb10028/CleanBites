![Alt text](./CleanBites/staticfiles/images/logo.png)

# NYC Restaurant Health Insights

A full-stack web application built with Django and Bootstrap that helps users discover local NYC restaurants and view detailed health inspection ratings, reviews, and other relevant data. Designed for real-time community interaction, the platform integrates map-based search, instant messaging, and moderation tools.

## 🌐 Live Features

- 🔍 **Health Rating Search**: Explore local NYC restaurants with up-to-date DOH inspection grades and violations.
- 🗺️ **Geo-Search Interface**: Built with PostGIS and GDAL, enabling spatial queries and map visualizations.
- 💬 **Instant Messaging**: Real-time chat between users using Django Channels and WebSockets (Daphne).
- 👥 **Social Features**: Follow restaurants, comment on profiles, receive notifications.
- 🔐 **Admin & Moderation Tools**: Full control panel for managing flagged content, user permissions, and audit logs.
- 📊 **Advanced Filtering**: Query by cuisine type, borough, or health grade.
- 🧪 **Unit & Integration Tests**: Comprehensive test suite ensures backend and frontend reliability.

## 🛠️ Tech Stack

**Backend**
- Django (async-enabled)
- Django Channels (WebSocket support via Daphne)
- PostgreSQL + PostGIS (geospatial querying)
- GDAL/GEOS (GeoDjango support)
- SSL/TLS (Let's Encrypt certificates)
- Hosted via AWS Elastic Beanstalk (with EB CLI & containerized deployments)

**Frontend**
- Bootstrap 5 / HTML / CSS / JavaScript
- Custom modals and responsive UI
- AJAX & Fetch for dynamic content loading

**DevOps & Deployment**
- AWS Elastic Beanstalk (staging + production environments)
- Daphne ASGI server
- HTTPS enabled via ACM/Let’s Encrypt
- Static & media file management with `whitenoise` and S3-ready configuration

## 🚀 Local Development

```bash
git clone https://github.com/yourusername/nyc-restaurant-health.git
cd nyc-restaurant-health
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Ensure you have PostgreSQL and PostGIS installed locally. Set up `.env` for sensitive config values.

## 🧪 Running Tests

```bash
python manage.py test
```

Includes unit and integration tests for views, models, websocket messaging, and moderation logic.

## 🔒 Security Features

- HTTPS enforced across all routes
- CSRF & XSS protections enabled
- Admin panel with user role differentiation (admin, moderator, user)
- Rate-limiting and validation on form inputs

## 🧭 Future Improvements

- Docker-based deployment
- Real-time health inspection updates via external APIs
- Mobile-first UI overhaul with better accessibility support

---

Built with care as part of a semester-long full-stack project to bring transparency and community to NYC’s dining scene.
