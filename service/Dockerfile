FROM python:3.11-slim

WORKDIR /srv

# Dependencies first, so a code change does not re-install them.
COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service/ ./service/
COPY contract/ ./contract/

EXPOSE 8000
CMD ["uvicorn", "service.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
