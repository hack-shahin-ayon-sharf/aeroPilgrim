# aeroPilgrim

[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.0+-green?style=flat-square&logo=django)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

A modern, AI-powered flight search and booking assistant platform tailored specifically for Umrah pilgrims. AeroPilgrim leverages real-time flight data from the Sky Scrapper API combined with intelligent AI recommendations to help pilgrims plan their perfect Umrah journey.

## 🌟 Features

### Core Flight Search
- **Real-time Flight Pricing**: Integration with Sky Scrapper API for accurate, up-to-date flight data
- **Multi-city Support**: Supports departure from major Bangladeshi cities:
  - Dhaka (DAC), Chattogram (CGP), Sylhet (ZYL)
  - To Jeddah (JED) and Medina (MED)
- **Flexible Search Parameters**:
  - Customizable stay duration (7, 10, 15, 20, 30 days)
  - Search timespan from 7 days to 1 year
- **Price Calendar**: View price trends across multiple dates

### User Management
- **Secure Authentication**: User registration and login system with password hashing
- **Personalized Searches**: Users can save and track their flight searches
- **Search History**: View all previous searches with timestamps

### AI-Powered Recommendations
- **Booking Guidance**: Step-by-step guidance for booking Umrah flights
- **Hotel Finder**: AI-recommended budget hotels near the Haram
- **Itinerary Planning**: Day-by-day Umrah schedule tailored to stay duration
- **Budget Calculator**: Comprehensive cost breakdown including flights, accommodation, and transport

### User Interface
- **Glass Morphism Design**: Modern, clean interface with glassmorphic UI elements
- **Responsive Layout**: Fully responsive design for desktop and mobile devices
- **Real-time Search Results**: Instant flight results with detailed pricing information

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend Framework** | Django 3.2+ |
| **Language** | Python 3.8+ |
| **Database** | SQLite (Development) / PostgreSQL (Production) |
| **APIs** | Sky Scrapper (Flight Data), AI Service |
| **Frontend** | Django Templates, HTML5, CSS3, JavaScript |
| **Authentication** | Django Auth, Secure Password Storage |

## 📋 Project Structure

```
aeroPilgrim/
├── manage.py                      # Django management script
├── README.md                      # Project documentation
├── .gitignore                     # Git ignore rules
│
├── search/                        # Main Django project
│   ├── settings.py               # Project settings & configuration
│   ├── urls.py                   # Project URL routing
│   ├── wsgi.py                   # WSGI application
│   ├── asgi.py                   # ASGI application
│   │
│   └── core/                     # Main application
│       ├── models.py             # Database models
│       ├── views.py              # View handlers
│       ├── forms.py              # Django forms
│       ├── urls.py               # App URL routing
│       ├── admin.py              # Admin configuration
│       │
│       ├── services/             # Business logic layer
│       │   ├── flight_api.py    # Sky Scrapper API integration
│       │   └── ai_service.py    # AI recommendations engine
│       │
│       ├── migrations/           # Database migrations
│       ├── templates/            # HTML templates
│       │   └── core/
│       │       ├── home.html
│       │       ├── search.html
│       │       ├── login.html
│       │       ├── register.html
│       │       └── flight_detail.html
│       │
│       └── tests.py             # Unit tests
│
└── static/                        # Static files
    ├── css/                       # Stylesheets
    ├── js/                        # JavaScript files
    ├── fonts/                     # Custom fonts
    └── Images/                    # Images and media
```

## 🚀 Getting Started

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git

### Installation

1. **Clone the Repository**
```bash
git clone https://github.com/yourusername/aeroPilgrim.git
cd aeroPilgrim
```

2. **Create Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Dependencies**
```bash
pip install django requests
```

4. **Set Environment Variables**
Create a `.env` file in the root directory:
```env
DEBUG=True
SECRET_KEY=your-secret-key-here
API_KEY=your-sky-scrapper-api-key
API_HOST=sky-scrapper.p.rapidapi.com
AI_API_KEY=your-ai-service-api-key
```

5. **Database Setup**
```bash
cd search
python manage.py migrate
python manage.py createsuperuser
```

6. **Run Development Server**
```bash
python manage.py runserver
```

Visit `http://localhost:8000` in your browser.

## 📊 Database Models

### Search Model
Stores flight search queries and results:

```python
class Search(models.Model):
    city_departure        # Origin city (3-letter code)
    city_arrival          # Destination city (3-letter code)
    stay_days             # Duration of stay (7, 10, 15, 20, 30 days)
    timespan_to_search    # Search period (7 days to 1 year)
    api_response          # Raw API response (JSON)
    created_at            # Timestamp of search creation
```

## 🔌 API Integrations

### Sky Scrapper API
Provides real-time flight pricing data across multiple dates.

**Endpoint**: `https://sky-scrapper.p.rapidapi.com/api/v1/flights/getPriceCalendar`

**Parameters**:
- `originSkyId`: Departure airport code
- `destinationSkyId`: Arrival airport code
- `fromDate`: Start date for search (YYYY-MM-DD format)
- `currency`: Currency code (USD)

### AI Service
Provides intelligent recommendations for:
- Booking planning
- Hotel recommendations
- Itinerary creation
- Budget analysis

## 👥 User Authentication

- **Registration**: Email-based registration with password validation
- **Login**: Secure session-based authentication
- **Authorization**: Role-based access control via Django permissions
- **Password Security**: PBKDF2 hashing with salt

## 📱 Views & Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Home page with search form |
| `/register/` | GET, POST | User registration |
| `/login/` | GET, POST | User login |
| `/logout/` | GET | User logout |
| `/search/` | POST | Process flight search |
| `/search/flight/<id>/<date>/` | GET | Flight details |
| `/search/flight/<id>/<date>/ai/` | GET | AI recommendations |

## 🎨 Frontend Features

- **Glass Morphism UI**: Modern, contemporary design with frosted glass effect
- **Custom Fonts**: Commit Mono, Breite Grotesk
- **Responsive Breakpoints**: Mobile-first design approach
- **Interactive Elements**: Real-time search filtering, date pickers
- **Video Support**: Background videos for engaging UI

## 🔐 Security Considerations

- **CSRF Protection**: Django CSRF middleware enabled
- **SQL Injection Prevention**: ORM-based queries
- **XSS Protection**: Template autoescaping enabled
- **Password Hashing**: PBKDF2 with salt
- **API Key Security**: Environment variable storage
- **Secure Headers**: HTTP security headers configured

## 🧪 Testing

Run the test suite:
```bash
cd search
python manage.py test
```

## 📦 Deployment

### Production Settings
- Set `DEBUG=False` in settings
- Configure allowed hosts
- Use environment variables for sensitive data
- Configure static files for production

### Recommended Deployment Stack
- **Web Server**: Gunicorn or uWSGI
- **Reverse Proxy**: Nginx
- **Database**: PostgreSQL
- **Cache**: Redis
- **Platform**: Heroku, AWS, DigitalOcean, or Google Cloud

### Docker (Optional)
```bash
docker build -t aeropilgrim .
docker run -p 8000:8000 aeropilgrim
```

## 📝 Configuration

Key settings in `search/settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Standards
- Follow PEP 8 style guide
- Add docstrings to functions and classes
- Write tests for new features
- Update documentation as needed

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Sky Scrapper API**: For providing real-time flight data
- **Django Community**: For the excellent web framework
- **Contributors**: All developers who have contributed to this project

## 📞 Support & Contact

For support, email us at support@aeropilgrim.com or open an issue on GitHub.

- **Project Issues**: [GitHub Issues](https://github.com/yourusername/aeroPilgrim/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/aeroPilgrim/discussions)

## 🗺️ Roadmap

- [ ] Mobile app (React Native)
- [ ] Multiple payment gateway integration
- [ ] WhatsApp bot integration
- [ ] Group booking features
- [ ] Visa processing guide
- [ ] Prayer time integration
- [ ] Hotel rating and reviews system
- [ ] Multi-language support (Arabic, Bengali, Urdu)

## 📊 Project Statistics

- **Languages**: Python, JavaScript, HTML, CSS
- **Framework**: Django
- **API Integrations**: 2
- **Database Models**: 1 (Main)
- **Views**: 6
- **Authentication**: Built-in

---

Made with ❤️ for Umrah pilgrims worldwide.
