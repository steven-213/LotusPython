from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.membresias.models import MembresiaUsuario, PlanMembresia
from apps.sesiones.models import Usuario


class MembresiasPublicasTest(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(
            documento=778899,
            nombre="Lina",
            apellido="Cliente",
            correo="lina@test.com",
            fecha_nacimiento="1994-05-12",
            clave="1234",
            rol=Usuario.ROL_CLIENTE,
        )

    def test_listado_publico_muestra_planes_base(self):
        response = self.client.get(reverse("membresias:membresias"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esencia Lotus")
        self.assertContains(response, "Ritual Sereno")
        self.assertContains(response, "Aura Suprema")

    def test_cliente_puede_activar_membresia(self):
        plan = PlanMembresia.objects.get(slug="ritual-sereno")
        session = self.client.session
        session["usuario_id"] = self.usuario.id
        session["usuario_rol"] = Usuario.ROL_CLIENTE
        session.save()

        response = self.client.post(
            reverse("membresias:activar_membresia", args=[plan.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            MembresiaUsuario.objects.filter(
                usuario=self.usuario,
                plan=plan,
                estado=MembresiaUsuario.ESTADO_ACTIVA,
            ).exists()
        )
        self.assertContains(response, "ya quedo activa")


class MembresiasDashboardTest(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create(
            documento=112233,
            nombre="Admin",
            apellido="Membresias",
            correo="admin-membresias@test.com",
            fecha_nacimiento="1990-02-10",
            clave="admin123",
            rol=Usuario.ROL_ADMIN,
        )
        self.cliente = Usuario.objects.create(
            documento=445566,
            nombre="Paula",
            apellido="Miembro",
            correo="paula@test.com",
            fecha_nacimiento="1995-07-22",
            clave="1234",
            rol=Usuario.ROL_CLIENTE,
        )
        self.plan = PlanMembresia.objects.get(slug="esencia-lotus")

        session = self.client.session
        session["usuario_id"] = self.admin.id
        session["usuario_rol"] = Usuario.ROL_ADMIN
        session.save()

    def test_admin_puede_asignar_membresia_por_documento(self):
        response = self.client.post(
            reverse("membresias:miembro_asignar"),
            {
                "documento": self.cliente.documento,
                "plan": self.plan.id,
                "notas": "Asignacion de prueba",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            MembresiaUsuario.objects.filter(
                usuario=self.cliente,
                plan=self.plan,
                estado=MembresiaUsuario.ESTADO_ACTIVA,
            ).exists()
        )
        self.assertContains(response, "Se asigno la membresia")

    def test_dashboard_admin_muestra_modulo(self):
        MembresiaUsuario.objects.create(
            usuario=self.cliente,
            plan=self.plan,
            fecha_fin=timezone.now() + timezone.timedelta(days=30),
            precio_pagado=self.plan.precio,
        )

        response = self.client.get(reverse("membresias:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Panel de membresias")
        self.assertContains(response, self.plan.nombre)
        self.assertContains(response, self.cliente.nombre)
