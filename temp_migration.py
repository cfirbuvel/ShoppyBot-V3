import os
from playhouse.migrate import SqliteDatabase, SqliteMigrator, migrate, IntegerField, DateTimeField, BooleanField, CharField, ForeignKeyField
import datetime
from src.models import Currencies, User, GroupProductCount


if __name__ == '__main__':
    db_path = 'db.sqlite'
    db = SqliteDatabase(db_path)
    migrator = SqliteMigrator(db)
    group_price = ForeignKeyField(GroupProductCount, GroupProductCount.id, null=True, related_name='users')
    migrate(
        migrator.add_column('user', 'group_price_id', group_price)
    )
    db.close()

