import os
from playhouse.migrate import SqliteDatabase, SqliteMigrator, migrate, IntegerField, DateTimeField, BooleanField, CharField, ForeignKeyField, DecimalField
import datetime
from src.models import Currencies, User, GroupProductCount, GroupProductCountPermission, Order, Product, ProductCount, Review


if __name__ == '__main__':
    db_path = 'db.sqlite'
    db = SqliteDatabase(db_path)
    migrator = SqliteMigrator(db)
    discount = DecimalField(default=0)
    last_sent_date = DateTimeField(null=True)
    picked = BooleanField(default=False)
    # media = CharField(null=True)
    # media_type = CharField(null=True)
    col = CharField(null=True)
    migrate(
        migrator.add_column('courierchatmessage', 'caption', col)
        #migrator.add_column('order', 'picked_by_courier', picked)
        # migrator.add_column('courierchatmessage', 'status_msg_id', col)
        # migrator.add_column('user', 'registration_msg_id', media_type)
        # migrator.drop_column('ad', 'photo_id'),
        # migrator.drop_column('ad', 'gif_id'),
        # migrator.add_column('ad', 'media', media),
        # migrator.add_column('ad', 'media_type', media_type)
        # migrator.drop_column('ad', 'last_sent_date'),
        # migrator.add_column('ad', 'last_sent_date', last_sent_date)
    )
    db.close()

