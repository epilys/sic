from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.db.models import Value, BooleanField
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage
from django.contrib.auth.decorators import login_required
from ..models import Tag

def browse_tags(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("browse_tags"):
        return redirect(reverse("browse_tags"))
    tags = Tag.objects.order_by("-created", "name")
    paginator = Paginator(tags, 10)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num BooleanFieldis bigger than the actual number of pages
        return redirect(
            reverse(
                "browse_tags_page",
                kwargs={"page_num": paginator.num_pages},
            )
        )
    return render(
        request,
        "browse_tags.html",
        {"tags": page},
    )

