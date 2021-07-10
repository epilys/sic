from django import forms
from django.core.exceptions import ValidationError
from .apps import SicAppConfig as config
from .models import Tag, User, StoryKind


class SubmitStoryForm(forms.Form):
    required_css_class = "required"
    title = forms.CharField(label="Story title", required=True, max_length=100)
    description = forms.CharField(required=False)
    url = forms.URLField(required=False)
    publish_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Set publication date if relevant (for example, an article on current affairs).",
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


class SubmitCommentForm(forms.Form):
    text = forms.CharField(
        required=True, label="Comment", max_length=500, widget=forms.Textarea
    )
    text.widget.attrs.update({"rows": 3, "placeholder": ""})


class SubmitReplyForm(forms.Form):
    text = forms.CharField(
        required=True, label="Reply", max_length=500, widget=forms.Textarea
    )
    text.widget.attrs.update({"rows": 3, "placeholder": ""})


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


class EditTagForm(forms.Form):
    name = forms.CharField(required=True, label="Name", max_length=40)
    hex_color = forms.CharField(
        max_length=7,
        required=False,
        initial="#ffffff",
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    parents = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        label="parents",
        required=False,
        help_text="Hold down “Control”, or “Command” on a Mac, to select more than one.",
    )
