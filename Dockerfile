FROM alpine:3.4

ENV LANG C.UTF-8
ENV JAVA_HOME /usr/lib/jvm/java-1.8-openjdk/jre
ENV PATH $PATH:/usr/lib/jvm/java-1.8-openjdk/jre/bin:/usr/lib/jvm/java-1.8-openjdk/bin

RUN apk add --no-cache \
              build-base \
              bash \
              python \
              python-dev \
              py-pip \
              openjdk8-jre \
              openssh-client \
  && pip install --upgrade pip

COPY . /cellos/
RUN pip install -r /cellos/requirements.txt

WORKDIR /cellos
ENTRYPOINT ["/cellos/cell"]
