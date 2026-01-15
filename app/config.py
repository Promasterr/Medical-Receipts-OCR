"""
Configuration management using Pydantic settings.
All environment variables are loaded from .env file.
"""
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # API Keys
    OPENAI_API_KEY: str = "sk-not-required"
    VLLM_API_URL: str = "http://127.0.0.1:8000/v1"
    VLLM_MODEL_NAME: str = "nanonets/Nanonets-OCR2-3B"
    
    # Authentication
    JWT_SECRET_KEY: str = "your-secret-key-here-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60
    
    # CORS
    CORS_ORIGINS: str = '["*"]'
    
    # Application
    APP_TITLE: str = "Document Batch Processor"
    APP_VERSION: str = "2.0.0"
    
    # Models
    BARCODE_MODEL_PATH: str = "YOLOV8s-Barcode-Detection/YOLOV8s_Barcode_Detection.pt"

    # Redis & Task Queue
    REDIS_URL: str = "redis://localhost:6379/0"
    TASK_RESULT_EXPIRE_TIME: int = 72 * 3600  # 72 hours

    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string"""
        try:
            return json.loads(self.CORS_ORIGINS)
        except:
            return ["*"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
