from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_coach_stripe_onboarding_complete'),
    ]

    operations = [
        migrations.AlterField(
            model_name='devis',
            name='statut',
            field=models.CharField(
                choices=[('en_attente', 'En attente'), ('offre_recue', 'Offre reçue')],
                default='en_attente',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='devis',
            name='invitation_liee',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='devis_associes',
                to='core.clientinvitation',
            ),
        ),
    ]
