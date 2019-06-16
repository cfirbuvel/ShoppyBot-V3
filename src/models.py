import datetime
import os
from gettext import gettext as _

from os.path import dirname, abspath, join
from enum import Enum
from peewee import Model, CharField, IntegerField, SqliteDatabase, \
    ForeignKeyField, DecimalField, BlobField, BooleanField, TimeField, TextField, OperationalError
from pytz import timezone
from playhouse.sqlite_ext import DateTimeField

d = dirname(dirname(abspath(__file__)))
db = SqliteDatabase(join(d, 'db.sqlite'))


class BaseModel(Model):
    class Meta:
        database = db


def format_date_time(value, formats, post_process=None):
    post_process = post_process or (lambda x: x)
    for fmt in formats:
        try:
            value, offset = value.rsplit('+')
            offset = '+' + offset.replace(':', '')
            value = value + offset
            return post_process(datetime.datetime.strptime(value, fmt))
        except ValueError:
            pass
    return value


class DateTimeTZField(DateTimeField):
    formats = [
        '%Y-%m-%d %H:%M:%S.%f%z',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]

    def adapt(self, value):
        if value and isinstance(value, str):
            return format_date_time(value, self.formats)
        return value


def israel_now():
    now = datetime.datetime.now()
    il_tz = timezone('Asia/Jerusalem')
    now = il_tz.localize(now)
    return now


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

    @staticmethod
    def get_clients_permissions():
        clients_permissions = [
            UserPermission.AUTHORIZED_RESELLER, UserPermission.FAMILY, UserPermission.FRIEND,
            UserPermission.VIP_CLIENT, UserPermission.CLIENT
        ]
        permissions = UserPermission.select().where(UserPermission.permission.in_(clients_permissions))
        return permissions

    @staticmethod
    def get_users_permissions():
        users_permissions = [
            UserPermission.AUTHORIZED_RESELLER, UserPermission.FAMILY, UserPermission.FRIEND,
            UserPermission.VIP_CLIENT, UserPermission.CLIENT, UserPermission.NOT_REGISTERED,
            UserPermission.PENDING_REGISTRATION
        ]
        users_permissions = UserPermission.select().where(UserPermission.permission.in_(users_permissions))
        return users_permissions

    @staticmethod
    def get_admin_permissions():
        admin_permissions = [
            UserPermission.AUTHORIZED_RESELLER, UserPermission.FAMILY, UserPermission.FRIEND,
            UserPermission.VIP_CLIENT, UserPermission.CLIENT, UserPermission.OWNER, UserPermission.LOGISTIC_MANAGER
        ]
        permissions = UserPermission.select().where(UserPermission.permission.in_(admin_permissions))
        return permissions


class User(BaseModel):
    username = CharField(null=True)
    telegram_id = IntegerField()
    locale = CharField(max_length=4, default='iw')
    phone_number = CharField(null=True)
    permission = ForeignKeyField(UserPermission, related_name='users')
    banned = BooleanField(default=False)
    registration_time = DateTimeTZField(default=israel_now)
    currency = CharField(default=Currencies.DOLLAR, choices=Currencies.CHOICES)
    registration_msg_id = CharField(null=True)

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

    @property
    def allowed_settings_list(self):
        return [item.setting for item in self.allowed_settings]


class AllowedSetting(BaseModel):
    COURIERS = 1
    BOT_STATUS = 2
    STATISTICS = 3
    USERS = 4
    REVIEWS = 5
    WORKING_HOURS = 6
    BOT_MESSAGES = 7
    LOTTERY = 8
    CHANNELS = 9
    ADVERTISMENTS = 10
    ORDERS = 11
    MY_PRODUCTS = 12
    CATEGORIES = 13
    WAREHOUSE = 14
    DISCOUNT = 15
    DELIVERY = 16
    PRICE_GROUPS = 17
    LOCATIONS = 18
    ID_PROCESS = 19
    DEFAULT_LANGUAGE = 20

    setting = IntegerField()
    user = ForeignKeyField(User, related_name='allowed_settings')


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


class GroupProductCount(BaseModel):
    name = CharField()


class Product(BaseModel):
    title = CharField()
    is_active = BooleanField(default=True)
    credits = IntegerField(default=0)
    warehouse_active = BooleanField(default=False)
    category = ForeignKeyField(ProductCategory, related_name='products', null=True)


class ProductGroupCount(BaseModel):
    product = ForeignKeyField(Product, related_name='price_groups')
    price_group = ForeignKeyField(GroupProductCount, related_name='products')


class UserGroupCount(BaseModel):
    user = ForeignKeyField(User, related_name='price_groups')
    price_group = ForeignKeyField(GroupProductCount, related_name='users')


class GroupProductCountPermission(BaseModel):
    price_group = ForeignKeyField(GroupProductCount, related_name='permissions')
    permission = ForeignKeyField(UserPermission, related_name='price_groups')


class ProductCount(BaseModel):
    product = ForeignKeyField(Product, related_name='product_counts', null=True)
    price_group = ForeignKeyField(GroupProductCount, related_name='product_counts', null=True)
    count = IntegerField()
    price = DecimalField()


class ProductMedia(BaseModel):
    product = ForeignKeyField(Product, related_name='product_media')
    file_id = CharField()
    file_type = CharField(null=True)


class ProductWarehouse(BaseModel):
    courier = ForeignKeyField(User, related_name='courier_warehouses', null=True)
    product = ForeignKeyField(Product, related_name='product_warehouses')
    count = IntegerField(default=0)


class DeliveryFeePermission(BaseModel):
    permission = ForeignKeyField(UserPermission, related_name='delivery_fees')


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
    shipping_time = CharField()
    location = ForeignKeyField(Location, null=True)
    status = IntegerField(default=CONFIRMED, choices=STATUSES)
    client_notified = BooleanField(default=False)
    date_created = DateTimeTZField(default=israel_now)
    address = CharField(default='', null=True)
    total_cost = DecimalField(default=0)
    btc_payment = BooleanField(default=False)
    coordinates = CharField(null=True)
    delivery_fee = DecimalField(default=0)
    discount = DecimalField(default=0)

    # refactor this?
    order_hidden_text = TextField(default='')
    order_text = TextField(default='')
    order_text_msg_id = TextField(null=True)

    picked_by_courier = BooleanField(default=False)

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
    for_order = BooleanField(default=False)
    type = CharField()


class IdentificationPermission(BaseModel):
    stage = ForeignKeyField(IdentificationStage, related_name='permissions')
    permission = ForeignKeyField(UserPermission, related_name='id_stages')


class IdentificationQuestion(BaseModel):
    content = CharField()
    stage = ForeignKeyField(IdentificationStage, related_name='identification_questions')


class UserIdentificationAnswer(BaseModel):
    stage = ForeignKeyField(IdentificationStage, related_name='identification_answers')
    question = ForeignKeyField(IdentificationQuestion, related_name='identification_answers')
    user = ForeignKeyField(User, related_name='identification_answers')
    content = CharField()


class OrderIdentificationAnswer(BaseModel):
    stage = ForeignKeyField(IdentificationStage, related_name='identification_answers')
    question = ForeignKeyField(IdentificationQuestion, related_name='identification_answers')
    order = ForeignKeyField(Order, related_name='identification_answers')
    content = CharField()
    msg_id = CharField(null=True)


class ChannelMessageData(BaseModel):
    channel = CharField()
    msg_id = CharField()
    order = ForeignKeyField(Order, related_name='channel_messages', null=True)


class CurrencyRates(BaseModel):
    currency = CharField(default=Currencies.DOLLAR, choices=Currencies.CHOICES)
    btc_rate = DecimalField()
    dollar_rate = DecimalField()


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
    caption = CharField(null=True)
    author = ForeignKeyField(User, related_name='read_messages')
    replied = BooleanField(default=False)
    read = BooleanField(default=False)
    sent_msg_id = CharField(null=True)
    # status_msg_id = CharField(null=True)
    date_created = DateTimeTZField(default=israel_now)


class Lottery(BaseModel):
    PRODUCT = 1
    PRICE = 2
    CATEGORY = 1
    ALL_PRODUCTS = 2
    SINGLE_PRODUCT = 3
    BY = (
        (PRODUCT, 'Product'), (PRICE, 'Price')
    )
    PRODUCTS = (
        (SINGLE_PRODUCT, 'Single Product'), (CATEGORY, 'Category'), (ALL_PRODUCTS, 'All products')
    )
    active = BooleanField(default=False)
    created_date = DateTimeTZField(default=israel_now)
    completed_date = DateTimeTZField(null=True)
    num_codes = IntegerField(default=0)
    num_tickets = IntegerField(default=0)
    by_condition = IntegerField(choices=BY, default=PRODUCT)
    products_condition = IntegerField(choices=PRODUCTS, default=ALL_PRODUCTS)
    category_condition = ForeignKeyField(ProductCategory, null=True)
    single_product_condition = ForeignKeyField(Product, null=True)
    min_price = DecimalField(null=True)
    prize_product = ForeignKeyField(Product, null=True)
    prize_count = IntegerField(null=True)

    @property
    def could_activate(self):
        condition = [self.num_codes, self.num_tickets, self.prize_product, self.prize_count]
        return all(condition)

    @property
    def by_condition_display(self):
        return dict(self.BY)[self.by_condition]

    @property
    def products_condition_display(self):
        return dict(self.PRODUCTS)[self.products_condition]


class LotteryPermission(BaseModel):
    lottery = ForeignKeyField(Lottery, related_name='permissions')
    permission = ForeignKeyField(UserPermission, related_name='lotteries')


class LotteryParticipant(BaseModel):
    is_winner = BooleanField(default=False)
    code = CharField()
    participant = ForeignKeyField(User, related_name='lotteries')
    lottery = ForeignKeyField(Lottery, related_name='participants', null=True)
    is_pending = BooleanField(default=False)
    created_date = DateTimeTZField(default=israel_now)


class Review(BaseModel):
    user = ForeignKeyField(User, related_name='reviews')
    order = ForeignKeyField(Order, related_name='reviews')
    text = CharField(null=True)
    date_created = DateTimeTZField(default=israel_now)
    is_pending = BooleanField(default=True)


class ReviewQuestion(BaseModel):
    text = CharField()


class ReviewQuestionRank(BaseModel):
    question = ForeignKeyField(ReviewQuestion)
    review = ForeignKeyField(Review)
    rank = IntegerField(default=5)


class Ad(BaseModel):
    title = CharField()
    text = CharField()
    media = CharField(null=True)
    media_type = CharField(null=True)
    interval = IntegerField(default=2)
    last_sent_date = DateTimeTZField(null=True)


class ChannelAd(BaseModel):
    channel = ForeignKeyField(Channel, related_name='ads')
    ad = ForeignKeyField(Ad, related_name='channels')


class UserAd(BaseModel):
    user = ForeignKeyField(User, related_name='ads')
    ad = ForeignKeyField(Ad, related_name='users')


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
            WorkingHours, GroupProductCountPermission, CourierChat, CourierChatMessage, IdentificationPermission,
            Lottery, LotteryParticipant, LotteryPermission, ProductGroupCount, UserGroupCount, Review, ReviewQuestion,
            ReviewQuestionRank, Ad, ChannelAd, UserAd, AllowedSetting, DeliveryFeePermission
        ], safe=True
    )


def close_db():
    db.close()


def delete_db():
    db.close()
    os.remove('db.sqlite')
