FROM wearep3r/docker

ENV TERM=xterm-256color 

RUN mkdir /app /code

WORKDIR /app

RUN apt-get update && apt-get -y install --no-install-recommends curl git python3-pip -y \
    && pip3 install poetry

COPY poetry.lock pyproject.toml README.md CHANGELOG.md /app/

RUN poetry config virtualenvs.create false \
    && poetry install -n --no-root

COPY . /app/

RUN poetry install

COPY docker-entrypoint.sh /docker-entrypoint.sh

WORKDIR /code

ENTRYPOINT ["/docker-entrypoint.sh"]

CMD ["arco"]

ARG BUILD_DATE
ARG VCS_REF
ARG BUILD_VERSION

LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.build-date=$BUILD_DATE
LABEL org.label-schema.name="wearep3r/arco"
LABEL org.label-schema.description="get k3s running. fast."
LABEL org.label-schema.url="https://www.p3r.one/"
LABEL org.label-schema.vcs-url="https://github.com/wearep3r/arco"
LABEL org.label-schema.vcs-ref=$VCS_REF
LABEL org.label-schema.vcs-type="Git"
LABEL org.label-schema.vendor="wearep3r"
LABEL org.label-schema.version=$BUILD_VERSION
LABEL org.label-schema.docker.dockerfile="/Dockerfile"
