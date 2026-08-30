from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserPreference, AlertSubscription

QUAL_CHOICES = [
    ("", "Select education"),
    ("10th Pass", "10th Pass"),
    ("12th Pass", "12th Pass"),
    ("ITI", "ITI"),
    ("Diploma", "Diploma"),
    ("Graduate", "Graduate"),
    ("Engineering", "Engineering"),
    ("Post Graduate", "Post Graduate"),
]


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class PreferenceForm(forms.ModelForm):
    education = forms.ChoiceField(choices=QUAL_CHOICES, required=False)
    preferred_qualifications_text = forms.CharField(required=False, help_text="Comma-separated")
    preferred_sectors_text = forms.CharField(required=False, help_text="Comma-separated")
    preferred_states_text = forms.CharField(required=False, help_text="Comma-separated")

    class Meta:
        model = UserPreference
        fields = ["education", "discipline", "state", "category", "date_of_birth", "experience_months", "language", "email_alerts", "push_alerts"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        if getattr(inst, "pk", None):
            self.fields["preferred_qualifications_text"].initial = ", ".join(inst.preferred_qualifications or [])
            self.fields["preferred_sectors_text"].initial = ", ".join(inst.preferred_sectors or [])
            self.fields["preferred_states_text"].initial = ", ".join(inst.preferred_states or [])

    def save(self, commit=True):
        obj = super().save(commit=False)
        for model_field, form_field in (
            ("preferred_qualifications", "preferred_qualifications_text"),
            ("preferred_sectors", "preferred_sectors_text"),
            ("preferred_states", "preferred_states_text"),
        ):
            raw = self.cleaned_data.get(form_field, "")
            setattr(obj, model_field, [x.strip() for x in raw.split(",") if x.strip()])
        if commit:
            obj.save()
        return obj


class EligibilityForm(forms.Form):
    education = forms.ChoiceField(choices=QUAL_CHOICES, required=False)
    discipline = forms.CharField(required=False, max_length=160)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    category = forms.ChoiceField(choices=UserPreference.CATEGORIES, required=False)
    gender = forms.ChoiceField(choices=[("", "Not specified"), ("Male", "Male"), ("Female", "Female"), ("Other", "Other")], required=False)
    experience_months = forms.IntegerField(required=False, min_value=0, max_value=1000)


class AlertForm(forms.ModelForm):
    qualifications_text = forms.CharField(required=False, help_text="Example: Graduate, Engineering")
    sectors_text = forms.CharField(required=False, help_text="Example: Railway, Banking")
    states_text = forms.CharField(required=False, help_text="Example: Uttar Pradesh, Delhi")
    keywords_text = forms.CharField(required=False, help_text="Example: clerk, engineer")

    class Meta:
        model = AlertSubscription
        fields = ["email", "frequency"]

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.qualifications = [x.strip() for x in self.cleaned_data.get("qualifications_text", "").split(",") if x.strip()]
        obj.sectors = [x.strip() for x in self.cleaned_data.get("sectors_text", "").split(",") if x.strip()]
        obj.states = [x.strip() for x in self.cleaned_data.get("states_text", "").split(",") if x.strip()]
        obj.keywords = [x.strip() for x in self.cleaned_data.get("keywords_text", "").split(",") if x.strip()]
        if commit:
            obj.save()
        return obj
