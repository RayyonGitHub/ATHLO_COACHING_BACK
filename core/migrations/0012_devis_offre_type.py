from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_devis_prix_propose_devis_prospect'),
    ]

    operations = [
        migrations.AddField(
            model_name='devis',
            name='offre_type',
            field=models.CharField(choices=[('seance', 'Séance individuelle'), ('pack', 'Pack'), ('abonnement', 'Abonnement')], default='seance', max_length=20),
        ),
    ]
