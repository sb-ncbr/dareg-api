# DAREG backend

## Local deployment

### Prepare container

Build the Docker image:
```
docker compose build
```

Run the app:
```
docker compose up
```

It's running. Go to http://localhost in a web-browser.

### Setup application

These commands must be executed when you first run the application. 
```
# update database model
pyma migrate

# create superuser
pyma createsuperuser
```

Now you can login with the new superuser credentials e.g. to Django admin interface (http://localhost/admin).
