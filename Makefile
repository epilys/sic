pylint:
	git ls-files | grep '\.py$$' | grep -v migrations | grep -v '^setup.py$$'| grep -v '^manage.py$$' | xargs pylint -E

black-check:
	git ls-files | grep '\.py$$' | grep -v migrations | grep -v '^setup.py$$'| grep -v '^manage.py$$' | xargs black --check --diff

black:
	git ls-files | grep '\.py$$' | grep -v migrations | grep -v '^setup.py$$'| grep -v '^manage.py$$' | xargs black
