from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_contratathlete'),
    ]

    operations = [
        migrations.AddField(
            model_name='commande',
            name='frais_livraison',
            field=models.FloatField(default=0.0),
        ),
    ]
