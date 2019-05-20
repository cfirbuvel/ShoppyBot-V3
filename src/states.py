import random
from datetime import datetime
from decimal import Decimal
from telegram import ParseMode, ReplyKeyboardRemove
from telegram.ext import ConversationHandler
from telegram.utils.helpers import escape_markdown, escape
from peewee import JOIN


from . import keyboards, messages, enums, shortcuts
from .cart_helper import Cart
from .models import Location, User, OrderBtcPayment, Channel, IdentificationStage, UserPermission, CourierLocation, \
    Product, WorkingHours, GroupProductCount, ProductCount, GroupProductCountPermission, Order
from .helpers import config, get_user_id, get_trans, is_vip_customer, is_admin, get_username, \
    get_user_update_username, logger, get_currency_symbol
from .btc_settings import BtcSettings
from .btc_wrapper import CurrencyConverter


#
# state entry functions, use them to enter various stages of checkout
# or return to previous states
#

def enter_unknown_command(_, bot, query):
    logger.info('Unknown command - {}'.format(query.data))
    # msg = _('Unknown command.')
    # bot.send_message(query.message.chat_id, msg)
    query.answer()
    return ConversationHandler.END


def enter_menu(bot, update, user_data, msg_id=None, query_id=None):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    user = User.get(telegram_id=user_id)
    products_info = Cart.get_products_info(user_data, user.currency)
    if products_info:
        msg = messages.create_cart_details_msg(user_id, products_info)
    else:
        first_name = escape_markdown(update.effective_user.first_name)
        msg = config.welcome_text.format(first_name)
    reply_markup = keyboards.main_keyboard(_, user)
    chat_id = update.effective_chat.id
    if msg_id:
        main_msg = bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        main_msg = bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    user_data['menu_id'] = main_msg['message_id']
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_INIT


def enter_registration(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('➡️ Registration')
    reply_markup = keyboards.registration_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_REGISTRATION


def enter_settings_channels(_, bot, chat_id, msg_id, query_id):
    msg = _('⭐ Channels')
    reply_markup = keyboards.channels_settings_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_CHANNELS


def enter_channels(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('⭐ Channels')
    reply_markup = keyboards.channels_settings_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_CHANNELS


def enter_channel_details(_, bot, chat_id, user_data, channel_id, msg_id=None, query_id=None):
    channel = Channel.get(id=channel_id)
    user_data['channel_select'] = channel_id
    name = escape_markdown(channel.name)
    msg = _('{}:').format(name)
    channel_tg_id = channel.channel_id
    if channel_id:
        msg += '\n'
        msg += _('*ID*: {}').format(channel_tg_id)
    link = channel.link
    if link:
        msg += '\n'
        msg += _('*Link*: [{}]').format(link)
    allow_remove = channel.conf_name is None
    reply_markup = keyboards.channel_details_keyboard(_, allow_remove)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_CHANNELS_DETAILS


def enter_settings(_, bot, chat_id, user_id, query_id=None, msg_id=None, msg=None):
    if not msg:
        msg = _('⚙ Bot settings')
    user = User.get(telegram_id=user_id)
    reply_markup = keyboards.bot_settings_keyboard(_, user)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.ADMIN_BOT_SETTINGS


def enter_settings_users(_, bot, chat_id, msg_id, query_id):
    msg = _('👨 Users')
    reply_markup = keyboards.clients_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_USERS


def enter_settings_registered_users_perms(_, bot, chat_id, msg_id, query_id, msg=None):
    if not msg:
        msg = _('👩 Select permission')
        # msg = _('👩 Registered users')
    registered_perms = (UserPermission.OWNER, UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION)
    statuses = UserPermission.select().join(User)\
        .where(User.id != None, UserPermission.permission.not_in(registered_perms)).group_by(UserPermission.permission)
    statuses = [(status.get_permission_display(), status.id) for status in statuses]

    # users = User.select(User.username, User.id).join(UserPermission) \
    #     .where(UserPermission.permission.not_in(registered_perms), User.banned == False).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, statuses)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_REGISTERED_USERS_PERMS


def enter_settings_registered_users(_, bot, chat_id, perm, msg_id, query_id, page=1, msg=None):
    if not msg:
        msg = _('👩 Registered users')
    users = User.select(User.username, User.id).where(User.permission == perm, User.banned == False).tuples()
    # users = User.select(User.username, User.id).join(UserPermission) \
    #     .where(UserPermission.permission.not_in(registered_perms), User.banned == False).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, users, page_num=page)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_REGISTERED_USERS


def enter_registered_users_select(_, bot, chat_id, msg, query_id, msg_id=None):
    reply_markup = keyboards.registered_user_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_REGISTERED_USERS_SELECT


def enter_pending_registrations(_, bot, chat_id, msg_id, query_id, page=1, msg=None):
    if not msg:
        msg = _('🙋‍ Pending registrations')
    users = User.select(User.username, User.id).join(UserPermission) \
        .where(UserPermission.permission == UserPermission.PENDING_REGISTRATION, User.banned == False).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, users, page_num=page)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_PENDING_REGISTRATIONS


def enter_pending_registrations_user(_, bot, chat_id, msg_id, query_id, user_data, user_id):
    user = User.get(id=user_id)
    bot.delete_message(chat_id, msg_id)
    answers_ids = shortcuts.send_user_identification_answers(bot, chat_id, user)
    user_data['user_id_messages'] = answers_ids
    msg = _('*Phone number*: {}').format(user.phone_number)
    reply_markup = keyboards.pending_user_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_PENDING_REGISTRATIONS_USER


def enter_black_list(_, bot, chat_id, msg_id, query_id, page=1, msg=None):
    if not msg:
        msg = _('🔒 Black-list')
    users = User.select(User.username, User.id).join(UserPermission)\
        .where(User.banned == True, UserPermission.permission != UserPermission.OWNER).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, users, page_num=page)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_BLACK_LIST


def enter_courier_detail(_, bot, chat_id, msg_id, query_id, courier_id):
    courier = User.get(id=courier_id)
    locations = CourierLocation.filter(user=courier)
    username = escape_markdown(courier.username)
    if locations:
        locations = [item.location.title for item in locations]
        locations_msg = escape_markdown(', '.join(locations))
    else:
        locations_msg = _('_Courier don\'t have any locations yet_')
    msg = _('Username: *{}*').format(username)
    msg += '\n'
    msg += _('Telegram ID: {}').format(courier.telegram_id)
    msg += '\n'
    msg += _('Locations:')
    msg += '\n'
    msg += locations_msg
    reply_markup = keyboards.courier_details_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_COURIER_DETAIL


def enter_order_options(_, bot, chat_id, msg_id=None, query_id=None, msg=None):
    if not msg:
        msg = _('💳 Order options')
    reply_markup = keyboards.order_options_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.ADMIN_ORDER_OPTIONS


def enter_courier_warehouse_detail(_, bot, chat_id, warehouse, msg_id=None, query_id=None):
    product_title = escape_markdown(warehouse.product.title)
    msg = _('Product: `{}`').format(product_title)
    msg += '\n'
    msg += _('Credits: `{}`').format(warehouse.product.credits)
    msg += '\n'
    msg += _('Courier credits: `{}`').format(warehouse.count)
    reply_markup = keyboards.edit_back_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_COURIER_WAREHOUSE_DETAIL


def enter_courier_warehouse_products(_, bot, chat_id, msg_id, query_id, page=1):
    active_products = Product.select(Product.title, Product.id) \
        .where(Product.warehouse_active == True, Product.is_active == True).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, active_products, page_num=page)
    msg = _('Please select product')
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_COURIER_WAREHOUSE_PRODUCTS


def enter_warehouse_products(_, bot, chat_id, msg_id, query_id, page):
    products = Product.filter(is_active=True)
    products = [(product.title, product.id) for product in products]
    msg = _('Select product to manage credits')
    products_keyboard = keyboards.general_select_one_keyboard(_, products, page_num=page)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=products_keyboard)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_WAREHOUSE_PRODUCTS


def enter_warehouse(_, bot, chat_id, product, msg_id=None, query_id=None):
    product_title = product.title.replace('*', '')
    product_title = escape_markdown(product_title)
    msg = _('🏗Product: `{}`').format(product_title)
    msg += '\n'
    msg += _('Credits: `{}`').format(product.credits)
    reply_markup = keyboards.warehouse_keyboard(_, product.warehouse_active)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_WAREHOUSE


def enter_warehouse_couriers(_, bot, chat_id, msg_id, query_id, page):
    couriers = User.select(User.username, User.id).join(UserPermission) \
        .where(UserPermission.permission == UserPermission.COURIER, User.banned == False).tuples()
    couriers_keyboard = keyboards.general_select_one_keyboard(_, couriers, page_num=page)
    bot.edit_message_text(_('Select a courier'), chat_id, msg_id, reply_markup=couriers_keyboard)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_WAREHOUSE_COURIERS


def enter_warehouse_courier_detail(_, bot, chat_id, warehouse, msg_id=None, query_id=None):
    product_title = warehouse.product.title.replace('*', '')
    product_title = escape_markdown(product_title)
    courier_username = escape_markdown(warehouse.courier.username)
    msg = _('Product: `{}`').format(product_title)
    msg += '\n'
    msg += _('Courier: `{}`').format(courier_username)
    msg += '\n'
    msg += _('Credits: `{}`').format(warehouse.count)
    reply_markup = keyboards.edit_back_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_WAREHOUSE_COURIER_DETAIL


def enter_delivery_fee(_, bot, chat_id, msg_id, query_id):
    msg = _('🚕 Delivery fee')
    reply_markup = keyboards.delivery_fee_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_DELIVERY_FEE


def enter_delivery_fee_add(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('➕ Add delivery fee')
    reply_markup = keyboards.delivery_fee_add_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_DELIVERY_FEE_ADD


def enter_delivery_fee_enter(_, bot, chat_id, location_id=None, msg_id=None, query_id=None):
    if location_id:
        location = Location.get(id=location_id)
    else:
        location = None
    msg = messages.create_delivery_fee_msg(_, location)
    reply_markup = keyboards.cancel_button(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_DELIVERY_FEE_ENTER


def enter_delivery_fee_location(_, bot, chat_id, msg_id=None, query_id=None, page=None):
    msg = _('Select location:')
    locations = Location.select(Location.title, Location.id).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, locations, page_num=page)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.ADMIN_DELIVERY_FEE_LOCATION


def enter_locations(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('🎯 Locations')
    reply_markup = keyboards.locations_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_LOCATIONS


def enter_locations_view(_, bot, chat_id, msg_id, query_id, page, msg=None):
    if not msg:
        msg = _('🎯 My locations')
    locations = Location.select(Location.title, Location.id).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, locations, page_num=page)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_LOCATIONS_VIEW


def enter_working_days(_, bot, chat_id, msg_id=None, query_id=None, msg=None):
    if not msg:
        msg = _('Please select working day')
        msg += '\n'
        msg += _('Current working hours:')
        msg += '\n'
        msg += messages.get_working_hours_msg(_)
    days = [(day[1], day[0]) for day in WorkingHours.DAYS]
    reply_markup = keyboards.general_select_one_keyboard(_, days)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.ADMIN_EDIT_WORKING_HOURS


def enter_delivery_options(_, bot, chat_id, msg_id, query_id):
    msg = _('🚕 Delivery')
    reply_markup = keyboards.delivery_options_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_DELIVERY


def enter_order_delivery(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('Please choose pickup or delivery')
    reply_markup = keyboards.create_delivery_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_CHECKOUT_SHIPPING


def enter_order_locations(_, bot, chat_id, action, msg_id=None, query_id=None, page_num=1):
    if action == Order.PICKUP:
        msg = _('Please select location to pickup')
    else:
        msg = _('Please select courier location')
    locations = Location.select(Location.title, Location.id).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, locations, page_num, cancel=True)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_CHECKOUT_LOCATION


def enter_order_delivery_address(_, bot, chat_id, query_id=None):
    msg = _('Please enter delivery address as text or send a location.')
    reply_markup = keyboards.location_request_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_CHECKOUT_ADDRESS


def enter_order_shipping_time(_, bot, chat_id, action, user_data, order_now, msg_id=None, query_id=None):
    if action == Order.PICKUP:
        msg = _('Please select day when you want to pickup order')
    else:
        msg = _('Please select delivery day')
    if not order_now:
        msg += '\n'
        msg += messages.get_working_hours_msg(_)
        state = enums.BOT_CHECKOUT_DATE_SELECT
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query_id, msg, True)
    reply_markup = keyboards.order_select_time_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_CHECKOUT_DATETIME_SELECT


def enter_order_phone_number(_, bot, chat_id, query_id=None):
    msg = _('Please enter or send phone number')
    reply_markup = keyboards.phone_number_request_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_CHECKOUT_PHONE_NUMBER


def enter_order_identify(_, bot, chat_id, user_data, id_stages, msg=None, msg_id=None, query_id=None):
    first_stage = id_stages[0]
    questions = first_stage.identification_questions
    question = random.choice(list(questions))
    user_data['order_details']['identification'] = {'passed_ids': [], 'current_id': first_stage.id, 'current_q_id': question.id,'answers': []}
    if not msg:
        msg = _('Please complete identification stages')
        msg += '\n\n'
    else:
        msg = ''
    msg += question.content
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.back_cancel_keyboard(_))
    else:
        bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_CHECKOUT_IDENTIFY


def enter_order_payment_type(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('Please select payment type.')
    reply_markup = keyboards.select_order_payment_type(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_CHECKOUT_PAYMENT_TYPE


def enter_btc_conversion_failed(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('Failed to get BTC conversion rates.')
    reply_markup = keyboards.btc_operation_failed_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_BTC_CONVERSION_FAILED


def enter_generating_address_failed(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('Failed to create BTC address to process payment.')
    reply_markup = keyboards.btc_operation_failed_keyboard(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_GENERATING_ADDRESS_FAILED


def enter_btc_too_low(_, bot, chat_id, msg_id=None, query_id=None):
    msg = _('Order total is too low. Please make sure it\'s greater than *{}* BTC').format(BtcSettings.DEFAULT_COMISSION)
    reply_markup = keyboards.btc_operation_failed_keyboard(_, retry=False)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_BTC_TOO_LOW


def enter_order_confirmation(_, bot, chat_id, user_data, user_id, msg_id=None, query_id=None):
    user = User.get(telegram_id=user_id)
    total = Cart.get_cart_total(user_data, user.currency)
    products_info = Cart.get_products_info(user_data, user.currency)
    order_details = user_data['order_details']
    btc_payment = order_details.get('btc_payment')
    location_id = order_details.get('location_id')
    try:
        location = Location.get(id=location_id)
    except Location.DoesNotExist:
        location = None
    delivery_fee = shortcuts.calculate_delivery_fee(order_details['delivery'], location, total, user.is_vip_client)
    if delivery_fee:
        delivery_fee = CurrencyConverter.convert_currencies(delivery_fee, config.currency, user.currency)
    text, btc_value = messages.create_confirmation_text(user_id, order_details, total, products_info, delivery_fee)
    if btc_payment:
        if not btc_value:
            enter_btc_conversion_failed(_, bot, chat_id, msg_id, query_id)
        if btc_value <= Decimal(BtcSettings.DEFAULT_COMISSION):
            enter_btc_too_low(_, bot, chat_id, msg_id, query_id)
        user_data['order_details']['btc_value'] = str(btc_value)
    reply_markup = keyboards.confirmation_keyboard(_)
    if msg_id:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.BOT_ORDER_CONFIRMATION


def enter_price_groups_list(_, bot, chat_id, msg_id, query_id, msg=None, page=1):
    groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
    keyboard = keyboards.general_select_one_keyboard(_, groups, page_num=page)
    if not msg:
        msg = _('Please select a price group:')
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_PRODUCT_PRICE_GROUP_LIST


def enter_price_group_selected(_, bot, chat_id, group_id, msg_id=None, query_id=None):
    group = GroupProductCount.get(id=group_id)
    product_counts = ProductCount.select(ProductCount.count, ProductCount.price) \
        .where(ProductCount.product_group == group).tuples()
    products = Product.select(Product.title).where(Product.group_price == group)
    group_name = escape(group.name)
    msg = _('Product price group:\n<i>{}</i>').format(group_name)
    msg += '\n\n'
    msg += _('Prices configured for this group:')
    msg += '\n'
    currency_sym = get_currency_symbol()
    for count, price in product_counts:
        msg += '{} x {}{}\n'.format(count, price, currency_sym)
    msg += '\n'
    msg += _('Products in this group price:')
    msg += '\n'
    for p in products:
        product_title = escape(p.title)
        msg += '<i>{}</i>'.format(product_title)
        msg += '\n'
    msg += '\n'
    msg += _('Special clients:')
    msg += '\n'
    permissions = GroupProductCountPermission.select().where(GroupProductCountPermission.price_group == group)
    if len(permissions):
        msg += ', '.join(group_perm.permission.get_permission_display() for group_perm in permissions)
    else:
        msg += 'All clients'
    keyboard = keyboards.create_product_price_group_selected_keyboard(_, group.id)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    if query_id:
        bot.answer_callback_query(query_id)
    return enums.ADMIN_PRODUCT_PRICE_GROUP_SELECTED


def enter_statistics_user_select(_, bot, chat_id, msg_id, query_id, page=1, msg=None):
    if msg is None:
        msg = _('Select user')
    client_perms = [
        UserPermission.AUTHORIZED_RESELLER, UserPermission.FRIEND, UserPermission.VIP_CLIENT,
        UserPermission.CLIENT, UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION,
        # comment out this
        UserPermission.OWNER, UserPermission.COURIER
    ]
    users = User.select(User.username, User.id).join(UserPermission) \
        .where(User.banned == False, UserPermission.permission.in_(client_perms)).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, users, page)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    bot.answer_callback_query(query_id)
    return enums.ADMIN_STATISTICS_USER_SELECT


def enter_courier_main_menu(_, bot, chat_id, user, order, msg_id=None, query_id=None, return_state=True):
    try:
        btc_data = OrderBtcPayment.get(order=order)
    except OrderBtcPayment.DoesNotExist:
        btc_data = None
    msg = messages.create_service_notice(_, order, btc_data, for_courier=True)
    reply_markup = keyboards.courier_order_status_keyboard(_, order.id, user)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    if return_state:
        return enums.COURIER_STATE_INIT