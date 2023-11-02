## Builder image
FROM python:3.11-slim AS builder
WORKDIR /srv/dareg

# install python packages
COPY ./requirements.txt .
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install -r requirements.txt

## Runtime image
FROM python:3.11-slim AS base
WORKDIR /srv/dareg
EXPOSE 80

# get python packages
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# copy files from repo
COPY ./init.sh /srv/
COPY dareg .

# prepare application
# create user web
RUN useradd -u 1000 -m web -s /bin/bash \
    && chown -R web .

# environment variables
ARG COMMIT_HASH="not_set"
ARG COMMIT_DATE="2000-01-01"
ENV COMMIT_HASH=${COMMIT_HASH}
ENV COMMIT_DATE=${COMMIT_DATE}

USER web

# user-specific
RUN echo "alias pyma='python3 manage.py'" >> ~/.bashrc
CMD [ "/bin/bash", "/srv/init.sh" ]
