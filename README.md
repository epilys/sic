# sic

Setup:

```shell
cp sic/secret_settings.py{.template,}
vim sic/secret_settings.py # add secret token
python3 manage.py migrate #sets up database
sqlite3 sic.dib < sic.db-dummy_data.sql # OPTIONAL insert dummy data
python3 manage.py createsuperuser #selfexplanatory
python3 manage.py runserver # run at 127.0.0.1:8000
python3 manage.py runserver 8001 # run at 127.0.0.1:8001
python3 manage.py runserver 0.0.0.0:8000 # run at public-ip:8000
```

## Code style

Python code *should* follow [Black's style](https://github.com/psf/black).

HTML/CSS *must* pass [w3's validators](https://validator.w3.org/), and if they don't it's a `TODO`/bug. Unless of course the errors refer to newer standards that haven't been implemented in the validator yet.

Commit subjects *should* be written in imperative mood for consistency and clarity.

### Running validators / formatters

#### python, `black`

```shell
black sic/*py
```

### django templates, `djhml`

```shell
git add sic/templates/TEMPL.html # stage first
djhtml -i sic/templates/TEMPL.html # in-place formatting
git add -p sic/templates/TEMPL.html # selectively add formatting if acceptable
```

#### HTML, `vnu.jar`

```shell
vnu.jar "http://127.0.0.1:8002/"
```

Recursive check with [`tools/recursive_html_validate.py`](tools/recursive_html_validate.py):

```shell
python3 tools/recursive_html_validate.py "127.0.0.1:8002" # no login
python3 tools/recursive_html_validate.py --login --username superuser@website.tld --password "password" "127.0.0.1:8002"
```

```
usage: recursive_html_validate.py [-h] [--login] [--check-xml]
                                  [--vnu-jar-bin VNU_JAR_BIN] [-u USERNAME]
                                  [-p PASSWORD]
                                  url

positional arguments:
  url

optional arguments:
  -h, --help            show this help message and exit
  --login               login before scraping? (html and valid endpoints are
                        different when authenticated
  --check-xml           also check XML (feeds)
  --vnu-jar-bin VNU_JAR_BIN
  -u USERNAME, --username USERNAME
  -p PASSWORD, --password PASSWORD
```

#### Broken links, `checklink`

```shell
checklink --broken --quiet --indicator --summary --recursive --location "http://127.0.0.1:8000" "http://127.0.0.1:8000/"
```

#### CSS, `css-validator.jar`

```shell
css-validator.jar "http://127.0.0.1:8002/static/style.css"
```
