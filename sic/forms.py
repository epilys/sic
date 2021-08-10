import functools, operator
from django import forms
from django.core.exceptions import ValidationError
from .apps import SicAppConfig as config
from .models import Tag, User, StoryKind, StoryFilter, TaggregationHasTag


class SubmitStoryForm(forms.Form):
    required_css_class = "required"
    title = forms.CharField(
        label="Story title", required=False, max_length=200, min_length=2
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea({"rows": 5, "cols": 15, "placeholder": ""}),
        help_text="Write additional context for the submitted link, or your content if your post has no URL.",
    )
    url = forms.URLField(required=False)
    publish_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Set publication date if relevant (for example, an article not published within the last year).",
    )
    user_is_author = forms.BooleanField(
        label="Author",
        required=False,
        help_text="I am the author of the story at this URL (or this text)",
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        label="Topical tags",
        required=False,
        help_text="Hold down “Control”, or “Command” on a Mac, to select more than one.",
    )
    kind = forms.ModelMultipleChoiceField(
        queryset=StoryKind.objects.all(),
        label="Submission kind",
        required=True,
        help_text="Hold down “Control”, or “Command” on a Mac, to select more than one.",
    )
    context_warning = forms.CharField(
        required=False,
        max_length=30,
        help_text="Optionally add context warning for sensitive media",
    )


class SubmitCommentForm(forms.Form):
    text = forms.CharField(
        required=True, label="Comment", min_length=1, widget=forms.Textarea
    )
    text.widget.attrs.update({"rows": 6, "placeholder": ""})


class DeleteCommentForm(forms.Form):
    confirm_delete = forms.BooleanField(
        required=True,
        label="Really Delete this comment?",
        help_text="Check this box to permanently delete this comment.",
    )
    deletion_reason = forms.CharField(
        required=False,
        label="Public deletion reason",
        help_text="Describe the reason (that will be shown in the public log) for deleting this comment.",
    )


class EditReplyForm(forms.Form):
    text = forms.CharField(
        required=True, label="Edit", min_length=1, widget=forms.Textarea
    )
    text.widget.attrs.update({"rows": 6, "placeholder": ""})
    edit_reason = forms.CharField(
        required=False,
        label="Reason",
        help_text="Describe the reason (that will be shown in the public log) for editing this comment.",
    )


class EditAvatarForm(forms.Form):
    new_avatar = forms.FileField(
        required=False,
        label="Image file",
        help_text="leave blank to keep current image",
    )
    avatar_title = forms.CharField(
        required=False,
        label="Title",
        help_text="optional avatar attribution/description/title",
        max_length=500,
        widget=forms.Textarea,
    )
    avatar_title.widget.attrs.update({"rows": 2, "placeholder": "avatar title"})


class EditProfileForm(forms.Form):
    homepage = forms.URLField(required=False, label="homepage", max_length=500)
    git_repository = forms.URLField(
        required=False, label="git repository", max_length=500
    )
    about = forms.CharField(
        required=False, label="about", max_length=500, widget=forms.Textarea
    )
    about.widget.attrs.update({"rows": 3, "placeholder": ""})
    metadata_1_label = forms.CharField(
        required=False, label="Metadata 1 label", max_length=200
    )
    metadata_1 = forms.CharField(required=False, label="Metadata 1", max_length=200)
    metadata_2_label = forms.CharField(
        required=False, label="Metadata 2 label", max_length=200
    )
    metadata_2 = forms.CharField(required=False, label="Metadata 2", max_length=200)
    metadata_3_label = forms.CharField(
        required=False, label="Metadata 3 label", max_length=200
    )
    metadata_3 = forms.CharField(required=False, label="Metadata 3", max_length=200)
    metadata_4_label = forms.CharField(
        required=False, label="Metadata 4 label", max_length=200
    )
    metadata_4 = forms.CharField(required=False, label="Metadata 4", max_length=200)
    metadata_1_label.widget.attrs.update({"placeholder": "metadata 1 label"})
    metadata_1.widget.attrs.update({"placeholder": "metadata 1 value"})
    metadata_2_label.widget.attrs.update({"placeholder": "metadata 2 label"})
    metadata_2.widget.attrs.update({"placeholder": "metadata 2 value"})
    metadata_3_label.widget.attrs.update({"placeholder": "metadata 3 label"})
    metadata_3.widget.attrs.update({"placeholder": "metadata 3 value"})
    metadata_4_label.widget.attrs.update({"placeholder": "metadata 4 label"})
    metadata_4.widget.attrs.update({"placeholder": "metadata 4 value"})


class GenerateInviteForm(forms.Form):
    email = forms.EmailField(required=True, label="Account e-mail")


class UserCreationForm(forms.Form):
    username = forms.CharField(
        label="Enter Username",
        min_length=4,
        max_length=150,
        required=False,
        help_text="Leaving it blank will show your e-mail address to other users instead.",
    )
    email = forms.EmailField(label="Enter email")
    password1 = forms.CharField(label="Enter password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if not username or len(username) == 0:
            return username
        if username in config.BANNED_USERNAMES:
            raise ValidationError("Username not allowed")
        exists = User.objects.filter(username__iexact=username)
        if exists.count():
            raise ValidationError("Username already exists")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        exists = User.objects.filter(email__iexact=email)
        if exists.count():
            raise ValidationError("Email already exists")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("Password don't match")

        return password2

    def save(self, commit=True):
        user = User.objects.create_user(
            self.cleaned_data["email"], self.cleaned_data["password1"]
        )
        username = self.cleaned_data["username"]
        if username and len(username) > 0:
            user.username = username
            user.save()
        return user


class AnnotationForm(forms.Form):
    text = forms.CharField(
        required=True, label="Annotation", max_length=500, widget=forms.Textarea
    )
    text.widget.attrs.update({"rows": 3, "placeholder": ""})


class ParentsSelect(forms.SelectMultiple):
    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        try:
            disabled = value.instance._disabled
            if disabled:
                option["attrs"]["disabled"] = "disabled"
        except AttributeError:
            pass
        return option


class EditTagForm(forms.Form):
    pk = forms.ModelChoiceField(
        queryset=Tag.objects.all(),
        widget=forms.HiddenInput,
        required=False,
        initial=None,
    )
    name = forms.CharField(required=True, label="Name", max_length=40)
    hex_color = forms.CharField(
        max_length=7,
        required=False,
        initial="#ffffff",
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    parents = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        widget=ParentsSelect(attrs={"size": "10"}),
        label="parents",
        required=False,
        help_text="Hold down “Control”, or “Command” on a Mac, to select more than one.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        edited_tag = None
        try:
            edited_tag = kwargs["initial"]["pk"]
        except:
            pass
        into = lambda t: forms.models.ModelChoiceIteratorValue(t.pk, t)
        if edited_tag is not None:
            parents = []
            others = []
            for t in Tag.objects.all().prefetch_related("children"):
                if edited_tag in t.children.all():
                    parents.append((into(t), t.name))
                else:
                    if t.pk == edited_tag.pk:
                        t._disabled = True
                    others.append((into(t), t.name))
            self.fields["parents"].choices = (("current", parents), ("others", others))
        else:
            self.fields["parents"].choices = [
                (into(t), t.name) for t in Tag.objects.all()
            ]


class EditTaggregationForm(forms.Form):
    name = forms.CharField(required=True, label="Name", max_length=40)
    description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 8, "placeholder": ""})
    )

    discoverable = forms.BooleanField(
        label="Is discoverable",
        required=False,
        help_text="Will be shown in public lists.",
    )
    private = forms.BooleanField(
        label="Is private",
        required=False,
        help_text="Will only be visible to users with access.",
    )
    subscribed = forms.BooleanField(required=False)


class EditTaggregationHasTagForm(forms.Form):
    tag = forms.ModelChoiceField(
        queryset=Tag.objects.all(),
        label="tag",
        required=True,
    )
    depth = forms.IntegerField(
        min_value=0, initial=0, required=False, help_text="leave empty for no depth."
    )
    exclude_filters = forms.ModelMultipleChoiceField(
        queryset=StoryFilter.objects.all(),
        label="exclude filters",
        required=False,
        help_text="Hold down “Control”, or “Command” on a Mac, to select more than one.",
    )


class DeleteTaggregationHasTagForm(forms.Form):
    pk = forms.ModelChoiceField(
        queryset=TaggregationHasTag.objects.all(),
        widget=forms.HiddenInput,
        required=True,
    )
    confirm_delete = forms.BooleanField(
        required=True,
        initial=None,
        label="Really Delete this filter?",
        help_text="Check this box to permanently delete this filter.",
    )


class EditAccountSettings(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        widget=forms.HiddenInput,
        required=True,
    )
    username = forms.CharField(
        label="username",
        min_length=4,
        max_length=150,
        required=False,
        help_text="Leaving it blank will show your e-mail address to other users instead.",
    )
    email = forms.EmailField(
        required=True,
        label="account e-mail address",
    )
    email_notifications = forms.BooleanField(initial=True, required=False)
    email_replies = forms.BooleanField(initial=True, required=False)
    email_messages = forms.BooleanField(initial=True, required=False)
    email_mentions = forms.BooleanField(initial=True, required=False)
    show_avatars = forms.BooleanField(initial=True, required=False)
    show_story_previews = forms.BooleanField(initial=True, required=False)
    show_submitted_story_threads = forms.BooleanField(initial=True, required=False)
    show_stories_with_context_warning = forms.BooleanField(initial=True, required=False)
    show_colors = forms.BooleanField(
        initial=True,
        help_text="If false, UI and tag colors are not shown, and if avatars are displayed, they are in monochrome.",
        required=False,
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if not username or len(username) == 0:
            return username
        if username in config.BANNED_USERNAMES:
            raise ValidationError("Username not allowed")
        exists = User.objects.filter(username__iexact=username).exclude(
            pk=self.cleaned_data["user"].pk
        )
        if exists.count():
            raise ValidationError("Username already exists")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        exists = User.objects.filter(email__iexact=email).exclude(
            pk=self.cleaned_data["user"].pk
        )
        if exists.count():
            raise ValidationError("Email already exists")
        return email


class WeeklyDigestForm(forms.Form):
    active = forms.BooleanField(
        required=False,
    )
    all_stories = forms.BooleanField(
        required=False,
        help_text="If false, only stories from subscribed aggregations will be considered for the digest.",
    )
    last_run = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="The last time a digest was sent. Clear to receive it again, or set to other date to change what stories you will receive in your next digest.",
    )
    on_monday = forms.BooleanField(
        required=False,
    )
    on_tuesday = forms.BooleanField(
        required=False,
    )
    on_wednesday = forms.BooleanField(
        required=False,
    )
    on_thursday = forms.BooleanField(
        required=False,
    )
    on_friday = forms.BooleanField(
        required=False,
    )
    on_saturday = forms.BooleanField(
        required=False,
    )
    on_sunday = forms.BooleanField(
        required=False,
    )

    def calculate_on_days(self):
        if not self.is_valid():
            return None
        return functools.reduce(
            operator.__or__,
            map(
                lambda t: (1 if self.cleaned_data[t[1]] else 0) << t[0],
                enumerate(
                    [
                        "on_monday",
                        "on_tuesday",
                        "on_wednesday",
                        "on_thursday",
                        "on_friday",
                        "on_saturday",
                        "on_sunday",
                    ]
                ),
            ),
        )


class EditSessionSettings(forms.Form):
    vivid_colors = forms.BooleanField(
        initial=True,
        help_text="If false, UI, tag and image colors are made less vivid.",
        required=False,
    )
    font_size = forms.TypedChoiceField(
        required=False,
        label="Font size factor",
        coerce=lambda c: int(c),
        choices=[
            ("100", "100%"),
            ("115", "115%"),
            ("125", "125%"),
            ("135", "135%"),
        ],
        initial=100,
        help_text="""<span style="font-size: 1rem;">100%</span>
        <span style="font-size: 1.15rem;">115%</span>
        <span style="font-size: 1.25rem;">125%</span>
        <span style="font-size: 1.35rem;">135%</span>""",
    )


class EditHatForm(forms.Form):
    name = forms.CharField(
        required=True,
        label="Name",
        max_length=100,
    )
    hex_color = forms.CharField(
        max_length=7,
        required=False,
        initial="#000000",
        widget=forms.TextInput(attrs={"type": "color"}),
    )


class SearchCommentsForm(forms.Form):
    text = forms.CharField(required=True, label="full text query", max_length=500)
    search_in = forms.ChoiceField(
        required=True,
        label="search in",
        choices=[("comments", "comments"), ("stories", "stories"), ("both", "both")],
        initial="both",
        widget=forms.RadioSelect,
    )
    order_by = forms.ChoiceField(
        required=True,
        label="order by",
        choices=[
            ("newest", "newest"),
            ("karma", "karma"),
            ("relevance", "relevance"),
        ],
        initial="relevance",
    )
    ordering = forms.TypedChoiceField(
        required=True,
        label="",
        coerce=lambda c: c == "asc",
        choices=[("asc", "ascending"), ("desc", "descending")],
        initial="desc",
    )


def validate_user(value):
    try:
        user = User.objects.get(username=value)
    except User.DoesNotExist:
        raise ValidationError(f"User {value} not found.")


class ComposeMessageForm(forms.Form):
    recipient = forms.CharField(
        required=True, label="recipient", validators=[validate_user]
    )
    subject = forms.CharField(required=True, label="subject", max_length=100)
    body = forms.CharField(
        required=True, label="Message", widget=forms.Textarea, min_length=1
    )
    body.widget.attrs.update({"rows": 8, "placeholder": ""})

    def clean_recipient(self):
        value = self.cleaned_data["recipient"]
        try:
            recipient = User.objects.get(username=value)
            return recipient
        except User.DoesNotExist:
            raise ValidationError(f"User {value} not found.")


class OrderByForm(forms.Form):
    order_by = forms.ChoiceField(required=True, label="order by")
    ordering = forms.TypedChoiceField(
        required=True,
        label="",
        coerce=lambda c: c == "asc",
        choices=[("asc", "ascending"), ("desc", "descending")],
    )

    def __init__(self, fields, *args, **kwargs):
        super(OrderByForm, self).__init__(*args, **kwargs)
        self.fields["order_by"].choices = [(f, f) for f in fields]


class BanUserForm(forms.Form):
    username = forms.CharField(
        required=True, label="username", validators=[validate_user]
    )
    ban = forms.BooleanField(
        label="ban",
        required=False,
        initial=True,
    )
    reason = forms.CharField(required=True, label="reason")

    def clean_username(self):
        value = self.cleaned_data["username"]
        try:
            user = User.objects.get(username=value)
            if user.is_moderator or user.is_admin:
                raise ValidationError(f"User {value} is staff.")
            return user
        except User.DoesNotExist:
            raise ValidationError(f"User {value} not found.")


CAPTCHA_CHOICES = [
    ("fish", "Fishes."),
    ("dog", "A dog."),
    ("rock", "A rock."),
]


class InvitationRequestForm(forms.Form):
    required_css_class = "required"
    name = forms.CharField(
        label="internet handle",
        required=True,
        max_length=100,
        help_text="something for us to call you",
    )
    address = forms.EmailField(
        required=True,
        label="e-mail",
        help_text="Doesn't have to be the same address you will use for your account.",
    )
    about = forms.CharField(
        required=True,
        widget=forms.Textarea({"rows": 3, "cols": 15, "placeholder": ""}),
        help_text="Insert evidence of your web presence like blog posts you've written and accounts on other communities to support your request. (this is just to make sure you're not a spammer, no need to add a lot of stuff)",
        min_length=20,
    )
    choose_dead = forms.ChoiceField(
        required=True,
        label="choose what cannot be alive (you cannot change this after submission)",
        choices=CAPTCHA_CHOICES,
    )

    def clean_choose_dead(self):
        choice = self.cleaned_data["choose_dead"]
        if choice != "rock":
            raise ValidationError("")
        return choice
