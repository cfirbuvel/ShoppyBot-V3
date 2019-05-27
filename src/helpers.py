import configparser
from configparser import NoOptionError
import datetime
import gettext
import json
import logging
import sys
import time
import re

from collections import defaultdict
from decimal import Decimal

import redis

from telegram import TelegramError

# from .btc_wrapper import CurrencyConverter
from .models import ProductCount, Product, User, OrderItem, Currencies, ConfigValue, UserPermission,\
    BitcoinCredentials, Channel, ChannelPermissions, CurrencyRates, Location, Order, CourierChat


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
                      'contact_info': 'Contact info not configured yet',
                      'phone_number_required': 'true',
                      'has_courier_option': 'true',
                      'only_for_registered': 'true', 'watch_non_registered': 'false',
                      'order_non_registered': 'false',
                      'delivery_method': 'both', 'delivery_fee': '0',
                      'delivery_fee_for_vip': 'false', 'discount': '0',
                      'discount_min': '0', 'btc_enabled': 'false',
                      'btc_address': '', 'currency': Currencies.DOLLAR,
                      'currencies_api_key': '7405b1ae5a19aefdad05fe182b8e62b7',
                      'lottery_messages': 'false',
                      'lottery_messages_interval': '2',
                      'lottery_messages_sent': ''})
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
            try:
                value = self.config.get(self.section, name)
            except NoOptionError:
                return
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

    def get_datetime_value(self, name):
        value = config.get_config_value(name)
        if value:
            format = '%Y-%m-%d %H-%M-%S'
            value = datetime.datetime.strptime(value, format)
            return value

    def set_datetime_value(self, name, value):
        format = '%Y-%m-%d %H-%M-%S'
        value = value.strftime(format)
        self.set_value(name, value)

    @property
    def lottery_messages(self):
        return self.get_config_value('lottery_messages', boolean=True)

    @property
    def lottery_messages_sent(self):
        return self.get_datetime_value('lottery_messages_sent')

    @property
    def lottery_messages_interval(self):
        return self.get_config_value('lottery_messages_interval', conversion=int)

    @property
    def currencies_api_key(self):
        return self.get_config_value('currencies_api_key')

    @property
    def currencies_last_updated(self):
        return self.get_datetime_value('currencies_last_updated')

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
    def username_gif(self):
        return self.get_config_value('username_gif')

    # @property
    # def working_hours(self):
    #     hours = self.get_config_value('working_hours')
    #     format = ''
    #     hours = datetime.datetime.strptime(hours, )
    #     return self.get_config_value('working_hours')

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
    def watch_non_registered(self):
        return self.get_config_value('watch_non_registered', boolean=True)

    @property
    def order_non_registered(self):
        return self.get_config_value('order_non_registered', boolean=True)

    @property
    def has_courier_option(self):
        return self.get_config_value('has_courier_option', boolean=True)

    @property
    def pickup(self):
        return self.get_config_value('pickup', boolean=True)

    @property
    def delivery_method(self):
        return self.get_config_value('delivery_method')

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


def calculate_discount_percents(discount, total):
    if discount.endswith('%'):
        discount = discount.replace('%', '').strip()
        discount = round(total / 100 * int(discount))
    return int(discount)


def calculate_discount(total):
    discount = config.discount
    discount_min = config.discount_min
    if discount_min != 0:
        discount = calculate_discount_percents(discount, total)
        if discount and total >= discount_min:
            return discount
    return 0


# def get_discount():
#     discount = config.discount


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
    print(locale)
    return gettext.gettext if locale == 'en' else cat.gettext


def get_currency_symbol():
    currency = config.currency
    return Currencies.CURRENCIES[currency][1]


def get_user_update_username(user_id, username):
    user = User.get(telegram_id=user_id)
    if user.username != username:
        user.username = username
        user.save()
    return user


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


def get_service_channel():
    return Channel.get(conf_name='service_channel').channel_id


def get_reviews_channel():
    return Channel.get(conf_name='reviews_channel').channel_id


def get_couriers_channel():
    return Channel.get(conf_name='couriers_channel').channel_id


def send_state(state, user_data):
    user_data['current_state'] = state
    return state


cat = gettext.GNUTranslations(open('he.mo', 'rb'))
config = ConfigHelper()


_ = gettext.gettext

logging.basicConfig(stream=sys.stderr, format='%(asctime)s %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
