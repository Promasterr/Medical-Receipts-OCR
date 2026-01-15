# OCR Document Processing Pipeline

Production-ready OCR pipeline for processing medical documents, invoices, and ID cards with Arabic text support.

## Features

- **Multi-format Support**: Handles PDF files with automatic page extraction
- **OCR Processing**: Async batch processing using vLLM API
- **Layout Detection**: PP-DocLayoutV2 for document structure  analysis
- **QR/Barcode**: Automatic detection and removal
- **Document Parsers**: Specialized parsers for different document types (Massara, Janzour, Invoice, ID Card)
- **Authentication**: JWT-based auth system (implemented but not enforced)
- **API Documentation**: Auto-generated OpenAPI/Swagger docs

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update values:

```bash
cp .env.example .env
```

Edit `.env` with your settings:
- `VLLM_API_URL`: Your vLLM server URL
- `JWT_SECRET_KEY`: Change to a secure random string
- Other API keys as needed

### 3. Run the Server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check
- `GET /api/health` - Service health status
- `GET /api/health/models` - Check if models are loaded

### Authentication
Authentication system is implemented in the codebase but **not currently exposed** as endpoints. The auth module (`app/auth/`) contains JWT token management, password hashing, and user models that can be enabled when needed.

### PDF Processing
- `POST /api/pdf/process` - Upload and process PDF (returns SSE stream)

### Documentation
- `GET /docs` - Interactive Swagger UI  
- `GET /redoc` - ReDoc documentation

## Project Structure

```
ocrproject/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Configuration management
│   ├── api/                 # API routes
│   │   └── routes/
│   │       ├── auth.py      # Authentication endpoints
│   │       ├── health.py    # Health check endpoints
│   │       └── pdf.py       # PDF processing endpoint
│   ├── auth/                # Authentication system
│   │   ├── jwt_handler.py   # JWT token management
│   │   ├── password_utils.py# Password hashing
│   │   └── models.py        # User models
│   ├── core/                # Core business logic
│   │   ├── ocr/            # OCR inference
│   │   ├── layout/         # Layout detection
│   │   ├── document/       # Document processing
│   │   └── parsers/        # Text/table parsers
│   ├── models/             # ML models & schemas
│   └── utils/              # Utility functions
├── main.py                  # Original monolithic file (backup)
├── requirements.txt
├── .env.example
└── README.md
```

## Development

### Adding New Document Types

1. Add prompt template in `app/core/ocr/prompts.py`
2. Add parser logic in `app/core/parsers/`
3. Update PDF processor to handle new type

### Testing

```bash
# Run tests (when implemented)
pytest tests/
```

## Notes

- **JWT Authentication**: Implemented but NOT enforced on endpoints yet
- **File Operations**: All image processing is in-memory (no file saving)
- **Original Code**: Preserved in `main.py` as backup reference

## Production Deployment

1. Set secure `JWT_SECRET_KEY` in `.env`
2. Configure proper CORS origins
3. Use production WSGI server (Gunicorn + Uvicorn workers)
4. Set up reverse proxy (Nginx)
5. Enable HTTPS

## License

[Your License Here]
