import collections
from datetime import datetime, timedelta
from django.utils.timezone import make_aware


HOTNESS_WINDOW = 60 * 60 * 22


def story_hotness(story):
    user = story.user
    domain_penalty = 0.0
    tag_hotness = sum(map(lambda t: t.hotness_modifier(), story.tags.all()))
    score = float(story.karma()) + tag_hotness - domain_penalty
    if story.user_is_author and story.url is not None:
        score += 0.25
    comment_score_modifier = 0
    for c in story.comments.all():
        if c.user == user:
            continue
        score += 0.25 * c.karma()
        comment_score_modifier += 0.25 * c.karma()
    now = make_aware(datetime.utcnow())
    age = now - story.created
    age = timedelta(days=age.days, seconds=age.seconds)
    time_window_penalty = -round(float(age.total_seconds()) / HOTNESS_WINDOW, 3)
    score += time_window_penalty
    return {
        "score": score,
        "time_window_penalty": time_window_penalty,
        "age": age,
        "comment_score_modifier": comment_score_modifier,
        "tag_hotness": tag_hotness,
        "domain_penalty": domain_penalty,
    }
