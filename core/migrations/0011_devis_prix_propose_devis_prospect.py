from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_salle_coachs_bannis'),
    ]

    operations = [
        migrations.AddField(
            model_name='devis',
            name='prix_propose',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='devis',
            name='prospect',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='devis_demandes', to=settings.AUTH_USER_MODEL),
        ),
    ]
