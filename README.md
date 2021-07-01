# sic

Setup:

```shell
cp sic/secret_settings.py{.template,}
vim sic/secret_settings.py # add secret token
python3 manage.py migrate #sets up database
python3 manage.py createsuperuser #selfexplanatory
python3 manage.py runserver # run at 127.0.0.1:8000
python3 manage.py runserver 8001 # run at 127.0.0.1:8001
python3 manage.py runserver 0.0.0.0:8000 # run at public-ip:8000
```
