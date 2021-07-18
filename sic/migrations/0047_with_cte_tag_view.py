from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sic", "0046_auto_20210718_0650"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                """CREATE TRIGGER cycle_check
BEFORE INSERT ON sic_tag_parents
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Cycle detected') WHERE EXISTS (
      WITH RECURSIVE w(parent, last_visited, already_visited, cycle) AS (
            SELECT DISTINCT to_tag_id AS parent, from_tag_id AS last_visited, to_tag_id AS already_visited, 0 AS cycle FROM sic_tag_parents

            UNION ALL

            SELECT t.to_tag_id AS parent, t.from_tag_id AS last_visited, already_visited || ', ' || t.to_tag_id, already_visited LIKE '%'||t.to_tag_id||"%" FROM sic_tag_parents AS t JOIN w ON w.last_visited = t.to_tag_id
            WHERE NOT cycle
      )
      SELECT already_visited, cycle FROM w WHERE last_visited = NEW.to_tag_id AND already_visited LIKE '%'||NEW.from_tag_id||'%'
    );
END;"""
            ],
            reverse_sql=["DROP TRIGGER IF EXISTS cycle_check;"],
        )
    ]
