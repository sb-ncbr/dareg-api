## Builder image
FROM python:3.11-slim AS builder
WORKDIR /srv/dareg

# install python packages
COPY ./requirements.txt .
COPY dareg/onedata_api/libs/onedata_core dareg/onedata_api/libs/onedata_core ./libs/onedata_core/
RUN apt update && apt install -y git
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install -r requirements.txt \
    && pip install "oneprovider-client @ git+https://github.com/CERIT-SC/onedata-libs#subdirectory=oneprovider_client" \
    && pip install "onezone-client @ git+https://github.com/CERIT-SC/onedata-libs#subdirectory=onezone_client" \
    && pip install "onepanel-client @ git+https://github.com/CERIT-SC/onedata-libs#subdirectory=onepanel_client" \
    && pip install --target "/opt/venv/lib/python3.11/site-packages" ./libs/onedata_core

## Runtime image
FROM python:3.11-slim AS base
WORKDIR /srv/dareg
EXPOSE 8080

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
