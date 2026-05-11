FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
COPY bot/requirements.txt bot/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt \
    && if [ -f bot/requirements.txt ]; then pip install --no-cache-dir -r bot/requirements.txt; fi

COPY . .

ENTRYPOINT ["python", "monitor.py"]
CMD []
