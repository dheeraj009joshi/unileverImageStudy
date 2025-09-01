# UnileverImageStudy

A production-ready Flask application for conducting IPED (Individual Parameter Estimation Design) research studies with comprehensive task timing analytics and anonymous respondent participation.

## 🚀 Features

### Core Functionality
- **Multi-Step Study Creation**: 3-step wizard for creating IPED studies
- **Study Types**: Support for both image and text-based studies
- **Anonymous Participation**: Public study access without registration
- **Task Timing Analytics**: Detailed tracking of time spent on each task and element
- **IPED Algorithm**: Automated task matrix generation with balanced element distribution
- **Data Export**: JSON and CSV export with complete timing data

### User Management
- **Study Creators**: Registration, authentication, and profile management
- **Anonymous Respondents**: No authentication required for study participation
- **Secure Sessions**: CSRF protection and secure cookie handling

### Analytics & Reporting
- **Real-time Dashboard**: Live study statistics and progress tracking
- **Task Timing Analysis**: Detailed completion time analytics
- **Element Interaction Heatmaps**: Visual representation of user engagement
- **Abandonment Analysis**: Track and analyze study abandonment patterns
- **Export Functionality**: Multiple format support for data analysis

## 🏗️ Architecture

### Technology Stack
- **Backend**: Flask 2.3.3 with Python 3.9+
- **Database**: MongoDB with MongoEngine ODM
- **Authentication**: Flask-Login + Flask-WTF
- **Frontend**: Pure HTML5, CSS3, JavaScript (no external libraries)
- **File Handling**: Secure file uploads with validation
- **Deployment**: Docker + Nginx + Gunicorn

### Database Models
- **Users**: Study creators with authentication
- **Studies**: Complete study configuration and IPED task matrices
- **StudyResponses**: Anonymous respondent submissions with timing data
- **TaskSessions**: Individual task timing and interaction tracking

## 📋 Requirements

### System Requirements
- Python 3.9+
- MongoDB 6.0+
- Redis 7.0+ (optional, for caching)
- Docker & Docker Compose (for deployment)

### Python Dependencies
```
Flask==2.3.3
Flask-Login==0.6.3
Flask-WTF==1.1.1
WTForms==3.0.1
mongoengine==0.27.0
pymongo==4.5.0
flask-mongoengine==1.0.0
Werkzeug==2.3.7
Pillow==10.0.0
python-dotenv==1.0.0
gunicorn==21.2.0
bcrypt==4.0.1
email-validator==2.0.0
```

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone <repository-url>
cd immInnovation
```

### 2. Set Up Environment
```bash
# Copy environment template
cp env.example .env

# Edit .env with your configuration
nano .env
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Up MongoDB
```bash
# Start MongoDB (if using Docker)
docker run -d --name mongodb -p 27017:27017 mongo:6.0

# Or install MongoDB locally
# Follow MongoDB installation guide for your OS
```

### 5. Run the Application
```bash
# Development mode
python app.py

# Production mode
gunicorn --bind 0.0.0.0:55000 app:create_app()
```

### 6. Access the Application
- **Main App**: http://localhost:55000
- **Dashboard**: http://localhost:55000/dashboard
- **Study Creation**: http://localhost:55000/study/create

## 🐳 Docker Deployment

### 1. Build and Run with Docker Compose
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### 2. Individual Services
```bash
# Build Flask app
docker build -t iped-system .

# Run Flask app
docker run -p 55000:55000 iped-system

# Run MongoDB
docker run -d --name mongodb -p 27017:27017 mongo:6.0
```

## 📚 Usage Guide

### Creating a Study

1. **Register/Login**: Create an account or sign in
2. **Start Study Creation**: Navigate to "Create Study"
3. **Step 1: Basic Information**
   - Study title and background
   - Language selection
   - Terms acceptance
4. **Step 2: Study Configuration**
   - Study type (image/text)
   - Main question and orientation
   - Rating scale configuration
   - Study elements setup
   - Classification questions
   - IPED parameters
5. **Step 3: Task Generation**
   - Generate IPED task matrix
   - Preview and launch study

### Study Participation (Anonymous)

1. **Access Study**: Use the generated share URL
2. **Welcome Page**: Read study information and consent
3. **Classification Questions**: Answer demographic questions (optional)
4. **Orientation**: Read study instructions
5. **Complete Tasks**: Rate elements in each task
6. **Study Completion**: Receive completion confirmation

### Dashboard Features

- **Study Overview**: List all created studies
- **Real-time Statistics**: Live response tracking
- **Analytics**: Detailed timing and interaction data
- **Data Export**: Download results in multiple formats
- **Study Management**: Edit, pause, and delete studies

## 🔧 Configuration

### Environment Variables

```bash
# Flask Configuration
FLASK_ENV=production
SECRET_KEY=your-super-secret-key
DEBUG=False

# MongoDB Configuration
MONGODB_URI=mongodb://username:password@host:port/database

# File Upload Configuration
MAX_CONTENT_LENGTH=5242880
UPLOAD_FOLDER=./uploads

# Security Configuration
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
```

### MongoDB Configuration

```javascript
// MongoDB connection string format
mongodb://username:password@host:port/database?authSource=admin

// Example
mongodb://admin:password123@localhost:27017/iped_system?authSource=admin
```

## 📊 IPED Algorithm

### Task Matrix Generation

The system implements the IPED algorithm to generate balanced task assignments:

1. **Parameter Input**:
   - Number of elements (4-16)
   - Tasks per consumer (1-100)
   - Number of respondents (1-10,000)
   - Min/max active elements per task

2. **Matrix Generation**:
   - Creates candidate task pool
   - Ensures balanced element distribution
   - Validates constraints (min/max active elements)
   - Generates respondent-specific task sequences

3. **Task Structure**:
   ```json
   {
     "0": [  // Respondent 0
       {
         "task_id": "0_0",
         "elements_shown": {"E1": 1, "E2": 0, "E3": 1, ...},
         "task_index": 0
       }
     ]
   }
   ```

## 🔒 Security Features

### Authentication & Authorization
- Secure password hashing with bcrypt
- Session management with Flask-Login
- CSRF protection for all forms
- Secure cookie configuration

### File Upload Security
- File type validation (images only)
- File size limits (5MB max)
- Secure filename generation
- Upload directory isolation

### Rate Limiting
- API endpoint rate limiting
- Login attempt throttling
- Anonymous user protection

## 📈 Analytics & Reporting

### Task Timing Analytics
- **Individual Task Timing**: Start/end timestamps and duration
- **Element Interaction Tracking**: View time, hover count, click count
- **Page Visibility Tracking**: Handle tab switching and minimize
- **Abandonment Detection**: Track incomplete tasks and reasons

### Data Export Options
- **JSON Export**: Complete data structure preservation
- **CSV Export**: Compatible with statistical analysis software
- **Timing Data**: Include all interaction and timing information
- **Anonymized Options**: Remove identifying information

### Real-time Dashboard
- **Response Tracking**: Live completion statistics
- **Performance Metrics**: Average completion times
- **Geographic Distribution**: IP-based analytics
- **Trend Analysis**: Daily/weekly completion patterns

## 🧪 Testing

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-flask pytest-mongodb

# Run tests
pytest tests/

# Run with coverage
pytest --cov=app tests/
```

### Test Coverage
- Unit tests for models and utilities
- Integration tests for API endpoints
- Form validation testing
- Database operation testing

## 🚀 Production Deployment

### Prerequisites
- SSL certificates for HTTPS
- Domain name configuration
- MongoDB production setup
- Redis for session storage (optional)

### Deployment Steps
1. **Environment Setup**: Configure production environment variables
2. **SSL Configuration**: Set up SSL certificates
3. **Database Setup**: Configure MongoDB with authentication
4. **Service Configuration**: Set up systemd services
5. **Monitoring**: Configure logging and monitoring
6. **Backup**: Set up automated backup procedures

### Performance Optimization
- **MongoDB Indexing**: Optimize database queries
- **Static File Serving**: Configure Nginx for static files
- **Caching**: Implement Redis caching layer
- **Load Balancing**: Set up multiple application instances

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

### Code Standards
- Follow PEP 8 Python style guidelines
- Add comprehensive docstrings
- Include type hints where appropriate
- Write unit tests for new features

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Documentation
- [API Documentation](docs/api.md)
- [User Guide](docs/user-guide.md)
- [Developer Guide](docs/developer-guide.md)

### Issues & Questions
- Create an issue on GitHub
- Check existing issues for solutions
- Review the documentation

### Community
- Join our discussion forum
- Contribute to the project
- Share your use cases

## 🔄 Changelog

### Version 1.0.0
- Initial release with core IPED functionality
- Multi-step study creation wizard
- Anonymous respondent participation
- Comprehensive task timing analytics
- Production-ready deployment configuration

## 📞 Contact

- **Project Maintainer**: Dheeraj Joshi
- **Email**: dlovej009@gmail.com
- **GitHub**: dheeraj009joshi

---

**Note**: This system is designed for research purposes and includes comprehensive data collection. Ensure compliance with relevant privacy regulations (GDPR, CCPA, etc.) when deploying in production environments.
# inniImage
# unileverImageStudy
