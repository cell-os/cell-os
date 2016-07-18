FROM alpine:3.4

COPY . /cellos/

RUN apk add --no-cache \
              build-base \
              bash \
              python \
              python-dev \
              py-pip \
  && pip install --upgrade pip \
  && pip install -r /cellos/requirements.txt

WORKDIR /cellos
ENTRYPOINT ["/cellos/cell"]
