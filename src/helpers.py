import configparser
import gettext
import json
import logging
import sys
import re

from collections import defaultdict
from decimal import Decimal

import redis

from telegram import TelegramError

from .models import ProductCount, Product, User, OrderItem, Currencies, ConfigValue, UserPermission,\
    BitcoinCredentials, Channel, ChannelPermissions


class JsonRedis(redis.StrictRedis):

    def json_get(self, name, default=None):
        value = self.get(name)
        if value:
            value = json.loads(value.decode("utf-8"))
        else:
            value = default
        return value

    def json_set(self, name, value):
        value = json.dumps(value)
        return self.set(name, value)


class ConfigHelper:
    def __init__(self, cfgfilename='shoppybot.conf'):
        self.cfgfilename = cfgfilename
        self.config = configparser.ConfigParser(
            defaults={'api_token': '',
                      'channels_language': 'iw', 'default_language': 'iw',
                      'welcome_text': 'Welcome text not configured yet',
                      'order_text': 'Order text not configured yet',
                      'order_complete_text': 'Order text not configured yet',
                      'working_hours': 'Working hours not configured yet',
                      'contact_info': 'Contact info not configured yet',
                      'phone_number_required': 'true',
                      'has_courier_option': 'true',
                      'only_for_registered': 'false', 'delivery_fee': '0',
                      'delivery_fee_for_vip': 'false', 'discount': '0',
                      'discount_min': '0', 'btc_enabled': 'false',
                      'btc_address': '', 'currency': Currencies.DOLLAR,
                      'currencies_api_key': '7405b1ae5a19aefdad05fe182b8e62b7'})
        self.config.read(cfgfilename, encoding='utf-8')
        self.section = 'Settings'

    def convert_to_bool(self, value):
        true_values = ('yes', 'true', '1', 'y')
        # false_values = ('no', 'false', '0', 'n')
        if value.lower() in true_values:
            return True
        else:
            return False

    def get_config_value(self, name, boolean=False, conversion=None):
        try:
            value = ConfigValue.get(name=name)
        except ConfigValue.DoesNotExist:
            value = None
        else:
            value = value.value
        if value is None:
            value = self.config.get(self.section, name)
        value = value.strip()
        if boolean:
            value = self.convert_to_bool(value)
        elif conversion:
            try:
                value = conversion(value)
            except ValueError:
                value = None
        return value

    def set_value(self, name, value):
        value = str(value)
        try:
            db_value = ConfigValue.get(name=name)
        except ConfigValue.DoesNotExist:
            ConfigValue.create(name=name, value=value)
        else:
            db_value.value = value
            db_value.save()

    @property
    def api_token(self):
        return self.get_config_value('api_token')

    @property
    def owner_id(self):
        return self.get_config_value('owner_id', conversion=int)

    @property
    def channels_language(self):
        return self.get_config_value('channels_language')

    @property
    def default_language(self):
        return self.get_config_value('default_language')

    @property
    def welcome_text(self):
        return self.get_config_value('welcome_text')

    @property
    def order_text(self):
        return self.get_config_value('order_text')

    @property
    def order_complete_text(self):
        return self.get_config_value('order_complete_text')

    @property
    def working_hours(self):
        return self.get_config_value('working_hours')

    @property
    def contact_info(self):
        return self.get_config_value('contact_info')

    @property
    def phone_number_required(self):
        return self.get_config_value('phone_number_required', boolean=True)

    @property
    def only_for_registered(self):
        return self.get_config_value('only_for_registered', boolean=True)

    @property
    def has_courier_option(self):
        return self.get_config_value('has_courier_option', boolean=True)

    @property
    def delivery_fee_for_vip(self):
        return self.get_config_value('delivery_fee_for_vip', boolean=True)

    @property
    def delivery_fee(self):
        value = self.get_config_value('delivery_fee', conversion=int)
        if not value:
            value = 0
        return value

    @property
    def delivery_min(self):
        value =  self.get_config_value('delivery_min', conversion=int)
        if not value:
            value = 0
        return value

    @property
    def bot_on_off(self):
        return self.get_config_value('bot_on_off', boolean=True)

    @property
    def discount(self):
        return self.get_config_value('discount')

    @property
    def discount_min(self):
        value = self.get_config_value('discount_min', conversion=int)
        if not value:
            value = 0
        return value

    @property
    def currency(self):
        return self.get_config_value('currency')


class Cart:

    @staticmethod
    def check_cart(user_data):
        # check that cart is still here in case we've restarted
        if 'cart' not in user_data:
            user_data['cart'] = {}
        return user_data['cart']

    @staticmethod
    def add(user_data, product_id):
        cart = Cart.check_cart(user_data)
        product = Product.get(id=product_id)
        if product.group_price:
            query = (ProductCount.product_group == product.group_price)
        else:
            query = (ProductCount.product == product)
        prices = ProductCount.select().where(query).order_by(ProductCount.count.asc())
        counts = [x.count for x in prices]
        min_count = counts[0]

        if product_id not in cart:
            cart[product_id] = min_count
        else:
            # add more
            current_count = cart[product_id]
            current_count_index = counts.index(current_count)
            # iterate through possible product counts for next price
            next_count_index = (current_count_index + 1) % len(counts)
            cart[product_id] = counts[next_count_index]
        user_data['cart'] = cart

        return user_data

    @staticmethod
    def remove(user_data, product_id):
        cart = Cart.check_cart(user_data)
        product_id = str(product_id)
        product = Product.get(id=product_id)
        if product.group_price:
            query = (ProductCount.product_group == product.group_price)
        else:
            query = (ProductCount.product == product)
        prices = ProductCount.select().where(query).order_by(ProductCount.count.asc())
        counts = [x.count for x in prices]

        if product_id in cart:
            current_count = cart[product_id]
            current_count_index = counts.index(current_count)

            if current_count_index == 0:
                del cart[product_id]
            else:
                next_count_index = current_count_index - 1
                cart[product_id] = counts[next_count_index]
        user_data['cart'] = cart

        return user_data

    @staticmethod
    def get_products_info(user_data, for_order=False):
        product_ids = Cart.get_product_ids(user_data)

        group_prices = defaultdict(int)
        products = Product.select().where(Product.id << list(product_ids))
        products_counts = []
        for product in products:
            count = Cart.get_product_count(user_data, product.id)
            group_price = product.group_price
            if group_price:
                group_prices[group_price.id] += count
            products_counts.append((product, count))

        for group_id, count in group_prices.items():
            group_count = ProductCount.select().where(
                ProductCount.product_group == group_id, ProductCount.count <= count
            ).order_by(ProductCount.count.desc()).first()
            price_per_one = group_count.price / group_count.count
            group_prices[group_id] = price_per_one

        products_info = []
        for product, count in products_counts:
            group_price = product.group_price
            if group_price:
                product_price = count * group_prices[group_price.id]
                product_price = Decimal(product_price).quantize(Decimal('0.01'))
            else:
                product_price = ProductCount.get(product=product, count=count).price
            if for_order:
                name = product.id
            else:
                name = product.title
            products_info.append((name, count, product_price))
        return products_info

    @staticmethod
    def get_product_ids(user_data):
        cart = Cart.check_cart(user_data)
        return cart.keys()

    @staticmethod
    def get_product_count(user_data, product_id):
        cart = Cart.check_cart(user_data)
        if product_id not in cart:
            return 0
        else:
            return cart[product_id]

    @staticmethod
    def not_empty(user_data):
        cart = Cart.check_cart(user_data)
        return len(cart) > 0

    @staticmethod
    def get_product_subtotal(user_data, product_id):
        count = Cart.get_product_count(user_data, product_id)
        product = Product.get(id=product_id)
        if product.group_price:
            subquery = {'product_group': product.group_price}
            # subquery = (ProductCount.product_group == product.group_price)
        else:
            subquery = {'product': product}
        try:
            product_count = ProductCount.get(count=count, **subquery)
        except ProductCount.DoesNotExist:
            price = 0
        else:
            price = product_count.price
        return price

    @staticmethod
    def get_cart_total(user_data):
        products_info = Cart.get_products_info(user_data)
        total = sum((val[-1] for val in products_info))
        return total

    @staticmethod
    def fill_order(user_data, order):
        products = Cart.get_products_info(user_data, for_order=True)
        for p_id, p_count, p_price in products:
            OrderItem.create(order=order, product_id=p_id, count=p_count, total_price=p_price)


def parse_discount(discount_str):
    discount_list = [v.strip() for v in discount_str.split('>')]
    if len(discount_list) == 2:
        discount, discount_min = discount_list
        try:
            discount_num = int(discount.split('%')[0].strip())
            discount_min = int(discount_min)
        except ValueError:
            pass
        else:
            return discount, discount_min
    else:
        try:
            int(discount_str)
        except ValueError:
            return
        return discount_str, 0


def calculate_discount_total(discount, total):
    if discount.endswith('%'):
        discount = discount.replace('%', '').strip()
        discount = round(total / 100 * int(discount))
    return int(discount)


def quantize_btc(val):
    val = Decimal(val).quantize(Decimal('0.000001'))
    return val


# def calculate_btc_comission(val, fixed, ):

def is_vip_customer(bot, user_id):
    if config.vip_customers:
        chat_id = config.vip_customers_channel
        member = bot.getChatMember(chat_id, user_id)
        if member and not member.status == 'left':
            return True


def is_customer(bot, user_id):
    if not config.only_for_customers:
        return True
    chat_id = config.customers_channel
    member = bot.getChatMember(chat_id, user_id)
    if member and not member.status == 'left':
        return True


def is_admin(bot, user_id):
    chat_id = config.service_channel
    member = bot.getChatMember(chat_id, user_id)
    if member and not member.status == 'left':
        return True


# we assume people in service channel can administrate the bot


def get_username(update):
    username = update.effective_user.username
    return username


def get_locale(update):
    language = update.effective_user.language_code
    if language not in ('iw', 'en'):
        language = config.default_language
    return language


def get_user_id(update):
    user_id = update.effective_user.id
    return user_id


def get_trans(user_id):
    user = User.get(telegram_id=user_id)
    locale = user.locale
    return gettext.gettext if locale == 'en' else cat.gettext


def get_channel_trans():
    locale = config.channels_language
    return gettext.gettext if locale == 'en' else cat.gettext


def get_full_product_info(product_id):
    try:
        product = Product.get(id=product_id)
    except Product.DoesNotExist:
        return '', []
    product_title = product.title
    if product.group_price:
        query = (ProductCount.product_group == product.group_price)
    else:
        query = (ProductCount.product == product)
    rows = ProductCount.select(ProductCount.count, ProductCount.price).where(query).tuples()
    return product_title, rows


def get_currency_symbol():
    currency = config.currency
    return Currencies.CURRENCIES[currency][1]


def get_user_update_username(user_id, username):
    user = User.get(telegram_id=user_id)
    if user.username != username:
        user.username = username
        user.save()
    return user


def init_bot_tables():
    for perm, _ in UserPermission.PERMISSIONS:
        try:
            UserPermission.get(permission=perm)
        except UserPermission.DoesNotExist:
            UserPermission.create(permission=perm)

    owner_id = config.owner_id
    if owner_id is None:
        raise AssertionError('Please set Owner ID in config file before starting the bot.')
    try:
        User.get(telegram_id=owner_id)
    except User.DoesNotExist:
        owner_perm = UserPermission.get(permission=UserPermission.OWNER)
        User.create(telegram_id=owner_id, permission=owner_perm)

    btc_creds = BitcoinCredentials.select().first()
    if not btc_creds:
        BitcoinCredentials.create()

    channels_map = {
        'reviews_channel': {'name': 'Reviews channel', 'perms': (1, 2, 3, 4, 5, 6, 7, 8)},
        'service_channel': {'name': 'Service channel', 'perms': (1, 2)},
        'customers_channel': {'name': 'Customers channel', 'perms': (1, 2, 4, 5, 6, 7, 8)},
        'vip_customers_channel': {'name': 'Vip customers channel', 'perms': (1, 2, 7)},
        'couriers_channel': {'name': 'Couriers channel', 'perms': (1, 2, 3)}
    }
    for conf_name, data in channels_map.items():
        try:
            channel = Channel.get(conf_name=conf_name)
        except Channel.DoesNotExist:
            name = data['name']
            perms = data['perms']
            conf_id = conf_name + '_id'
            conf_link = conf_name + '_link'
            channel_id = config.get_config_value(conf_id)
            channel_link = config.get_config_value(conf_link)
            if not channel_link or not channel_id:
                raise AssertionError('Please specify both "{}" and "{}" config values'.format(conf_id, conf_link))
            channel = Channel.create(name=name, channel_id=channel_id, link=channel_link, conf_name=conf_name)
            for val in perms:
                perm = UserPermission.get(permission=val)
                ChannelPermissions.create(channel=channel, permission=perm)


def clear_user_data(user_data, *args):
    values_stored = {key: user_data.get(key) for key in args}
    user_data.clear()
    user_data.update(values_stored)


def fix_markdown(message):
    escape_chars = '*_['
    message = message.replace('`', '\\`')
    for char in escape_chars:
        count = 0
        for c in message:
            if c == char:
                count += 1
        if count % 2 != 0:
            msg_li = message.rsplit(char, 1)
            message = '\\{}'.format(char).join(msg_li)
    return message


cat = gettext.GNUTranslations(open('he.mo', 'rb'))
config = ConfigHelper()


_ = gettext.gettext

logging.basicConfig(stream=sys.stderr, format='%(asctime)s %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
