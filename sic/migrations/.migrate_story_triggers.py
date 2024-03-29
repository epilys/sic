CREATE_TAGGREGATION_TAGS = """CREATE VIEW taggregation_tags AS WITH RECURSIVE w (
    taggregation_id,
    tag_id,
    depth,
    taggregationhastag_id
) AS (
    SELECT DISTINCT
        taggregation_id,
        tag_id,
        depth,
        id
    FROM
        sic_taggregationhastag
    UNION ALL
    SELECT
        w.taggregation_id AS taggregation_id,
        p.from_tag_id AS tag_id,
        (
            CASE w.depth
            WHEN NULL THEN
                w.depth
            ELSE
                w.depth - 1
            END),
        taggregationhastag_id
    FROM
        sic_tag_parents AS p
        JOIN w ON w.tag_id = p.to_tag_id
    WHERE
        (w.depth != 0 OR w.depth ISNULL)
        AND p.from_tag_id NOT IN (
            SELECT
                tag_id
            FROM
                taggregationhastag_exacttag)
) SELECT DISTINCT
    taggregation_id,
    tag_id,
    depth,
    taggregationhastag_id as has_id
FROM
    w;"""

CREATE_VIEW_TAGGREGATION_STORIES = """CREATE VIEW taggregation_stories AS SELECT DISTINCT
    s.id AS id,
    v.has_id AS has_id,
    v.taggregation_id AS taggregation_id
FROM
    sic_story AS s
    JOIN sic_story_tags AS t ON t.story_id = s.id
    JOIN taggregation_tags AS v ON v.tag_id = t.tag_id
WHERE
    NOT EXISTS (
        SELECT
            1
        FROM
            domainfilter AS df
        WHERE
            df.has_id = v.has_id
            AND ((df.match_string = s.domain_id AND NOT df.is_regexp)))
    AND NOT EXISTS (
        SELECT
            1
        FROM
            domainfilter AS df
        WHERE
            df.has_id = v.has_id
            AND ((REGEXP (df.match_string, s.domain_id) AND df.is_regexp)))
    AND NOT EXISTS (
        SELECT
            1
        FROM
            userfilter AS uf
        WHERE
            uf.has_id = v.has_id
            AND uf.user_id = s.user_id);"""

CREATE_UPDATE_LAST_MODIFIED_STORY_ON_INSERT_VOTE = """CREATE TRIGGER update_last_modified_story_on_insert_vote AFTER INSERT ON sic_vote FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = NEW.created
WHERE
    id = NEW.story_id;
END;"""

CREATE_UPDATE_LAST_MODIFIED_STORY_ON_UPDATE_VOTE = """CREATE TRIGGER update_last_modified_story_on_update_vote AFTER UPDATE ON sic_vote FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = strftime('%Y-%m-%d %H:%M:%f000', 'now')
WHERE
    id = NEW.story_id;
END;"""

CREATE_UPDATE_LAST_MODIFIED_STORY_ON_DELETE_VOTE = """CREATE TRIGGER update_last_modified_story_on_delete_vote AFTER DELETE ON sic_vote FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = strftime ('%Y-%m-%d %H:%M:%f000', 'now')
WHERE
    id = OLD.story_id;
END;"""

CREATE_TAGGREGATION_LAST_ACTIVE = """CREATE VIEW taggregation_last_active AS
SELECT
    MAX(s.last_active) AS last_active,
    t.taggregation_id AS taggregation_id
FROM
    sic_story AS s
    JOIN taggregation_stories AS t ON t.id = s.id
GROUP BY
    t.taggregation_id;"""

CREATE_INSERT = """CREATE TRIGGER sic_vote_insert AFTER INSERT ON sic_vote
                    FOR EACH ROW WHEN NEW.comment_id IS NULL
                    BEGIN
                    UPDATE sic_story
                    SET karma = (karma + 1)
                    WHERE
                        id = NEW.story_id;
                        END;"""
CREATE_DELETE = """CREATE TRIGGER sic_vote_delete AFTER DELETE ON sic_vote
                    FOR EACH ROW WHEN OLD.comment_id IS NULL
                    BEGIN
                    UPDATE sic_story
                    SET karma = (karma - 1)
                    WHERE
                        id = OLD.story_id;
                        END;"""
CREATE_INSERT_COMMENT = """CREATE TRIGGER sic_vote_insert_comment AFTER INSERT ON sic_vote
                    FOR EACH ROW WHEN NEW.comment_id IS NOT NULL
                    BEGIN
                    UPDATE sic_comment
                    SET karma = (karma + 1)
                    WHERE
                        id = NEW.comment_id;
                        END;"""

CREATE_DELETE_COMMENT = """CREATE TRIGGER sic_vote_delete_comment AFTER DELETE ON sic_vote
                    FOR EACH ROW WHEN OLD.comment_id IS NOT NULL
                    BEGIN
                    UPDATE sic_comment
                    SET karma = (karma - 1)
                    WHERE
                        id = OLD.comment_id;
                        END;"""

DROP_INSERT = """DROP TRIGGER sic_vote_insert;"""
DROP_DELETE = """DROP TRIGGER sic_vote_delete;"""
DROP_INSERT_COMMENT = """DROP TRIGGER sic_vote_insert_comment;"""
DROP_DELETE_COMMENT = """DROP TRIGGER sic_vote_delete_comment;"""

DROP_TAGGREGATION_TAGS = """DROP VIEW taggregation_tags;"""
DROP_VIEW_TAGGREGATION_STORIES = """DROP VIEW taggregation_stories;"""
DROP_UPDATE_LAST_MODIFIED_STORY_ON_INSERT_VOTE = (
    """DROP TRIGGER update_last_modified_story_on_insert_vote;"""
)
DROP_UPDATE_LAST_MODIFIED_STORY_ON_UPDATE_VOTE = (
    """DROP TRIGGER update_last_modified_story_on_update_vote;"""
)
DROP_UPDATE_LAST_MODIFIED_STORY_ON_DELETE_VOTE = (
    """DROP TRIGGER update_last_modified_story_on_delete_vote;"""
)
DROP_TAGGREGATION_LAST_ACTIVE = """DROP VIEW taggregation_last_active;"""

DROPS = [
    DROP_INSERT,
    DROP_DELETE,
    DROP_INSERT_COMMENT,
    DROP_DELETE_COMMENT,
    DROP_TAGGREGATION_TAGS,
    DROP_VIEW_TAGGREGATION_STORIES,
    DROP_UPDATE_LAST_MODIFIED_STORY_ON_INSERT_VOTE,
    DROP_UPDATE_LAST_MODIFIED_STORY_ON_UPDATE_VOTE,
    DROP_UPDATE_LAST_MODIFIED_STORY_ON_DELETE_VOTE,
    DROP_TAGGREGATION_LAST_ACTIVE,
]
CREATES = [
    CREATE_INSERT,
    CREATE_DELETE,
    CREATE_INSERT_COMMENT,
    CREATE_DELETE_COMMENT,
    CREATE_TAGGREGATION_TAGS,
    CREATE_VIEW_TAGGREGATION_STORIES,
    CREATE_UPDATE_LAST_MODIFIED_STORY_ON_INSERT_VOTE,
    CREATE_UPDATE_LAST_MODIFIED_STORY_ON_UPDATE_VOTE,
    CREATE_UPDATE_LAST_MODIFIED_STORY_ON_DELETE_VOTE,
    CREATE_TAGGREGATION_LAST_ACTIVE,
]

if len(DROPS) != len(CREATES):
    raise Exception("Mismatched CREATEs and DROPs")
