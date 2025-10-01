#!/usr/bin/env python3
"""
Test script to verify database connection and table creation.
"""

import os
import sys
from sqlalchemy import inspect, text
from database import engine, create_tables
from models import User, UserDrug

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def test_tables():
    """Test if tables exist"""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"✓ Found tables: {', '.join(tables)}")
        
        # Check for specific tables
        required_tables = ['users', 'user_drugs']
        missing_tables = [table for table in required_tables if table not in tables]
        
        if missing_tables:
            print(f"✗ Missing tables: {', '.join(missing_tables)}")
            return False
        else:
            print("✓ All required tables exist")
            return True
            
    except Exception as e:
        print(f"✗ Error checking tables: {e}")
        return False

def create_tables_if_needed():
    """Create tables if they don't exist"""
    try:
        print("Creating tables...")
        create_tables()
        print("✓ Tables created successfully")
        return True
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False

def main():
    """Main test function"""
    print("Testing database setup...")
    print("-" * 40)
    
    # Test connection
    if not test_connection():
        sys.exit(1)
    
    # Test tables
    if not test_tables():
        print("\nCreating missing tables...")
        if not create_tables_if_needed():
            sys.exit(1)
        
        # Test again
        if not test_tables():
            sys.exit(1)
    
    print("\n✓ Database setup is working correctly!")

if __name__ == "__main__":
    main()
