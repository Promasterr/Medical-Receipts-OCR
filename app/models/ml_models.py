"""
ML Model initialization and management.
All models are loaded once at application startup.
"""
from ultralytics import YOLO
from paddleocr import LayoutDetection
from openai import OpenAI
from qrdet import QRDetector
from huggingface_hub import snapshot_download
from app.config import settings
import os


class ModelManager:
    """Singleton class to manage all ML models"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.layout_model = None
            self.barcode_model = None
            self.qr_detector = None
            self.vllm_client = None
            self._initialized = True
    
    def initialize_layout_model(self):
        """Initialize PP-DocLayoutV2 model on GPU"""
        if self.layout_model is None:
            self.layout_model = LayoutDetection(model_name="PP-DocLayoutV2", device="gpu")
            print("✓ PP-DocLayoutV2 loaded successfully on GPU")
        return self.layout_model
    
    def initialize_barcode_model(self):
        """Initialize YOLO barcode detection model"""
        if self.barcode_model is None:
            repo_dir = "YOLOV8s-Barcode-Detection"
            
            # Download model if not exists
            if not os.path.exists(repo_dir):
                print("Downloading barcode detection model...")
                snapshot_download(
                    repo_id="Piero2411/YOLOV8s-Barcode-Detection",
                    local_dir=repo_dir,
                    local_dir_use_symlinks=False
                )
                print("✓ Model download completed")
            
            self.barcode_model = YOLO(settings.BARCODE_MODEL_PATH)
            print("✓ YOLO barcode model loaded successfully")
        return self.barcode_model
    
    def initialize_qr_detector(self):
        """Initialize QR code detector"""
        if self.qr_detector is None:
            self.qr_detector = QRDetector(model_size='n')
            print("✓ QR detector initialized")
        return self.qr_detector
    
    def initialize_vllm_client(self):
        """Initialize OpenAI client for vLLM (Synchronous)"""
        if self.vllm_client is None:
            self.vllm_client = OpenAI(
                base_url=settings.VLLM_API_URL,
                api_key="EMPTY"  # vLLM uses dummy key
            )
            print(f"✓ vLLM client initialized (sync): {settings.VLLM_API_URL}")
        return self.vllm_client
    
    def initialize_all(self):
        """Initialize all models at startup"""
        print("Initializing models...")
        self.initialize_layout_model()
        self.initialize_barcode_model()
        self.initialize_qr_detector()
        self.initialize_vllm_client()
        print("✓ All models initialized successfully")


# Global model manager instance
model_manager = ModelManager()
