#!/bin/bash
#
# This script is run when the container starts.
#

# Django configuration
python3 /srv/dareg/manage.py collectstatic --noinput

# start web server
echo "Start web server..."
if [ -n "$PRODUCTION" ] && [ "$PRODUCTION" == "true" ]; then
    gunicorn --bind 0.0.0.0:80 dareg.wsgi
else
    python3 /srv/dareg/manage.py runserver 0.0.0.0:80
fi
