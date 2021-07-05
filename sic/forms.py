from django import forms
from django.forms import formset_factory, ModelForm
from django.forms import modelformset_factory
from django.forms import BaseFormSet
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from .apps import SicAppConfig as config
from .models import Tag, User


class SubmitStoryForm(forms.Form):
    title = forms.CharField(label="Story title", required=True, max_length=100)
    description = forms.CharField(required=False)
    url = forms.URLField(required=False)
    user_is_author = forms.BooleanField(
        label="Author",
        required=False,
        help_text="I am the author of the story at this URL (or this text)",
    )
    tags = forms.ModelMultipleChoiceField(queryset=Tag.objects.all(), required=False)


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
        required=False, label="Avatar file (leave blank for none)"
    )


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
        r = User.objects.filter(username__iexact=username)
        if r.count():
            raise ValidationError("Username already exists")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        r = User.objects.filter(email__iexact=email)
        if r.count():
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
