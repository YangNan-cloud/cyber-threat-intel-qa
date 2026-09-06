"""Start the API with configuration from this folder's .env file."""
from app.config import HOST, PORT  # loads .env before app modules are imported
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
