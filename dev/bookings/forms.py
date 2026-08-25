from django import forms

from .models import Notification


class MessageStudentForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Write a message to this student...'}),
        }
