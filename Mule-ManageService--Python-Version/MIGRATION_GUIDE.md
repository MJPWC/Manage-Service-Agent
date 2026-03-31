# Migration Guide - Folder Restructuring

## 📋 Overview

This guide helps you migrate from the old folder structure to the new organized structure. All changes have been applied automatically, but this document explains what changed and how to verify everything works.

---

## 🎯 Quick Start

### Immediate Actions Required

1. **Stop the application** if it's running
2. **Pull latest changes** from repository
3. **Verify folder structure** matches new layout
4. **Test the application** using checklist below
5. **Update any custom scripts** if you have them

---

## 📂 What Changed

### Folder Reorganization

#### Old Structure → New Structure

| Old Location | New Location | Type |
|-------------|--------------|------|
| `public/styles.css` | `static/css/styles.css` | Static |
| `public/app.js` | `static/js/app.js` | Static |
| `public/index.html` | `templates/index.html` | Template |
| `public/login.html` | `templates/login.html` | Template |
| `anthropic_client.py` | `src/api/anthropic_client.py` | API |
| `cohere_client.py` | `src/api/cohere_client.py` | API |
| `groq_client.py` | `src/api/groq_client.py` | API |
| `openrouter_client.py` | `src/api/openrouter_client.py` | API |
| `llm_manager.py` | `src/api/llm_manager.py` | API |
| `github_connector.py` | `src/services/github_connector.py` | Service |
| `github_git_operations.py` | `src/services/github_git_operations.py` | Service |
| `connectedapp_manager.py` | `src/services/connectedapp_manager.py` | Service |
| `code_validator.py` | `src/utils/code_validator.py` | Util |
| `context_analyzer.py` | `src/utils/context_analyzer.py` | Util |
| `debug_log_parser.py` | `src/utils/debug_log_parser.py` | Util |
| `formatting_rules.py` | `src/utils/formatting_rules.py` | Util |
| `static_analysis.py` | `src/utils/static_analysis.py` | Util |
| `connected_apps_credentials.csv` | `data/connected_apps_credentials.csv` | Data |
| `rulesets/` | `config/rulesets/` | Config |
| `*.md` (guides) | `docs/guides/*.md` | Docs |
| `*.md` (features) | `docs/features/*.md` | Docs |
| `*.md` (API) | `docs/api/*.md` | Docs |
| `test_*.html`, `test_*.py` | `tests/test_*` | Tests |
| `fix_syntax.py`, `START.bat` | `scripts/*` | Scripts |

---

## 🔧 Code Changes Applied

### 1. Import Statements (`app.py`)

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

### 2. Flask Configuration (`app.py`)

**Before:**
```python
app = Flask(__name__, static_folder="public", template_folder="public")
```

**After:**
```python
app = Flask(__name__, static_folder="static", template_folder="templates")
```

### 3. Ruleset Paths (All LLM Clients)

**Before:**
```python
RULESETS_DIR = Path(__file__).parent / "rulesets"
```

**After:**
```python
RULESETS_DIR = Path(__file__).parent.parent.parent / "config" / "rulesets"
```

**Affected Files:**
- `src/api/anthropic_client.py`
- `src/api/cohere_client.py`
- `src/api/groq_client.py`
- `src/api/openrouter_client.py`

### 4. Credentials Path (`connectedapp_manager.py`)

**Before:**
```python
CREDENTIALS_FILE = 'connected_apps_credentials.csv'
```

**After:**
```python
CREDENTIALS_FILE = str(Path(__file__).parent.parent.parent / "data" / "connected_apps_credentials.csv")
```

### 5. Package Initialization

**New Files Created:**
- `src/__init__.py`
- `src/api/__init__.py`
- `src/services/__init__.py`
- `src/utils/__init__.py`
- `src/core/__init__.py`

---

## ✅ Verification Steps

### Step 1: Check Folder Structure

Run this command to verify the structure:

**Windows:**
```cmd
dir /s /b src static templates docs config data tests scripts
```

**Linux/Mac:**
```bash
find src static templates docs config data tests scripts -type f
```

**Expected Output:**
- `src/` with subdirectories `api/`, `services/`, `utils/`, `core/`
- `static/` with subdirectories `css/`, `js/`
- `templates/` with `index.html`, `login.html`
- `docs/` with subdirectories `guides/`, `api/`, `features/`
- `config/rulesets/` with ruleset files
- `data/` with CSV file
- `tests/` with test files
- `scripts/` with utility scripts

### Step 2: Start the Application

**Option 1: Using run.py**
```bash
python run.py
```

**Option 2: Using app.py**
```bash
python app.py
```

**Option 3: Using START.bat (Windows)**
```cmd
scripts\START.bat
```

**Expected Output:**
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

**✅ Success Indicators:**
- No import errors
- No "File not found" errors
- Server starts successfully

**❌ Failure Indicators:**
- `ModuleNotFoundError: No module named 'src'`
- `FileNotFoundError: rulesets not found`
- Template or static file errors

### Step 3: Test Login Page

1. Open browser: `http://localhost:5000/login`
2. **Check:**
   - [ ] Page loads without errors
   - [ ] CSS styles are applied
   - [ ] JavaScript loads (check browser console)
   - [ ] No 404 errors in network tab

### Step 4: Test Login Functionality

1. Try Anypoint login with valid credentials
2. **Check:**
   - [ ] Authentication works
   - [ ] No errors in server console
   - [ ] Redirect to dashboard works

### Step 5: Test Dashboard

1. After login, verify dashboard loads
2. **Check:**
   - [ ] Static files (CSS/JS) load
   - [ ] No 404 errors
   - [ ] UI displays correctly

### Step 6: Test AI Analysis

1. Select an API with errors
2. Upload a log file or use GitHub integration
3. Click "Analyze"
4. **Check:**
   - [ ] Analysis runs without errors
   - [ ] Rulesets are loaded correctly
   - [ ] Results display properly

### Step 7: Test GitHub Integration

1. Login to GitHub (if not already)
2. Browse repositories
3. View a file
4. Run AI analysis
5. **Check:**
   - [ ] GitHub API calls work
   - [ ] File content displays
   - [ ] Analysis works

---

## 🐛 Troubleshooting

### Issue 1: Import Errors

**Error:**
```
ModuleNotFoundError: No module named 'src'
```

**Solution:**
Make sure you're running from the project root directory:
```bash
cd Mule-ManageService--Python-Version
python app.py
```

**Verify PYTHONPATH includes current directory:**
```bash
# Windows
set PYTHONPATH=%CD%

# Linux/Mac
export PYTHONPATH=$(pwd)
```

### Issue 2: Template Not Found

**Error:**
```
jinja2.exceptions.TemplateNotFound: index.html
```

**Solution:**
Verify Flask configuration in `app.py`:
```python
app = Flask(__name__, static_folder="static", template_folder="templates")
```

Check that `templates/index.html` exists.

### Issue 3: Static Files 404

**Error:**
```
GET /static/css/styles.css 404 (Not Found)
```

**Solution:**
1. Verify `static/css/styles.css` exists
2. Check Flask static folder configuration
3. Clear browser cache

### Issue 4: Ruleset Not Found

**Error:**
```
[AnthropicClient] Warning: Ruleset not found: /path/to/rulesets/error-analysis-rules.txt
```

**Solution:**
1. Verify `config/rulesets/error-analysis-rules.txt` exists
2. Check path in LLM client files:
   ```python
   RULESETS_DIR = Path(__file__).parent.parent.parent / "config" / "rulesets"
   ```

### Issue 5: Credentials File Not Found

**Error:**
```
FileNotFoundError: connected_apps_credentials.csv
```

**Solution:**
1. Verify `data/connected_apps_credentials.csv` exists
2. Check path in `connectedapp_manager.py`:
   ```python
   CREDENTIALS_FILE = str(Path(__file__).parent.parent.parent / "data" / "connected_apps_credentials.csv")
   ```
3. If file doesn't exist, it will be created automatically on first Connected App login

---

## 🔄 Reverting Changes (If Needed)

If you need to revert to the old structure:

1. **Backup current state**
   ```bash
   git stash
   ```

2. **Checkout previous commit**
   ```bash
   git checkout <previous-commit-hash>
   ```

3. **Or manually revert** using your backup

**Note:** Not recommended. The new structure is better for long-term maintenance.

---

## 📝 Custom Scripts Update

If you have custom scripts that import modules, update them:

### Example: Custom Analysis Script

**Before:**
```python
from debug_log_parser import MuleLogParser
from llm_manager import get_llm_manager

parser = MuleLogParser()
llm = get_llm_manager()
```

**After:**
```python
from src.utils.debug_log_parser import MuleLogParser
from src.api.llm_manager import get_llm_manager

parser = MuleLogParser()
llm = get_llm_manager()
```

---

## 🚀 Benefits of New Structure

### Developer Experience
- ✅ **Clear organization** - Easy to find files
- ✅ **Logical grouping** - Related files together
- ✅ **Standard structure** - Follows Python conventions
- ✅ **Better imports** - Clear architectural layers

### Maintenance
- ✅ **Separation of concerns** - API, services, utils clearly separated
- ✅ **Scalability** - Easy to add new features
- ✅ **Documentation** - All docs organized
- ✅ **Testing** - Dedicated tests folder

### Deployment
- ✅ **Professional** - Industry-standard structure
- ✅ **Docker-friendly** - Clear boundaries
- ✅ **CI/CD ready** - Standard layout
- ✅ **Packaging** - Ready for pip/poetry

---

## 📚 Next Steps

After successful migration:

1. **Update README.md** (if you have custom instructions)
2. **Update deployment scripts** (if any)
3. **Update CI/CD pipelines** (if configured)
4. **Train team** on new structure
5. **Update documentation** with new paths

---

## 📞 Support

### Documentation References
- `FOLDER_STRUCTURE.md` - Detailed structure documentation
- `README.md` - Main project README
- `docs/guides/` - User guides
- `docs/features/` - Feature documentation

### Common Questions

**Q: Do I need to reinstall dependencies?**
A: No, `requirements.txt` is unchanged.

**Q: Will my data be preserved?**
A: Yes, all data in `data/` and `logs/` is preserved.

**Q: Do I need to update environment variables?**
A: No, `.env` file is unchanged.

**Q: What about my local changes?**
A: Commit or stash them before pulling updates.

---

## ✅ Migration Checklist

Use this checklist to ensure complete migration:

### Pre-Migration
- [ ] Backup current working directory
- [ ] Commit or stash local changes
- [ ] Note any custom scripts or modifications

### Migration
- [ ] Pull latest changes
- [ ] Verify folder structure matches new layout
- [ ] Check all files moved to correct locations
- [ ] Verify `__init__.py` files created

### Testing
- [ ] Application starts without errors
- [ ] Login page loads and works
- [ ] Dashboard loads correctly
- [ ] Static files (CSS/JS) load
- [ ] AI analysis works
- [ ] GitHub integration works
- [ ] Connected App authentication works
- [ ] No errors in console/logs

### Post-Migration
- [ ] Update custom scripts (if any)
- [ ] Update documentation (if needed)
- [ ] Train team on new structure
- [ ] Remove old backup (after confirming everything works)

---

## 🎉 Success Criteria

Migration is successful when:

1. ✅ Application starts without errors
2. ✅ All pages load correctly
3. ✅ All features work as before
4. ✅ No 404 errors for static files
5. ✅ No import errors in logs
6. ✅ AI analysis functions properly
7. ✅ GitHub integration works
8. ✅ Connected App authentication works

---

**Migration Guide Version:** 1.0  
**Last Updated:** 2024  
**Status:** ✅ Complete  

**If you encounter any issues not covered here, check `FOLDER_STRUCTURE.md` or contact the development team.**