FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

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
EXPOSE 8080

# Streamlit — front + back en un solo servicio
CMD ["python", "-m", "streamlit", "run", "frontend/app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
