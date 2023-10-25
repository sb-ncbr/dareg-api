# DAREG backend

## Local deployment

### Prepare container

Build the Docker image:
```
docker compose build
```

Run the app:
```
# run container with app in the background (detached mode)
docker compose up -d

# follow logs
docker compose logs -ft
```

It's running. Go to http://localhost in a web-browser.

### Setup application

These commands must be executed when you first run the application. 
```
# enter to the container with app
docker compose exec dareg bash

# update database model
pyma migrate

# create superuser
pyma createsuperuser
```

You can login with the new superuser credentials e.g. to Django admin interface (http://localhost/admin).
