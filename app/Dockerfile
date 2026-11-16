FROM python:3.12-slim 
LABEL org.opencontainers.image.source="https://github.com/ibtihal-mrn/Distrubuted_Systems_Project"
WORKDIR /app 
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ARG APP_VERSION=dev 
ENV APP_VERSION=$APP_VERSION
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]