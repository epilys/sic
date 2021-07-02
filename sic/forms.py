from django import forms
from django.forms import formset_factory, ModelForm
from django.forms import modelformset_factory
from django.forms import BaseFormSet
from django.apps import apps as django_apps
from .models import Tag


class SubmitStoryForm(forms.Form):
    title = forms.CharField(label="Story title", required=True, max_length=100)
    description = forms.CharField(required=False)
    url = forms.URLField(required=False)
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
