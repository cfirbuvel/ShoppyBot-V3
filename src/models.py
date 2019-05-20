import datetime
import os
from gettext import gettext as _

from os.path import dirname, abspath, join
from enum import Enum
from peewee import Model, CharField, IntegerField, SqliteDatabase, \
    ForeignKeyField, DecimalField, BlobField, BooleanField, TimeField, DateTimeField, TextField, OperationalError

d = dirname(dirname(abspath(__file__)))
db = SqliteDatabase(join(d, 'db.sqlite'))


class BaseModel(Model):
    class Meta:
        database = db


class Currencies:
    DOLLAR = 'USD'
    EURO = 'EUR'
    POUND = 'GBP'
    ILS = 'ILS'

    CURRENCIES = {
        DOLLAR: (_('Dollar'), '$'), EURO: (_('Euro'), '€'), POUND: (_('Pound'), '£'), ILS: (_('Shekel'), '₪')
    }

    CHOICES = [
        (DOLLAR, 'Dollar'), (EURO, 'Euro'), (POUND, 'Pound'), (ILS, 'Shekel')
    ]


class ConfigValue(BaseModel):
    name = CharField()
    value = CharField()


class WorkingHours(BaseModel):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6
    DAYS = [
        (SUN, _('Sunday')), (MON, _('Monday')), (TUE, _('Tuesday')), (WED, _('Wednesday')), (THU, _('Thurdsay')),
        (FRI, _('Friday')), (SAT, _('Saturday'))
    ]
    day = IntegerField(choices=DAYS)
    open_time = TimeField()
    close_time = TimeField()

    def get_day_display(self):
        print(dict(self.DAYS))
        return dict(self.DAYS)[self.day]


class Location(BaseModel):
    title = CharField()
    delivery_min = IntegerField(null=True)
    delivery_fee = IntegerField(null=True)


class UserPermission(BaseModel):
    OWNER = 1
    LOGISTIC_MANAGER = 2
    COURIER = 3
    AUTHORIZED_RESELLER = 4
    FAMILY = 5
    FRIEND = 6
    VIP_CLIENT = 7
    CLIENT = 8
    NOT_REGISTERED = 9
    PENDING_REGISTRATION = 10

    PERMISSIONS = (
        (OWNER, _('Admin')), (LOGISTIC_MANAGER, _('Logistic manager')), (COURIER, _('Courier')),
        (AUTHORIZED_RESELLER, _('Authorized reseller')), (FAMILY, _('Family')), (FRIEND, _('Friend')),
        (VIP_CLIENT, _('Vip client')), (CLIENT, _('Client')), (NOT_REGISTERED, _('Not registered')),
        (PENDING_REGISTRATION, _('Pending registration'))
    )
    permission = IntegerField(default=NOT_REGISTERED, choices=PERMISSIONS)

    def get_permission_display(self):
        return dict(self.PERMISSIONS)[self.permission]


# class LogisticManagerPermission(BaseModel):
#     permission =
class GroupProductCount(BaseModel):
    name = CharField()


class User(BaseModel):
    username = CharField(null=True)
    telegram_id = IntegerField()
    locale = CharField(max_length=4, default='iw')
    phone_number = CharField(null=True)
    permission = ForeignKeyField(UserPermission, related_name='users')
    banned = BooleanField(default=False)
    registration_time = DateTimeField(default=datetime.datetime.now)
    currency = CharField(default=Currencies.DOLLAR, choices=Currencies.CHOICES)
    group_price = ForeignKeyField(GroupProductCount, null=True, related_name='users')

    @property
    def is_admin(self):
        return self.permission.permission == UserPermission.OWNER

    @property
    def is_logistic_manager(self):
        return self.permission.permission == UserPermission.LOGISTIC_MANAGER

    @property
    def is_registered(self):
        return self.permission.permission not in (UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION)

    @property
    def is_pending_registration(self):
        return self.permission.permission == UserPermission.PENDING_REGISTRATION

    @property
    def is_vip_client(self):
        return self.permission.permission == UserPermission.VIP_CLIENT

    @property
    def is_courier(self):
        return self.permission.permission == UserPermission.COURIER


class CourierLocation(BaseModel):
    location = ForeignKeyField(Location, related_name='couriers')
    user = ForeignKeyField(User, related_name='locations')


class Channel(BaseModel):
    name = CharField()
    conf_name = CharField(null=True)
    channel_id = CharField(null=True)
    link = CharField(null=True)


class ChannelPermissions(BaseModel):
    channel = ForeignKeyField(Channel, related_name='permissions')
    permission = ForeignKeyField(UserPermission, related_name='channels')

    def get_permission_display(self):
        return self.permission.get_permission_display()


class ProductCategory(BaseModel):
    title = CharField(unique=True)


class GroupProductCountPermission(BaseModel):
    price_group = ForeignKeyField(GroupProductCount, related_name='permissions')
    permission = ForeignKeyField(UserPermission, related_name='group_counts')


class Product(BaseModel):
    title = CharField()
    is_active = BooleanField(default=True)
    credits = IntegerField(default=0)
    warehouse_active = BooleanField(default=False)
    category = ForeignKeyField(ProductCategory, related_name='products', null=True)
    group_price = ForeignKeyField(GroupProductCount, related_name='products', null=True)


class ProductMedia(BaseModel):
    product = ForeignKeyField(Product, related_name='product_media')
    file_id = CharField()
    file_type = CharField(null=True)


class ProductCount(BaseModel):
    product = ForeignKeyField(Product, related_name='product_counts', null=True)
    product_group = ForeignKeyField(GroupProductCount, related_name='product_counts', null=True)
    count = IntegerField()
    price = DecimalField()


class ProductWarehouse(BaseModel):
    courier = ForeignKeyField(User, related_name='courier_warehouses', null=True)
    product = ForeignKeyField(Product, related_name='product_warehouses')
    count = IntegerField(default=0)


class DeliveryMethod(Enum):
    PICKUP = 1
    DELIVERY = 2


class Order(BaseModel):
    PICKUP = 1
    DELIVERY = 2
    DELIVERY_METHODS = (
        (PICKUP, _('Pickup')), (DELIVERY, _('Delivery'))
    )

    CONFIRMED = 1
    PROCESSING = 2
    DELIVERED = 3
    CANCELLED = 4
    # FINISHED = 5
    STATUSES = (
        (CONFIRMED, _('Confirmed')), (PROCESSING, _('Processing')), (DELIVERED, _('Delivered')), (CANCELLED, _('Cancelled'))
    )
    user = ForeignKeyField(User, related_name='user_orders')
    courier = ForeignKeyField(User, related_name='courier_orders', null=True)
    shipping_method = IntegerField(default=PICKUP, choices=DELIVERY_METHODS)
    shipping_time = DateTimeField()
    location = ForeignKeyField(Location, null=True)
    status = IntegerField(default=CONFIRMED, choices=STATUSES)
    client_notified = BooleanField(default=False)
    date_created = DateTimeField(default=datetime.datetime.now)
    address = CharField(default='')
    phone_number = CharField(default='')
    total_cost = DecimalField(default=0)
    btc_payment = BooleanField(default=False)
    coordinates = CharField(null=True)
    delivery_fee = DecimalField(default=0)

    # refactor this?
    order_hidden_text = TextField(default='')
    order_text = TextField(default='')
    order_text_msg_id = TextField(null=True)

    def get_delivery_display(self):
        return dict(self.DELIVERY_METHODS)[self.shipping_method]

    def get_status_display(self):
        return dict(self.STATUSES)[self.status]


class BtcStatus:
    LOWER = 1
    PAID = 2
    HIGHER = 3
    NOT_PAID = 4
    ERROR = 5


class BtcStage:
    FIRST = 1
    SECOND = 2


class OrderBtcPayment(BaseModel):
    order = ForeignKeyField(Order, related_name='btc_data')
    address = CharField(null=True)
    xpub = CharField(null=True)
    admin_address = CharField(null=True)
    admin_xpub = CharField(null=True)
    amount = DecimalField(null=True)
    paid_status = IntegerField(default=BtcStatus.NOT_PAID)
    balance = DecimalField(null=True, default=0)
    payment_stage = IntegerField(default=BtcStage.FIRST)


class BtcProc(BaseModel):
    order_id = IntegerField()


class OrderItem(BaseModel):
    order = ForeignKeyField(Order, related_name='order_items')
    product = ForeignKeyField(Product, related_name='product_items')
    count = IntegerField(default=1)
    total_price = DecimalField(default=0,
                               verbose_name='total price for each item')


class IdentificationStage(BaseModel):
    active = BooleanField(default=True)
    vip_required = BooleanField(default=False)
    for_order = BooleanField(default=False)
    type = CharField()
    # actual_type = CharField()


class IdentificationQuestion(BaseModel):
    content = CharField()
    stage = ForeignKeyField(IdentificationStage, related_name='identification_questions')


class UserIdentificationAnswer(BaseModel):
    stage = ForeignKeyField(IdentificationStage, related_name='identification_answers')
    question = ForeignKeyField(IdentificationQuestion, related_name='identification_answers')
    user = ForeignKeyField(User, related_name='identification_answers')
    content = CharField()
    # actual_type = CharField()


class OrderIdentificationAnswer(BaseModel):
    stage = ForeignKeyField(IdentificationStage, related_name='identification_answers')
    question = ForeignKeyField(IdentificationQuestion, related_name='identification_answers')
    order = ForeignKeyField(Order, related_name='identification_answers')
    content = CharField()
    # actual_type = CharField()
    msg_id = CharField(null=True)


class ChannelMessageData(BaseModel):
    channel = CharField()
    msg_id = CharField()
    order = ForeignKeyField(Order, related_name='channel_messages', null=True)


class CurrencyRates(BaseModel):
    currency = CharField(default=Currencies.DOLLAR, choices=Currencies.CHOICES)
    btc_rate = DecimalField()
    dollar_rate = DecimalField()
    # last_updated = DateTimeField(default=datetime.datetime.now)


class BitcoinCredentials(BaseModel):
    wallet_id = CharField(null=True)
    password = CharField(null=True)
    enabled = BooleanField(default=False)


class CourierChat(BaseModel):
    YES = 1
    NO = 2
    ANSWER_CHOICES = (YES, 'yes'), (NO, 'no')
    active = BooleanField(default=False)
    order = ForeignKeyField(Order, related_name='chats')
    user = ForeignKeyField(User, related_name='chats')
    courier = ForeignKeyField(User, related_name='chats')
    unresponsible_answer = IntegerField(choices=ANSWER_CHOICES, null=True)
    ping_sent = BooleanField(default=False)
    user_menu_id = CharField(null=True)
    courier_menu_id = CharField(null=True)


class CourierChatMessage(BaseModel):
    chat = ForeignKeyField(CourierChat, related_name='messages')
    msg_type = CharField()
    message = CharField()
    author = ForeignKeyField(User, related_name='read_messages')
    replied = BooleanField(default=False)
    read = BooleanField(default=False)
    sent_msg_id = CharField(null=True)
    date_created = DateTimeField(default=datetime.datetime.now)


def create_tables():
    try:
        db.connect()
    except OperationalError:
        db.close()
        db.connect()

    db.create_tables(
        [
            Location, UserPermission, User, Channel, ChannelPermissions, ProductCategory, Product, ProductCount,
            Order, OrderItem, ProductWarehouse, ProductMedia, IdentificationStage,
            OrderIdentificationAnswer, IdentificationQuestion, ChannelMessageData, GroupProductCount,
            CurrencyRates, BitcoinCredentials, OrderBtcPayment, BtcProc, ConfigValue, UserIdentificationAnswer, CourierLocation,
            WorkingHours, GroupProductCountPermission, CourierChat, CourierChatMessage
        ], safe=True
    )


def close_db():
    db.close()


def delete_db():
    db.close()
    os.remove('db.sqlite')
