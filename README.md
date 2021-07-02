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

## Code style

Python code *should* follow [Black's style](https://github.com/psf/black).

HTML/CSS *must* pass [w3's validators](https://validator.w3.org/), and if they don't it's a `TODO`/bug. Unless of course the errors refer to newer standards that haven't been implemented in the validator yet.

Commit subjects *should* be written in imperative mood for consistency and clarity.
