# DAREG backend

## Local build and run
 docker build --progress plain -f Dockerfile --build-arg COMMIT_HASH=hash --build-arg COMMIT_DATE=2023-10-25 -t registry.gitlab.ics.muni.cz:443/ceitec-cf-biodata/dareg:devel --push .

 docker run -d -p 80:80 --name dareg --rm registry.gitlab.ics.muni.cz:443/ceitec-cf-biodata/dareg:devel

## Getting started

These commands must be executed when you first run the application. 

 pyma makemigrations

 pyma migrate

 pyma createsuperuser
