FROM python:3.13-slim

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y ffmpeg bash

RUN pip install --upgrade pip && \
    pip install --upgrade build

RUN python -m venv .venv

COPY . .

RUN . ./.venv/bin/activate && pip install .

ENTRYPOINT [ "./.venv/bin/highlight-video-maker" ]