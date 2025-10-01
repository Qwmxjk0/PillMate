from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, List
import uvicorn

# Import database and models
from database import get_db, create_tables
from models import User, UserDrug
from schemas import UserCreate, UserResponse, UserUpdate, UserLogin, UserDrugCreate, UserDrugResponse, UserDrugUpdate

app = FastAPI(
    title="PillMate Backend API",
    description="FastAPI backend with Server-Sent Events support",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "PillMate Backend API",
        "version": "1.0.0",
        "endpoints": {
            "sse": "/events",
            "docs": "/docs",
            "health": "/health",
            "users": "/users",
            "user_drugs": "/user-drugs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/events")
async def stream_events():
    """Server-Sent Events endpoint"""
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

async def event_stream() -> AsyncGenerator[str, None]:
    """Generate server-sent events"""
    counter = 0
    try:
        while True:
            # Create a sample event
            event_data = {
                "id": counter,
                "timestamp": datetime.now().isoformat(),
                "message": f"Event {counter}",
                "data": {
                    "counter": counter,
                    "random_value": counter * 2
                }
            }
            
            # Format as SSE
            event = f"id: {counter}\n"
            event += f"event: message\n"
            event += f"data: {json.dumps(event_data)}\n\n"
            
            yield event
            counter += 1
            
            # Wait before sending next event
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        # Client disconnected
        print("Client disconnected from SSE stream")
        raise

@app.get("/events/custom")
async def stream_custom_events(duration: int = 30, interval: float = 1.0):
    """Custom SSE endpoint with configurable duration and interval"""
    if duration > 300:  # Max 5 minutes
        raise HTTPException(status_code=400, detail="Duration cannot exceed 300 seconds")
    
    return StreamingResponse(
        custom_event_stream(duration, interval),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

async def custom_event_stream(duration: int, interval: float) -> AsyncGenerator[str, None]:
    """Generate custom server-sent events with specified duration and interval"""
    counter = 0
    start_time = datetime.now()
    
    try:
        while (datetime.now() - start_time).total_seconds() < duration:
            event_data = {
                "id": counter,
                "timestamp": datetime.now().isoformat(),
                "message": f"Custom event {counter}",
                "progress": min(100, (counter * 100) // (duration // int(interval))),
                "data": {
                    "counter": counter,
                    "elapsed_seconds": (datetime.now() - start_time).total_seconds(),
                    "remaining_seconds": duration - (datetime.now() - start_time).total_seconds()
                }
            }
            
            # Format as SSE
            event = f"id: {counter}\n"
            event += f"event: custom\n"
            event += f"data: {json.dumps(event_data)}\n\n"
            
            yield event
            counter += 1
            
            await asyncio.sleep(interval)
            
    except asyncio.CancelledError:
        print("Client disconnected from custom SSE stream")
        raise

# User Management Endpoints

@app.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create a new user"""
    # Check if password and confirm password equal
    is_valid = user.password == user.confirm_password
    if not is_valid :
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password and Confirm Password incorrect"
        )
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    db_user = User(email=user.email)
    db_user.set_password(user.password)
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

# @app.get("/users/", response_model=List[UserResponse])
# async def get_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
#     """Get all users with pagination"""
#     users = db.query(User).offset(skip).limit(limit).all()
#     return users

# @app.get("/users/{user_id}", response_model=UserResponse)
# async def get_user(user_id: int, db: Session = Depends(get_db)):
#     """Get a specific user by ID"""
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="User not found"
#         )
#     return user

# @app.put("/users/{user_id}", response_model=UserResponse)
# async def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
#     """Update a user"""
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="User not found"
#         )
    
#     # Update fields if provided
#     if user_update.email is not None:
#         # Check if email is already taken by another user
#         existing_user = db.query(User).filter(
#             User.email == user_update.email,
#             User.id != user_id
#         ).first()
#         if existing_user:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Email already registered"
#             )
#         user.email = user_update.email
    
#     if user_update.password is not None:
#         user.set_password(user_update.password)
    
#     if user_update.is_active is not None:
#         user.is_active = user_update.is_active
    
#     if user_update.is_verified is not None:
#         user.is_verified = user_update.is_verified
    
#     db.commit()
#     db.refresh(user)
#     return user

# @app.delete("/users/{user_id}")
# async def delete_user(user_id: int, db: Session = Depends(get_db)):
#     """Delete a user"""
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="User not found"
#         )
    
#     db.delete(user)
#     db.commit()
#     return {"message": "User deleted successfully"}

@app.post("/users/login")
async def login_user(user_login: UserLogin, db: Session = Depends(get_db)):
    """Login user and verify credentials"""
    user = db.query(User).filter(User.email == user_login.email).first()
    
    if not user or not user.verify_password(user_login.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    
    return {
        "message": "Login successful",
        "user": user.to_dict()
    }

# User-Drug Management Endpoints

@app.post("/user-drugs/", response_model=UserDrugResponse, status_code=status.HTTP_201_CREATED)
async def create_user_drug(user_drug: UserDrugCreate, user_id: int, db: Session = Depends(get_db)):
    """Add a drug to a user's list"""
    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if user already has this drug
    existing_user_drug = db.query(UserDrug).filter(
        UserDrug.user_id == user_id,
        UserDrug.drugbank_id == user_drug.drugbank_id
    ).first()
    
    if existing_user_drug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has this drug"
        )
    
    # Create new user-drug relationship
    db_user_drug = UserDrug(
        user_id=user_id,
        drugbank_id=user_drug.drugbank_id
    )
    
    db.add(db_user_drug)
    db.commit()
    db.refresh(db_user_drug)
    
    return db_user_drug

@app.get("/user-drugs/", response_model=List[UserDrugResponse])
async def get_user_drugs(user_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all drugs for a specific user"""
    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user_drugs = db.query(UserDrug).filter(
        UserDrug.user_id == user_id
    ).offset(skip).limit(limit).all()
    
    return user_drugs

@app.get("/user-drugs/{user_drug_id}", response_model=UserDrugResponse)
async def get_user_drug(user_drug_id: int, db: Session = Depends(get_db)):
    """Get a specific user-drug relationship"""
    user_drug = db.query(UserDrug).filter(UserDrug.id == user_drug_id).first()
    if not user_drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User-drug relationship not found"
        )
    return user_drug

@app.put("/user-drugs/{user_drug_id}", response_model=UserDrugResponse)
async def update_user_drug(user_drug_id: int, user_drug_update: UserDrugUpdate, db: Session = Depends(get_db)):
    """Update a user-drug relationship"""
    user_drug = db.query(UserDrug).filter(UserDrug.id == user_drug_id).first()
    if not user_drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User-drug relationship not found"
        )
    
    # Update drugbank_id if provided
    if user_drug_update.drugbank_id is not None:
        # Check if user already has this new drug
        existing_user_drug = db.query(UserDrug).filter(
            UserDrug.user_id == user_drug.user_id,
            UserDrug.drugbank_id == user_drug_update.drugbank_id,
            UserDrug.id != user_drug_id
        ).first()
        
        if existing_user_drug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has this drug"
            )
        
        user_drug.drugbank_id = user_drug_update.drugbank_id
    
    db.commit()
    db.refresh(user_drug)
    return user_drug

@app.delete("/user-drugs/{user_drug_id}")
async def delete_user_drug(user_drug_id: int, db: Session = Depends(get_db)):
    """Remove a drug from a user's list"""
    user_drug = db.query(UserDrug).filter(UserDrug.id == user_drug_id).first()
    if not user_drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User-drug relationship not found"
        )
    
    db.delete(user_drug)
    db.commit()
    return {"message": "User-drug relationship deleted successfully"}

@app.get("/users/{user_id}/drugs", response_model=List[UserDrugResponse])
async def get_user_drugs_by_user(user_id: int, db: Session = Depends(get_db)):
    """Get all drugs for a specific user (alternative endpoint)"""
    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user_drugs = db.query(UserDrug).filter(UserDrug.user_id == user_id).all()
    return user_drugs

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
