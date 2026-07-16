FROM python:3.12-alpine

WORKDIR /app
COPY app.py ./
COPY radar ./radar
COPY public ./public

ENV DATA_DIR=/data
ENV PYTHONUNBUFFERED=1
VOLUME /data

EXPOSE 8400
CMD ["python", "app.py"]
