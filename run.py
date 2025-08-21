#!/usr/bin/env python3
"""
Simple startup script for the UnileverImageStudy
Run this for development purposes
"""

import os
import sys
from app import create_app, create_tables

def main():
    """Main startup function."""
    print("🚀 Starting UnileverImageStudy...")
    
    # Create application
    app = create_app()
    
    # Create database tables/indexes
    # with app.app_context():
    #     try:
    #         create_tables()
    #         print("✅ Database setup completed")
    #     except Exception as e:
    #         print(f"⚠️  Database setup warning: {e}")
    #         print("   Continuing with startup...")
    
    # Run the application
    print("🌐 Starting Flask development server...")
    print("   Access the application at: http://localhost:55000")
    print("   Dashboard: http://localhost:55000/dashboard")
    print("   Study Creation: http://localhost:55000/study/create")
    print("\n   Press Ctrl+C to stop the server")
    
    app.run(
        debug=True,
        host='0.0.0.0',
        port=55000,
        use_reloader=True
    )

if __name__ == '__main__':
    main()
