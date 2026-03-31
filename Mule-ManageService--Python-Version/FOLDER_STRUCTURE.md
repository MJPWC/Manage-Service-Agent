# Folder Structure Documentation

## 📁 Overview

This document describes the reorganized folder structure for the MuleSoft Management Service application. The new structure follows Python best practices and provides better separation of concerns.

---

## 🎯 Design Principles

1. **Separation of Concerns** - Clear boundaries between different layers
2. **Scalability** - Easy to add new features without cluttering
3. **Maintainability** - Logical organization for easy navigation
4. **Python Standards** - Follows PEP 8 and common Python project layouts
5. **Clear Dependencies** - Import paths reflect architectural layers

---

## 📂 Directory Structure

```
Mule-ManageService--Python-Version/
│
├── src/                          # Source code
│   ├── __init__.py
│   ├── api/                      # AI/LLM API clients
│   │   ├── __init__.py
│   │   ├── anthropic_client.py   # Claude API client
│   │   ├── cohere_client.py      # Cohere API client
│   │   ├── groq_client.py        # Groq API client
│   │   ├── openrouter_client.py  # OpenRouter API client
│   │   └── llm_manager.py        # LLM orchestration
│   │
│   ├── services/                 # Business logic services
│   │   ├── __init__.py
│   │   ├── github_connector.py   # GitHub authentication
│   │   ├── github_git_operations.py  # Git operations
│   │   └── connectedapp_manager.py   # Connected App OAuth2
│   │
│   ├── utils/                    # Utility modules
│   │   ├── __init__.py
│   │   ├── code_validator.py     # Code validation
│   │   ├── context_analyzer.py   # MuleSoft context analysis
│   │   ├── debug_log_parser.py   # Log parsing
│   │   ├── formatting_rules.py   # Formatting utilities
│   │   └── static_analysis.py    # Static code analysis
│   │
│   └── core/                     # Core business logic
│       └── __init__.py
│
├── static/                       # Static assets (CSS, JS, images)
│   ├── css/
│   │   └── styles.css            # Main stylesheet
│   └── js/
│       └── app.js                # Main JavaScript application
│
├── templates/                    # HTML templates
│   ├── index.html                # Main dashboard
│   └── login.html                # Login page
│
├── docs/                         # Documentation
│   ├── guides/                   # User guides
│   │   ├── CONNECTEDAPP_GUIDE.md
│   │   ├── CONNECTEDAPP_QUICKREF.md
│   │   ├── TOKEN_AUTO_REFRESH_GUIDE.md
│   │   ├── TOKEN_REFRESH_QUICK_GUIDE.md
│   │   └── LOG_ANALYSIS_GUIDE.md
│   │
│   ├── api/                      # API documentation
│   │   ├── CONNECTEDAPP_IMPLEMENTATION.md
│   │   ├── ERROR_GROUPING_CHANGES.md
│   │   ├── ERROR_GROUPING_COMPLETE.md
│   │   ├── ERROR_GROUPING_EXAMPLES.md
│   │   ├── IMPLEMENTATION_SUMMARY.md
│   │   └── README_LOG_PARSER.md
│   │
│   └── features/                 # Feature documentation
│       ├── UI_IMPROVEMENTS.md
│       ├── UI_IMPROVEMENTS_QUICK_REF.md
│       ├── UI_COMPARISON.md
│       ├── UI_SUMMARY.md
│       ├── UI_TESTING_GUIDE.md
│       ├── SCROLLBAR_IMPROVEMENTS.md
│       ├── SCROLLBAR_QUICK_REF.md
│       ├── ANALYSIS_INPUT_AUTOHIDE.md
│       ├── AUTOHIDE_QUICK_REF.md
│       ├── CROSS_LOGIN_FEATURE.md
│       └── CROSS_LOGIN_QUICK_REF.md
│
├── config/                       # Configuration files
│   └── rulesets/                 # AI analysis rulesets
│       ├── error-analysis-rules.txt
│       └── code-changes-rules.txt
│
├── data/                         # Application data
│   └── connected_apps_credentials.csv
│
├── logs/                         # Application logs
│   └── (runtime logs)
│
├── tests/                        # Test files
│   ├── test_extraction.html
│   ├── test_grouping.html
│   └── test_parser.py
│
├── scripts/                      # Utility scripts
│   ├── START.bat                 # Windows startup script
│   └── fix_syntax.py             # Syntax fixing utility
│
├── flask_sessions/               # Flask session storage
├── __pycache__/                  # Python cache (auto-generated)
│
├── app.py                        # Main Flask application
├── run.py                        # Application entry point
├── requirements.txt              # Python dependencies
├── README.md                     # Main README
├── FOLDER_STRUCTURE.md          # This file
│
└── .env                          # Environment variables (not in repo)
```

---

## 📦 Package Descriptions

### `src/` - Source Code

Main application source code organized by architectural layer.

#### `src/api/` - API Clients
**Purpose:** External API integrations for AI/LLM services

**Files:**
- `anthropic_client.py` - Claude (Anthropic) API client
- `cohere_client.py` - Cohere API client  
- `groq_client.py` - Groq API client
- `openrouter_client.py` - OpenRouter API client
- `llm_manager.py` - Orchestrates all LLM clients, handles fallbacks

**Import Pattern:**
```python
from src.api.llm_manager import LLMManager, get_llm_manager
from src.api.anthropic_client import AnthropicClient
```

#### `src/services/` - Business Services
**Purpose:** High-level business logic and external service integrations

**Files:**
- `github_connector.py` - GitHub authentication and API calls
- `github_git_operations.py` - Git operations (clone, commit, PR)
- `connectedapp_manager.py` - Connected App OAuth2 management

**Import Pattern:**
```python
from src.services.github_connector import GitHubAuthenticator
from src.services.connectedapp_manager import get_connected_app_manager
```

#### `src/utils/` - Utilities
**Purpose:** Reusable utility modules and helpers

**Files:**
- `code_validator.py` - MuleSoft code validation
- `context_analyzer.py` - Context analysis for MuleSoft apps
- `debug_log_parser.py` - Parse and analyze MuleSoft logs
- `formatting_rules.py` - Text formatting utilities
- `static_analysis.py` - Static code analysis

**Import Pattern:**
```python
from src.utils.debug_log_parser import MuleLogParser
from src.utils.code_validator import MuleSoftCodeValidator
```

#### `src/core/` - Core Logic
**Purpose:** Core business domain models and logic (currently empty, reserved for future use)

---

### `static/` - Static Assets

**Purpose:** CSS, JavaScript, images, and other static files served to the browser

**Structure:**
- `css/` - Stylesheets
- `js/` - JavaScript files

**Flask Configuration:**
```python
app = Flask(__name__, static_folder="static")
```

**URL Access:**
- `/static/css/styles.css`
- `/static/js/app.js`

---

### `templates/` - HTML Templates

**Purpose:** Jinja2 HTML templates for Flask

**Files:**
- `index.html` - Main dashboard (after login)
- `login.html` - Login page

**Flask Configuration:**
```python
app = Flask(__name__, template_folder="templates")
```

**Usage:**
```python
return render_template('index.html')
return render_template('login.html')
```

---

### `docs/` - Documentation

**Purpose:** All project documentation organized by type

#### `docs/guides/` - User Guides
End-user documentation, how-to guides, and quick references.

#### `docs/api/` - API Documentation
Technical API documentation, implementation details.

#### `docs/features/` - Feature Documentation
Detailed documentation for specific features and UI improvements.

---

### `config/` - Configuration

**Purpose:** Application configuration files

**Contents:**
- `rulesets/` - AI analysis prompt templates and rules
  - `error-analysis-rules.txt` - Error analysis guidelines
  - `code-changes-rules.txt` - Code generation guidelines

**Usage:**
```python
# Paths are resolved relative to project root
RULESETS_DIR = Path(__file__).parent.parent.parent / "config" / "rulesets"
```

---

### `data/` - Application Data

**Purpose:** Runtime data files and user-generated content

**Contents:**
- `connected_apps_credentials.csv` - Stored Connected App credentials

**Note:** This directory may contain sensitive data. Ensure proper `.gitignore` rules.

---

### `logs/` - Log Files

**Purpose:** Application log files and debug outputs

**Note:** Not committed to repository (in `.gitignore`)

---

### `tests/` - Test Files

**Purpose:** Unit tests, integration tests, and test utilities

**Contents:**
- `test_parser.py` - Parser unit tests
- `test_extraction.html` - Extraction test page
- `test_grouping.html` - Grouping test page

---

### `scripts/` - Utility Scripts

**Purpose:** Helper scripts for development and deployment

**Contents:**
- `START.bat` - Windows startup script
- `fix_syntax.py` - Code formatting/fixing script

---

## 🔄 Migration from Old Structure

### What Changed

**Old Structure:**
```
├── public/                    # Mixed HTML, CSS, JS
├── anthropic_client.py        # Root level
├── github_connector.py        # Root level
├── (many Python files at root)
├── rulesets/                  # Root level
└── (docs at root level)
```

**New Structure:**
```
├── src/api/                   # API clients
├── src/services/              # Services
├── src/utils/                 # Utilities
├── static/css/                # Stylesheets
├── static/js/                 # JavaScript
├── templates/                 # HTML
├── docs/guides/               # User docs
├── docs/api/                  # API docs
├── docs/features/             # Feature docs
├── config/rulesets/           # Config files
└── data/                      # Data files
```

### Import Changes

**Before:**
```python
from anthropic_client import AnthropicClient
from github_connector import GitHubAuthenticator
from debug_log_parser import MuleLogParser
```

**After:**
```python
from src.api.anthropic_client import AnthropicClient
from src.services.github_connector import GitHubAuthenticator
from src.utils.debug_log_parser import MuleLogParser
```

### Flask Configuration Changes

**Before:**
```python
app = Flask(__name__, static_folder="public", template_folder="public")
```

**After:**
```python
app = Flask(__name__, static_folder="static", template_folder="templates")
```

### Path Updates Required

**Rulesets:**
```python
# Old
RULESETS_DIR = Path(__file__).parent / "rulesets"

# New
RULESETS_DIR = Path(__file__).parent.parent.parent / "config" / "rulesets"
```

**Connected App Credentials:**
```python
# Old
CREDENTIALS_FILE = 'connected_apps_credentials.csv'

# New
CREDENTIALS_FILE = str(Path(__file__).parent.parent.parent / "data" / "connected_apps_credentials.csv")
```

---

## 📝 Best Practices

### 1. Module Organization

**Do:**
- Group related functionality together
- Keep modules focused and single-purpose
- Use `__init__.py` to expose public APIs

**Don't:**
- Mix different layers (API, service, utils)
- Create circular dependencies
- Put everything in one module

### 2. Import Conventions

**Preferred:**
```python
from src.api.llm_manager import get_llm_manager
from src.services.github_connector import GitHubAuthenticator
```

**Avoid:**
```python
from src.api import *  # Don't use wildcard imports
import src.api.llm_manager  # Prefer from...import
```

### 3. Path Handling

Always use `pathlib.Path` for cross-platform compatibility:

```python
from pathlib import Path

# Good
config_dir = Path(__file__).parent.parent / "config"
data_file = Path(__file__).parent.parent / "data" / "file.csv"

# Avoid
config_dir = "../config"  # String paths are fragile
```

### 4. Adding New Files

**API Client:**
→ Place in `src/api/`

**Business Logic/Service:**
→ Place in `src/services/`

**Utility/Helper:**
→ Place in `src/utils/`

**Documentation:**
→ Place in appropriate `docs/` subdirectory

**Static Asset:**
→ Place in `static/css/` or `static/js/`

---

## 🔍 Finding Files

### Quick Reference

| You need... | Look in... |
|-------------|------------|
| AI/LLM integration | `src/api/` |
| GitHub operations | `src/services/` |
| Log parsing | `src/utils/` |
| Code validation | `src/utils/` |
| Stylesheets | `static/css/` |
| JavaScript | `static/js/` |
| HTML pages | `templates/` |
| User guides | `docs/guides/` |
| Feature docs | `docs/features/` |
| Configuration | `config/` |
| Test files | `tests/` |

---

## ✅ Verification Checklist

After reorganization, verify:

- [ ] Application starts: `python app.py` or `python run.py`
- [ ] Login page loads correctly
- [ ] Static files (CSS/JS) load properly
- [ ] AI analysis works (ruleset paths correct)
- [ ] GitHub integration works
- [ ] Connected App authentication works
- [ ] No import errors in logs
- [ ] All tests pass

---

## 🚀 Benefits of New Structure

### For Developers
- ✅ **Clear organization** - Easy to find what you need
- ✅ **Logical imports** - Import paths reflect architecture
- ✅ **Scalability** - Room to grow without clutter
- ✅ **Standards** - Follows Python community conventions

### For Maintenance
- ✅ **Separation of concerns** - Changes isolated to specific areas
- ✅ **Testability** - Easy to write unit tests
- ✅ **Documentation** - All docs in one place
- ✅ **Configuration** - Clear config management

### For Deployment
- ✅ **Clean structure** - Professional appearance
- ✅ **Easy packaging** - Ready for pip/poetry
- ✅ **Docker-friendly** - Clear boundaries
- ✅ **CI/CD ready** - Standard structure for automation

---

## 📚 Related Documentation

- `README.md` - Main project README
- `docs/guides/` - User guides and how-tos
- `docs/features/` - Feature-specific documentation
- `requirements.txt` - Python dependencies

---

## 🔄 Future Enhancements

Planned improvements to folder structure:

1. **Add `src/models/`** - For database models and schemas
2. **Add `src/middleware/`** - For Flask middleware components
3. **Add `src/routes/`** - Separate route handlers from `app.py`
4. **Add `migrations/`** - For database migrations
5. **Add `docker/`** - Docker-related files
6. **Add `.github/workflows/`** - CI/CD configurations

---

**Last Updated:** 2024  
**Structure Version:** 2.0  
**Status:** ✅ Production Ready