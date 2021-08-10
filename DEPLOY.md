# How to deploy [sic]

## Basic setup

```shell
cp sic/local/secret_settings.py{.template,}
vim sic/local/secret_settings.py # add secret token
vim sic/local/settings_local.py # local settings (SMTP etc)
python3 manage.py migrate #sets up database
python3 manage.py createsuperuser #selfexplanatory
```

## Development

You can use django's development server:

```shell
python3 manage.py runserver # run at 127.0.0.1:8000
python3 manage.py runserver 8001 # run at 127.0.0.1:8001
python3 manage.py runserver 0.0.0.0:8000 # run at public-ip:8000
```

Any IPs you use with `runserver` must be in your `ALLOWED_HOSTS` settings.

## Production

Put local settings in `/local/` in `settings_local.py`. Optionally install `memcached` and `pymemcache`.

### `sic/local/settings_local.py`

```python
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "localhost"
EMAIL_PORT = 25
DEFAULT_FROM_EMAIL = "noreply@example.com"

DEBUG=False

ALLOWED_HOSTS = [ "127.0.0.1", "example.com", ] # you can add extra hosts too e.g. "example.onion"
ADMINS = [('user', 'webmaster@example.com'), ]

STATIC_ROOT = "/path/to/collected/static/"
```

### Static files

Issue `python3 manage.py collectstatic` to put all static files in your defined `STATIC_ROOT` folder.

### `apache2` and `modwsgi`

```text
<VirtualHost *:80>
  ServerName example.com
  ServerAdmin webmaster@example.com
  ErrorLog ${APACHE_LOG_DIR}/sic-error.log
  CustomLog ${APACHE_LOG_DIR}/sic-access.log combined
  RewriteEngine on
  RewriteCond %{SERVER_NAME} =example.com
  RewriteRule ^ https://%{SERVER_NAME}%{REQUEST_URI} [END,NE,R=permanent]
</VirtualHost>

<VirtualHost *:443>
  <Directorymatch "^/.*/\.git/">
    Order deny,allow
    Deny from all
  </Directorymatch>
  ServerAdmin webmaster@example.com
  ServerName example.com
  Alias /static /PATH/TO/static

  <Directory /PATH/TO/static>
    Require all granted
  </Directory>


  WSGIScriptAlias / /PATH/TO/sic/sic/wsgi.py
  WSGIDaemonProcess examplecom user=debian python-home=/PATH/TO/sic/venv python-path=/PATH/TO/sic processes=2 threads=3
  WSGIProcessGroup examplecom

  <Directory /PATH/TO/sic/sic>
    <Files wsgi.py>
    Require all granted
    </Files>
  </Directory>

    <IfModule mod_expires.c>
      # Activate mod
      ExpiresActive On
      <IfModule mod_headers.c>
        Header append Cache-Control "public"
      </IfModule>
      AddType application/font-sfnt            otf ttf
      AddType application/font-woff            woff
      AddType application/font-woff2           woff2

      ExpiresByType text/css "access plus 1 hour"
      ExpiresByType application/font-sfnt "access plus 1 month"
      ExpiresByType application/font-woff "access plus 1 month"
      ExpiresByType application/font-woff2 "access plus 1 month"
    </IfModule>

    LogLevel info

    ErrorLog ${APACHE_LOG_DIR}/sic-ssl-error.log
    CustomLog ${APACHE_LOG_DIR}/sic-ssl-access.log combined

    SSLCertificateFile /etc/letsencrypt/live/example.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/example.com/privkey.pem
    Include /etc/letsencrypt/options-ssl-apache.conf
    Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    <LocationMatch ^((?!(tags/graph-svg.*)).)*$>
    Header always set X-Frame-Options DENY
    </LocationMatch>
    Header always set X-Content-Type-Options nosniff

    <IfModule mod_headers.c>
      Header always set Strict-Transport-Security "max-age=15552000; includeSubDomains; preload"
    </IfModule>
</VirtualHost>
```

### `memcached`

Add the following to `settings_local.py`:

```
# Optional
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': '127.0.0.1:11211',
        'OPTIONS': {
            'no_delay': True,
            'ignore_exc': True,
            'max_pool_size': 4,
            'use_pooling': True,
        }
    }
}
```

Configure memcache systemd service to restart along with apache2:

```shell
systemctl edit memcached
```

And add:

```
[Unit]
PartOf=apache2.service
WantedBy=apache2.service
```
