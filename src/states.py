import random
from datetime import datetime
from decimal import Decimal
from telegram import ParseMode, ReplyKeyboardRemove
from telegram.ext import ConversationHandler
from telegram.utils.helpers import escape_markdown


from . import keyboards, messages, enums, shortcuts
# from .admin import is_admin
from .models import Location, User, OrderBtcPayment, Channel, IdentificationStage, UserPermission, CourierLocation, \
    Product, WorkingHours
from .helpers import Cart, config, get_user_id, get_trans, is_vip_customer, is_admin, get_username, \
    get_user_update_username, logger
from .btc_settings import BtcSettings


#
# state entry functions, use them to enter various stages of checkout
# or return to previous states
#

def enter_unknown_command(_, bot, query):
    logger.info('Unknown command - {}'.format(query.data))
    msg = _('Unknown command.')
    bot.send_message(query.message.chat_id, msg)
    query.answer()
    return ConversationHandler.END


def enter_menu(bot, update, user_data, msg_id=None, query_id=None):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    user = User.get(telegram_id=user_id)
    products_info = Cart.get_products_info(user_data)
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


def enter_settings_registered_users(_, bot, chat_id, msg_id, query_id, page=1, msg=None):
    if not msg:
        msg = _('👩 Registered users')
    registered_perms = (UserPermission.OWNER, UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION)
    users = User.select(User.username, User.id).join(UserPermission) \
        .where(UserPermission.permission.not_in(registered_perms), User.banned == False).tuples()
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
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
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
    users = User.select(User.username, User.id).where(User.banned == True).tuples()
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


def enter_order_options(_, bot, chat_id, msg_id, query_id):
    msg = _('💳 Order options')
    reply_markup = keyboards.order_options_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
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


def enter_courier_warehouse_products(_, bot, chat_id, msg_id, query_id, page):
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


def enter_delivery_fee_enter(_, bot, chat_id, msg_id=None, query_id=None):
    msg = messages.create_delivery_fee_msg(_)
    reply_markup = keyboards.cancel_button(_)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_DELIVERY_FEE_ENTER


def enter_delivery_fee_location(_, bot, chat_id, page, msg_id=None, query_id=None):
    msg = _('Select location:')
    locations = Location.select(Location.title, Location.id).tuples()
    reply_markup = keyboards.general_select_one_keyboard(_, locations, page_num=page)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        bot.answer_callback_query(query_id)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
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
    if action == 'pickup':
        msg = _('Please select location to pickup')
    else:
        msg = _('Please select courier location')
    locations = Location.select(Location.title, Location.id)
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
    if action == 'pickup':
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
    total = Cart.get_cart_total(user_data)
    products_info = Cart.get_products_info(user_data)
    order_details = user_data['order_details']
    btc_payment = order_details.get('btc_payment')
    text, btc_value = messages.create_confirmation_text(user_id, order_details, total, products_info)
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


# def enter_state_init_order_confirmed(bot, update, user_data, order):
#     user_id = get_user_id(update)
#     total = cart.get_cart_total(get_user_session(user_id))
#     _ = get_trans(user_id)
#     chat_id = update.message.chat_id
#     if order.btc_payment:
#         btc_data = OrderBtcPayment.get(order=order)
#         msg = _('Please transfer *{}* BTC to address:').format(btc_data.amount)
#         msg += '\n'
#         msg += _('*{}*').format(btc_data.address)
#         bot.send_message(chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
#     user = User.get(telegram_id=user_id)
#     first_name = escape_markdown(update.efective_user.first_name)
#     bot.send_message(
#         chat_id,
#         text=config.get_order_complete_text().format(
#             update.effective_user.first_name),
#         reply_markup=ReplyKeyboardRemove(),
#     )
#     bot.send_message(
#         chat_id,
#         text='〰〰〰〰〰〰〰〰〰〰〰〰️',
#         reply_markup=main_keyboard(_, config.get_reviews_channel(), user, is_admin(bot, user_id), total),
#     )
#
#     return BOT_STATE_INIT

