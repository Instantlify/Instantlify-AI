"""Placeholder kept so the migration graph stays intact.

The seeded templates (0006, 0010) and default branding already use the Instantlify name,
so there is nothing left to rewrite here.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0012_affiliateaccount"), ("tenants", "0012_profilephoto")]
    operations = []
