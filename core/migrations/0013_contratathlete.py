from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def seed_existing_contracts(apps, schema_editor):
    Client = apps.get_model('core', 'Client')
    ContratAthlete = apps.get_model('core', 'ContratAthlete')
    today = django.utils.timezone.now().date()

    for client in Client.objects.exclude(coach=None):
        credits = max(int(client.seances_restantes or 0), 0)
        if credits <= 0:
            continue
        ContratAthlete.objects.create(
            client=client,
            coach=client.coach,
            type_contrat='PACK',
            statut='ACTIF',
            date_debut=today,
            seances_total=credits,
            seances_restantes=credits,
            montant_ttc=0,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_devis_offre_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContratAthlete',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_contrat', models.CharField(choices=[('ABONNEMENT', 'Abonnement mensuel'), ('PACK', 'Pack de seances'), ('UNITE', 'Seance a l unite')], max_length=20)),
                ('statut', models.CharField(choices=[('ACTIF', 'Actif'), ('EXPIRE', 'Expire'), ('ANNULE', 'Annule')], default='ACTIF', max_length=20)),
                ('date_debut', models.DateField(default=django.utils.timezone.now)),
                ('date_expiration', models.DateField(blank=True, null=True)),
                ('seances_total', models.PositiveIntegerField(default=0)),
                ('seances_restantes', models.PositiveIntegerField(default=0)),
                ('stripe_payment_intent_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('montant_ttc', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contrats', to='core.client')),
                ('coach', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contrats_athletes', to='core.coach')),
            ],
            options={
                'ordering': ['-date_debut', '-id'],
            },
        ),
        migrations.RunPython(seed_existing_contracts, migrations.RunPython.noop),
    ]
