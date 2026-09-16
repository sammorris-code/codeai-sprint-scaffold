FROM python:3.11-slim

WORKDIR /srv

# Dependencies first, so a code change does not re-install them.
COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service/ ./service/
COPY contract/ ./contract/

# The static site, served by the API at the same origin. Listed explicitly
# rather than copying the repository, so what becomes reachable over HTTP is
# something you can read off in one glance - and so service/.env can never
# arrive here by accident.
COPY index.html ./site/
COPY css/ ./site/css/
COPY tools/ ./site/tools/
COPY contract/ ./site/contract/

EXPOSE 8000
CMD ["uvicorn", "service.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
