# Mule-ManageService--Python-Version

Exact Python replica of the Node.js MuleSoft Get Logs Agent Web Dashboard with the same UI and functionality.

## Features

### ✅ Core Features
- **Web Dashboard** - Modern, responsive web interface for viewing MuleSoft applications and logs
- **Environment Selection** - Display and select from available Anypoint Platform environments
- **Application Management** - View all deployed APIs with status indicators and error counts
- **Advanced Log Parser** - Converts raw Mule logs to structured JSON (ported from Node.js)
- **Error Log Viewing** - View and analyze ERROR level logs with detailed formatting
- **Real-time Error Counts** - Shows error count badges for each application

### ✅ UI/UX Features
- **Dark/Light Theme** - Switch between light and dark themes
- **Responsive Design** - Works on desktop and mobile devices
- **Search Functionality** - Filter applications by name
- **Interactive Settings** - Configure Anypoint Platform and GitHub credentials
- **Loading States** - Visual feedback during data fetching
- **Error Handling** - User-friendly error messages and banners

### ✅ Technical Features
- **Flask Backend** - RESTful API with all endpoints from the original Node.js version
- **Session Management** - In-memory session storage for authentication
- **Log Parsing** - Python port of the original JavaScript log parser
- **API Integration** - Full Anypoint Platform API integration
- **Security** - Secure credential handling (in-memory only)

## Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python Package Manager)
- Anypoint Platform credentials

### Installation

```bash
# Navigate to the Python version directory
cd Mule-ManageService--Python-Version

# Install dependencies
pip install -r requirements.txt

# Start the web application
python app.py
```

The dashboard will be available at http://localhost:3000

### Usage

1. **Open Settings** - Click the settings icon to configure your Anypoint Platform credentials
2. **Test Connection** - Use the "Test Connection" button to verify your credentials
3. **Save Credentials** - Save your Anypoint username and password
4. **Select Environment** - Choose an environment from the dropdown menu
5. **View Applications** - Browse deployed applications with error counts
6. **View Logs** - Click on any application to view its error logs
7. **Search & Filter** - Use the search box to filter applications
8. **Refresh Data** - Use the refresh button to update application and log data

## Project Structure

```
Mule-ManageService--Python-Version/
├── src/                     # Source code
│   ├── api/                 # AI/LLM clients (Gemini, OpenAI, etc.)
│   ├── services/            # Business services (GitHub, ServiceNow)
│   ├── utils/               # Utilities and log parsers
│   └── core/                # Core business logic
├── static/                  # Static assets (CSS, JS)
├── templates/               # HTML templates
├── config/                  # Configuration (AI rulesets)
├── data/                    # Application data (CSV storage)
├── docs/                    # Detailed documentation
├── tests/                   # Test files
├── scripts/                 # Utility scripts
├── app.py                   # Main Flask application
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/session` | GET | Check authentication status |
| `/api/anypoint/test` | POST | Test Anypoint credentials |
| `/api/anypoint/login` | POST | Login and save session |
| `/api/environments` | GET | List environments |
| `/api/environments/:id/applications` | GET | List applications |
| `/api/environments/:envId/applications/:appId/logs` | GET | Get error logs |
| `/api/environments/:envId/error-counts` | GET | Get error counts for all apps |
| `/api/github/test` | POST | Test GitHub credentials |
| `/api/logout` | POST | Logout and clear session |

## Log Parser

The Python version includes an exact port of the Node.js log parser functionality:

- **Structured Parsing** - Converts raw Mule logs to JSON format
- **Exception Handling** - Parses exception blocks with detailed information
- **Data Extraction** - Extracts correlation IDs, timestamps, components, and metadata
- **Error Detection** - Identifies and categorizes log levels
- **Flow Stack Analysis** - Captures Mule flow execution context

### Parser Features

```python
from app import LogParser

# Parse raw log text
logs = LogParser.parse_logs(raw_log_text)

# Each log entry contains:
# - timestamp: ISO timestamp
# - level: Log level (ERROR, INFO, etc.)
# - tag: Log tag
# - component: Mule component name
# - context: Execution context
# - message: Log message
# - data: Parsed key-value data
# - exception: Exception details (if present)
# - event_id: Correlation ID (if present)
```

## Configuration

### Environment Variables

- `PORT` - Server port (default: 3000)

### Theme Configuration

The application supports light and dark themes:
- Light theme is enabled by default
- Dark mode can be toggled in Settings > General
- Theme preference is saved in localStorage

## Security Considerations

⚠️ **Important**: This version uses in-memory session storage and is not suitable for production use without additional security measures:

- Credentials are stored in memory only
- No token encryption or persistence
- No HTTPS enforcement
- Session data is lost on server restart

For production use, consider:
- Implementing proper session storage (Redis, database)
- Adding token encryption
- Enforcing HTTPS
- Implementing proper authentication and authorization

## Dependencies

- **Flask** - Web framework
- **Flask-CORS** - Cross-origin resource sharing
- **requests** - HTTP client for API calls
- **python-dotenv** - Environment variable management
- **cryptography** - Encryption utilities (for future enhancements)

## Comparison with Node.js Version

| Feature | Node.js Version | Python Version |
|---------|----------------|----------------|
| Web Dashboard | ✅ | ✅ (Exact replica) |
| UI/UX | ✅ | ✅ (Exact replica) |
| Log Parser | ✅ | ✅ (Ported) |
| API Endpoints | ✅ | ✅ (All ported) |
| Theme Support | ✅ | ✅ |
| Error Handling | ✅ | ✅ |
| Session Management | ✅ | ✅ (In-memory) |
| CLI Interface | ✅ | ❌ (Web only) |
| Log Filtering | ✅ | ❌ (Web only) |

## Development

### Running in Development Mode

```bash
# Install dependencies
pip install -r requirements.txt

# Run with debug mode
python app.py
```

The Flask development server will automatically reload on code changes.

### Adding New Features

1. **Backend Changes** - Modify `app.py`
2. **Frontend Changes** - Modify files in `public/`
3. **API Endpoints** - Add new routes in `app.py`
4. **UI Components** - Add to `public/index.html` and `public/styles.css`

## Troubleshooting

### "Connection failed" error
- Verify your Anypoint Platform username and password
- Check your network connection
- Ensure you're using the correct organization

### "No applications found"
- Check that your environment has deployed APIs
- Verify the environment has the correct permissions
- Try selecting a different environment

### Server won't start
- Check if port 3000 is already in use
- Verify Python 3.8+ is installed
- Ensure all dependencies are installed

## License

This project maintains the same license as the original Node.js version.

---

**Current Version:** 1.0.0  
**Last Updated:** 2026-02-05  
**Compatibility:** Python 3.8+
