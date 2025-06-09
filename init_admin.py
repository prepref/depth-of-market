import os
import uuid
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/market")

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)

def generate_api_key():
    return str(uuid.uuid4()).replace('-', '')[:32]

def init_admin():
    try:
        # Generate admin API key
        admin_api_key = generate_api_key()
        
        # SQL query to insert admin user
        insert_admin = text("""
            INSERT INTO users (name, api_key, role)
            VALUES ('Admin', :api_key, 'ADMIN')
            ON CONFLICT (api_key) DO NOTHING
            RETURNING id, api_key;
        """)
        
        with engine.connect() as conn:
            result = conn.execute(insert_admin, {"api_key": admin_api_key})
            conn.commit()
            
            # Get the inserted admin user
            admin = result.fetchone()
            
            if admin:
                print("\n=== Admin User Created Successfully ===")
                print(f"Admin ID: {admin[0]}")
                print(f"API Key: {admin[1]}")
                print("=====================================\n")
            else:
                print("\nAdmin user already exists or creation failed.\n")
                
    except Exception as e:
        print(f"Error creating admin user: {str(e)}")

if __name__ == "__main__":
    init_admin() 