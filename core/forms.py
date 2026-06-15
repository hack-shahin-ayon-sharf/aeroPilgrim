from django import forms
from .models import Search


class SearchForm(forms.ModelForm):

    class Meta:
        model = Search

        fields = [
            'city_departure',
            'city_arrival',
            'stay_days',
            'timespan_to_search',
        ]

        widgets = {
            'city_departure': forms.Select(
                attrs={
                    'class': 'bg-transparent w-full outline-none'
                }
            ),

            'city_arrival': forms.Select(
                attrs={
                    'class': 'bg-transparent w-full outline-none'
                }
            ),

            'stay_days': forms.Select(
                attrs={
                    'class': 'bg-transparent w-full outline-none'
                }
            ),

            'timespan_to_search': forms.Select(
                attrs={
                    'class': 'bg-transparent w-full outline-none'
                }
            ),
        }