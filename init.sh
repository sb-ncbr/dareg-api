#!/bin/bash
#
# This script is run when the container starts.
#

# Django configuration
python3 /srv/dareg/manage.py collectstatic --noinput

# start web server
echo "Start web server..."
if [ -n "$PRODUCTION" ] && [ "$PRODUCTION" == "true" ]; then
    echo "Running in production mode";
    gunicorn --bind 0.0.0.0:8080 dareg.dareg.wsgi
else
    echo "Running in development mode";
    python3 /srv/dareg/manage.py runserver 0.0.0.0:8080
fi
