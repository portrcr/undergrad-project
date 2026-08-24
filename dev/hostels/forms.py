from django import forms

from .models import Hostel, Room, Term


class HostelForm(forms.ModelForm):
    class Meta:
        model = Hostel
        fields = ['name', 'location', 'description', 'image']


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['room_number', 'capacity', 'price_per_term', 'has_private_bathroom', 'status']


class TermForm(forms.ModelForm):
    class Meta:
        model = Term
        fields = ['name', 'start_date', 'end_date', 'sequence_number']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
