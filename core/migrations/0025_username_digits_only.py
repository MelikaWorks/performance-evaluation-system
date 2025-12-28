from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0022_evaluationreport'),  # مثل '0024_auto_20251005_1453'
    ]

    operations = [
        migrations.RunSQL(
            # قفل عددی فقط برای کاربران غیرسوپر‌یوزر
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'auth_user_username_digits_only_non_super'
                    ) THEN
                        ALTER TABLE auth_user
                        ADD CONSTRAINT auth_user_username_digits_only_non_super
                        CHECK (
                            is_superuser = TRUE OR username ~ '^[0-9]+$'
                        );
                    END IF;
                END$$;
            """,
            reverse_sql="""
                ALTER TABLE auth_user
                DROP CONSTRAINT IF EXISTS auth_user_username_digits_only_non_super;
            """,
        ),
    ]
