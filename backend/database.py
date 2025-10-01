from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from urllib.parse import quote_plus

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mariadb+pymysql://root:P%40ssw0rd@localhost:3306/DrugBank"
)

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=10,
    max_overflow=20
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

# Metadata for migrations
metadata = MetaData()

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Create all tables"""
    # Import models to ensure they are registered with Base.metadata
    from models import User, UserDrug
    Base.metadata.create_all(bind=engine)

def drop_tables():
    """Drop all tables"""
    # Import models to ensure they are registered with Base.metadata
    from models import User, UserDrug
    Base.metadata.drop_all(bind=engine)


if __name__ == "__main__":
    create_tables()
