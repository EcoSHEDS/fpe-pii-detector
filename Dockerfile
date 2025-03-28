FROM python:3.8-slim

RUN apt-get update && \
    apt-get install -y libgl1-mesa-glx libglib2.0-0 && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# initialize ultralytics
RUN python -c "from ultralytics import YOLO; YOLO()"

RUN mkdir -p /data
COPY model /app/model
COPY tests /app/tests
COPY data /app/data
COPY fpe_pii_detector /app/fpe_pii_detector

COPY entrypoint.py /app/entrypoint.py
RUN chmod +x /app/entrypoint.py

ENTRYPOINT ["/app/entrypoint.py"]
