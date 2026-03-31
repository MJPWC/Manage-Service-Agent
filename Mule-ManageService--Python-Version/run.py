#!/usr/bin/env python3
"""
Startup script for the MuleSoft Get Logs Agent Dashboard
"""

import sys
import os

def main():
    """Main entry point"""
    print("MuleSoft Get Logs Agent - Python Version")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return 1
    
    print(f"Python version: {sys.version}")
    print()
    
    # Check if required modules can be imported
    required_modules = ['flask', 'requests', 'dotenv']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✓ {module} - Available")
        except ImportError:
            print(f"✗ {module} - Missing")
            missing_modules.append(module)
    
    if missing_modules:
        print()
        print("Missing required modules:")
        for module in missing_modules:
            print(f"  - {module}")
        print()
        print("Please install missing modules:")
        print("pip install -r requirements.txt")
        return 1
    
    print()
    print("All dependencies satisfied!")
    print()
    print("Starting Flask application...")
    
    # Change to the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Import and run the app
    try:
        from app import app
        print("Dashboard will be available at: http://localhost:3000")
        print("Press Ctrl+C to stop the server")
        print()
        app.run(debug=True, host='0.0.0.0', port=3000)
    except Exception as e:
        print(f"Error starting application: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
