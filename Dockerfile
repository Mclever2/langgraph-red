FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libgomp1 \
    ca-certificates \
    curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install torch CPU-only FIRST (saves ~1.8 GB vs full CUDA torch)
RUN pip install --no-cache-dir \
    "numpy<2" \
    torch==2.5.1+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Python dependencies (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download HuggingFace embedding model during build (baked into image).
# Stored at /root/.cache/huggingface/ — no network access needed at runtime.
RUN python -c "\
from langchain_huggingface import HuggingFaceEmbeddings; \
HuggingFaceEmbeddings(model_name='intfloat/multilingual-e5-small', model_kwargs={'device': 'cpu'})"

# Source code + chroma_db/biblioteca/ (pre-indexed books) + books/
# .dockerignore excludes: venv/, .env, __pycache__/, .git/, outputs/
COPY . .

# Outputs directory for exported JSON reports
RUN mkdir -p /app/outputs

# Prevent any HuggingFace network calls at runtime (model already baked in)
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1

ENV PORT=8080
# Evita que Streamlit corte WebSockets largos por inactividad (>120s)
ENV STREAMLIT_SERVER_MAX_UPLOAD_SIZE=200
ENV STREAMLIT_SERVER_ENABLE_WEBSOCKET_COMPRESSION=false
EXPOSE 8080

# Streamlit — front + back en un solo servicio
# enableCORS=false y enableXsrfProtection=false requeridos detrás del proxy de Cloud Run
CMD ["python", "-m", "streamlit", "run", "frontend/app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--server.maxUploadSize=200", \
     "--server.fileWatcherType=none"]
