from django.db import migrations, models


def map_old_devis_status(apps, schema_editor):
    Devis = apps.get_model('core', 'Devis')
    Devis.objects.filter(statut='offre_recue').update(statut='accepte')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_devis_invitation_liee_and_statut_choices'),
    ]

    operations = [
        migrations.RunPython(map_old_devis_status, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='devis',
            name='statut',
            field=models.CharField(
                choices=[
                    ('en_attente', 'En attente'),
                    ('accepte', 'Accepté'),
                    ('refuse', 'Refusé'),
                ],
                default='en_attente',
                max_length=20,
            ),
        ),
    ]
