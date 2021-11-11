import io
import re
import types
from datetime import datetime, timedelta

from itertools import cycle, chain

import matplotlib
from matplotlib import rcParams
from matplotlib.figure import Figure
from mpl_toolkits.axisartist.axislines import Subplot
import numpy as np

from django.utils.timezone import make_aware
from django.http import HttpResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_safe
from django.core.cache import cache
from django.db import connection

from sic.jobs import Job, JobKind

rcParams["svg.fonttype"] = "none"

CACHE_TIMEOUT = 60 * 60 * 12

UNAVAILABLE_SVG = """<svg id="svg" viewBox="0 0 240 80" xmlns="http://www.w3.org/2000/svg">
  <text x="20" y="35">data unavailable</text>
</svg>"""


def make_posts_svg(data):
    fig = Figure()

    ax = Subplot(fig, 111)
    fig.add_subplot(ax)

    def x_ticks(labels):
        for (p, l) in zip(cycle([True, False, False, False]), labels):
            if p:
                yield l
            else:
                continue

    ax.axis["right"].set_visible(False)
    ax.axis["left"].set_visible(False)
    ax.axis["top"].set_visible(False)
    ax.set_ylim(ymin=0, ymax=max(data["count"]) + 1)
    fig.subplots_adjust(left=0.0, right=1.0, top=0.9, bottom=0.1)
    ax.plot(data["label"], data["count"], color="black", marker="o", markersize=4)
    ax.set_xticks(list(x_ticks(data["label"])))

    label_history = set()
    for x, y in zip(data["label"], data["count"]):

        label = y
        if label in label_history:
            continue
        label_history.add(label)

        ax.annotate(
            label,  # this is the text
            (x, y),  # these are the coordinates to position the label
            textcoords="offset points",  # how to position the text
            xytext=(0, 10),  # distance from text to points (x,y)
            ha="center",
        )  # horizontal alignment can be left, right or center

    svg = io.BytesIO()
    fig.savefig(svg, format="svg")
    return svg.getvalue().decode(encoding="UTF-8").strip()


def daily_posts_svg_job(job):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT
    COUNT(id) AS count,
    strftime ("%Y-%m-%d", created) AS label
FROM
    sic_story
GROUP BY
    label
    ORDER BY
        label;"""
        )
        posts = cursor.fetchall()
    data = {
        "count": [x[0] for x in posts],
        "label": [x[1] for x in posts],
    }
    job.data = data
    job.save()
    cache.set(
        "daily_posts", list(zip(data["label"], data["count"])), timeout=CACHE_TIMEOUT
    )
    if not posts:
        svg = UNAVAILABLE_SVG
    else:
        svg = make_posts_svg(data)
        svg = re.sub(
            r"""<svg """,
            """<svg id="svg" """,
            svg,
            count=1,
        )
    return svg


def registrations_svg_job(job):
    with connection.cursor() as cursor:
        cursor.execute(
            """CREATE TEMPORARY VIEW IF NOT EXISTS month_labels AS WITH RECURSIVE cte (
    label,
    month,
    date,
    offset
) AS (
    SELECT
        '2021-07' AS label,
        8 AS month,
        '2021-08-01' AS date,
        0 AS offset
    UNION ALL
    SELECT
        strftime ('%Y-%m',
            cte.date) AS label,
        (
            CASE WHEN cte.month < 12 THEN
                (cte.month + 1)
            ELSE
                1
            END) AS month,
        (
            CASE WHEN cte.month < 12 THEN
                (strftime ('%Y-',
                        cte.date) || printf ("%02d-01",
                        cte.month + 1))
            ELSE
                ((strftime ('%Y',
                            cte.date) + 1) || '-01-01')
            END) AS date,
        cte.offset + 1 AS offset
    FROM
        cte
    WHERE
        date(cte.date, 'start of month') < date('now', 'start of month')
)
SELECT
    label, month, date, offset
FROM
    cte;""",
            [],
        )

        cursor.execute(
            """SELECT
    COUNT(id) AS count,
    strftime ("%Y-%m", created) AS label
FROM
    sic_user
GROUP BY
    label
UNION ALL
SELECT
    0 AS count,
    label
FROM
    month_labels
WHERE
    label NOT IN (SELECT DISTINCT
            strftime ("%Y-%m", created)
        FROM
            sic_user)
    ORDER BY
        label;
""",
            [],
        )
        registrations = cursor.fetchall()
    data = {
        "count": [x[0] for x in registrations],
        "label": [x[1] for x in registrations],
    }
    job.data = data
    job.save()
    cache.set(
        "registrations", list(zip(data["label"], data["count"])), timeout=CACHE_TIMEOUT
    )
    if not registrations:
        svg = UNAVAILABLE_SVG
    else:
        svg = make_registrations_svg(data)
        svg = re.sub(
            r"""<svg """,
            """<svg id="svg" """,
            svg,
            count=1,
        )
        cache.set("registrations_svg", svg, timeout=CACHE_TIMEOUT)
    return svg


def make_registrations_svg(data):
    fig = Figure()

    ax = Subplot(fig, 111)
    fig.add_subplot(ax)

    ax.axis["right"].set_visible(False)
    ax.axis["left"].set_visible(False)
    ax.axis["top"].set_visible(False)
    ax.set_ylim(ymin=0, ymax=max(data["count"]) + 1)
    fig.subplots_adjust(left=0.0, right=1.0, top=0.9, bottom=0.1)
    ax.plot(data["label"], data["count"], color="black", marker="o", markersize=4)
    ax.set_xticks(list(data["label"]))

    label_history = set()
    for x, y in zip(data["label"], data["count"]):

        label = y
        if label in label_history:
            continue
        label_history.add(label)

        ax.annotate(
            label,  # this is the text
            (x, y),  # these are the coordinates to position the label
            textcoords="offset points",  # how to position the text
            xytext=(0, 10),  # distance from text to points (x,y)
            ha="center",
        )  # horizontal alignment can be left, right or center

    svg = io.BytesIO()
    fig.savefig(svg, format="svg")
    return svg.getvalue().decode(encoding="UTF-8").strip()


def make_total_graph_igraph_svg(edges):
    import igraph

    g = igraph.Graph()
    tags = set(chain.from_iterable(edges))
    vertices = {y: x for x, y in enumerate(tags)}
    g.add_vertices(len(vertices))
    for (l, r) in edges:
        g.add_edges([(vertices[l], vertices[r])])

    layout = g.layout_kamada_kawai()
    fig = Figure()
    ax = Subplot(fig, 111)
    fig.add_subplot(ax)
    ax.axis["right"].set_visible(False)
    ax.axis["left"].set_visible(False)
    ax.axis["top"].set_visible(False)
    ax.axis["bottom"].set_visible(False)

    igraph.plot(
        g,
        target=ax,
        layout=layout,
        vertex_color=["black" for _ in g.vs],
        edge_width=0.7,
        vertex_size=3,
        bbox=(0, 0, 100, 100),
        margin=[0, 0, 0, 0],
    )  # , vertex_label=g.vs["name"])
    ax.axis("off")
    svg = io.BytesIO()
    fig.savefig(svg, format="svg", bbox_inches="tight", pad_inches=0.2)
    return svg.getvalue().decode(encoding="UTF-8").strip()


def make_total_graph_svg(edges):
    try:
        import igraph

        return make_total_graph_igraph_svg(edges)
    except ImportError:
        pass
    import graphviz

    dot = graphviz.Digraph(
        format="svg",
        graph_attr={
            "ratio": "compress",
        },
        node_attr={
            "shape": "point",
        },
    )
    nodes = set()
    for edge in edges:
        nodes.add(edge[0])
        nodes.add(edge[1])
    for n in nodes:
        dot.node(str(n))
    for edge in edges:
        dot.edge(str(edge[0]), str(edge[1]), arrowhead="none")
    return dot.pipe().decode("utf-8")


def total_graph_svg_job(job):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT
    from_tag_id,
    to_tag_id
FROM
    sic_tag_parents;"""
        )
        edges = cursor.fetchall()
    if not edges:
        svg = UNAVAILABLE_SVG
    else:
        svg = make_total_graph_svg(edges)
        svg = re.sub(
            r"""<svg """,
            """<svg id="svg" """,
            svg,
            count=1,
        )
        cache.set("total_graph_svg", svg, timeout=CACHE_TIMEOUT)
    return svg


def make_upvote_ratio_svg(ratios):
    labels = []
    data = []
    for k in ratios:
        labels.append(k)
        data.append(ratios[k])
    data = np.array(data)
    data_cum = data.cumsum(axis=1)

    fig = Figure()

    ax = Subplot(fig, 111)
    ax.invert_yaxis()
    ax.xaxis.set_visible(False)
    ax.axis["right"].set_visible(False)
    ax.axis["top"].set_visible(False)
    fig.add_subplot(ax)
    ax.set_xlim(0, np.sum(data, axis=1).max())
    fig.subplots_adjust(left=0.0, right=1.0, top=0.9, bottom=0.1)
    for i, (hatch, colname) in enumerate([("ooooo", "upvotes"), (None, "comments")]):
        widths = data[:, i]
        starts = data_cum[:, i] - widths
        _rects = ax.barh(
            labels,
            widths,
            left=starts,
            height=0.5,
            fill=False,
            hatch=hatch,
            label=colname,
        )
        _xcenters = starts + widths / 2

        # text_color = 'darkgrey'
        # for y, (x, c) in enumerate(zip(xcenters, widths)):
        #    ax.text(x, y, str(int(c)), ha='center', va='center',
        #            color=text_color)

    def x_ticks(labels):
        for (p, l) in zip(cycle([True, False, False, False]), labels):
            if p:
                yield l
            else:
                yield ""

    ax.set_yticklabels(list(x_ticks(labels)))
    ax.legend(ncol=2, bbox_to_anchor=(0, 1), loc="lower left", fontsize="small")
    svg = io.BytesIO()
    fig.savefig(svg, format="svg")
    return svg.getvalue().decode(encoding="UTF-8").strip()


def upvote_ratio_svg_job(job):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT
    COUNT(id) AS count,
    strftime ("%Y-%m-%d", created) AS day
FROM
    sic_vote
GROUP BY
    day
    ORDER BY
        day;"""
        )
        votes = list(cursor.fetchall())
        cursor.execute(
            """SELECT
    COUNT(id) AS count,
    strftime ("%Y-%m-%d", created) AS day
FROM
    sic_comment
GROUP BY
    day
    ORDER BY
        day;"""
        )
        comments = list(cursor.fetchall())
    ratios = {}
    for v in votes:
        if v[1] in ratios:
            ratios[v[1]][0] = v[0]
        else:
            ratios[v[1]] = [v[0], 0]
    for c in comments:
        if c[1] in ratios:
            ratios[c[1]][1] = c[0]
        else:
            ratios[c[1]] = [0, c[0]]

    cache.set("upvote_ratio", ratios, timeout=CACHE_TIMEOUT)
    job.data = ratios
    job.save()
    if len(ratios) == 0:
        svg = UNAVAILABLE_SVG
    else:
        svg = make_upvote_ratio_svg(ratios)
        svg = re.sub(
            r"""<svg """,
            """<svg id="svg" """,
            svg,
            count=1,
        )
        cache.set("upvote_ratio_svg", svg, timeout=CACHE_TIMEOUT)
    return svg


def user_graph_svg_job(job):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT
    inviter_id,
    receiver_id
FROM
    sic_invitation WHERE receiver_id IS NOT NULL;"""
        )
        edges = cursor.fetchall()
    if not edges:
        svg = UNAVAILABLE_SVG
    else:
        svg = make_total_graph_svg(edges)
        svg = re.sub(
            r"""<svg """,
            """<svg id="svg" """,
            svg,
            count=1,
        )
        cache.set("user_graph_svg", svg, timeout=CACHE_TIMEOUT)
    return svg


def get_svg_or_schedule_job(job_name: str, func: types.FunctionType) -> str:
    svg_name = f"{job_name}_svg"
    svg = cache.get(svg_name, None)
    if svg is None:
        kind = JobKind.from_func(func)
        jobs = Job.objects.filter(
            kind=kind,
            created__gte=make_aware(datetime.now() - timedelta(seconds=CACHE_TIMEOUT)),
        )
        if jobs.exists():
            for job in jobs:
                if not job.failed and not job.active:
                    svg = job.logs
                    cache.set(svg_name, svg, timeout=CACHE_TIMEOUT)
                    cache.set(job_name, job.data, timeout=CACHE_TIMEOUT)
                else:
                    job.active = True
                    job.save(update_fields=["active"])
        else:
            _job_obj, _ = Job.objects.get_or_create(
                kind=kind, created=make_aware(datetime.now()), periodic=False
            )
    if not svg:
        kind = JobKind.from_func(func)
        job = Job.objects.filter(
            kind=kind,
            created__lte=make_aware(datetime.now()),
            failed=False,
            active=False,
        ).last()
        if job:
            svg = job.logs
            cache.set(svg_name, svg, timeout=30)
            cache.set(job_name, job.data, timeout=30)
    if not svg:
        svg = UNAVAILABLE_SVG
    return svg


@require_safe
def user_graph_svg(request):
    return HttpResponse(
        get_svg_or_schedule_job("user_graph", user_graph_svg_job),
        content_type="image/svg+xml",
    )


@require_safe
def daily_posts_svg(request):
    return HttpResponse(
        get_svg_or_schedule_job("daily_posts", daily_posts_svg_job),
        content_type="image/svg+xml",
    )


@require_safe
def upvote_ratio_svg(request):
    return HttpResponse(
        get_svg_or_schedule_job("upvote_ratio", upvote_ratio_svg_job),
        content_type="image/svg+xml",
    )


@require_safe
def registrations_svg(request):
    return HttpResponse(
        get_svg_or_schedule_job("registrations", registrations_svg_job),
        content_type="image/svg+xml",
    )


@require_safe
def total_graph_svg(request):
    return HttpResponse(
        get_svg_or_schedule_job("total_graph", total_graph_svg_job),
        content_type="image/svg+xml",
    )
