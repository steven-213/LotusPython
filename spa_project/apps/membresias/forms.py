from django import forms

from apps.membresias.models import PlanMembresia
from apps.sesiones.models import Usuario


class PlanMembresiaForm(forms.ModelForm):
    class Meta:
        model = PlanMembresia
        fields = [
            "nombre",
            "slug",
            "subtitulo",
            "descripcion",
            "beneficios",
            "precio",
            "duracion_dias",
            "insignia",
            "destacado",
            "activo",
            "orden",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "beneficios": forms.Textarea(attrs={"rows": 6}),
        }
        help_texts = {
            "slug": "Opcional. Si lo dejas vacio se genera automaticamente.",
        }


class AsignarMembresiaForm(forms.Form):
    documento = forms.IntegerField(label="Documento del cliente")
    plan = forms.ModelChoiceField(
        queryset=PlanMembresia.objects.none(),
        label="Plan de membresia",
        empty_label="Selecciona un plan",
    )
    notas = forms.CharField(
        label="Notas",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = PlanMembresia.objects.filter(activo=True).order_by("orden", "precio")

    def clean_documento(self):
        documento = self.cleaned_data["documento"]
        usuario = Usuario.objects.filter(documento=documento, rol=Usuario.ROL_CLIENTE).first()
        if not usuario:
            raise forms.ValidationError("No existe un cliente registrado con ese documento.")
        self.cleaned_data["usuario"] = usuario
        return documento

