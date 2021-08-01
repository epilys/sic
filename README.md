# sic

Link aggregator community organised by tags in `python3`/`django3` + `sqlite3`.

Public instance at https://sic.pm and [Tor hidden service](http://sicpm3hp7dtrwhmf4qlelycqlvie6flqa5qnjnt3snok5xydvxhs4xyd.onion/).

Follow the `[sic]` bot on Mastodon: https://botsin.space/@sic

<table>
	<tbody>
		<tr>
			<td><kbd><img src="./screenshot-frontpage.png" alt="1" /></kbd></td>
			<td><kbd><img src="./screenshot-frontpage-mobile.png" alt="2" /></kbd></td>
		</tr>
		<tr>
			<th></th>
			<th></th>
		</tr>
	</tbody>
</table>

Setup:

```shell
cp sic/local/secret_settings.py{.template,}
vim sic/local/secret_settings.py # add secret token
vim sic/local/settings_local.py # OPTIONAL: local settings (SMTP etc)
python3 manage.py migrate #sets up database
sqlite3 sic.dib < sic.db-dummy_data.sql # OPTIONAL insert dummy data
python3 manage.py createsuperuser #selfexplanatory
python3 manage.py runserver # run at 127.0.0.1:8000
python3 manage.py runserver 8001 # run at 127.0.0.1:8001
python3 manage.py runserver 0.0.0.0:8000 # run at public-ip:8000
```

See [`DEPLOY.md`](DEPLOY.md) for deployment instructions.

## Code style

See [`CODE_STYLE.md`](CODE_STYLE.md).
