import random
from decimal import Decimal
from telegram import ParseMode, ReplyKeyboardRemove
from telegram.ext import ConversationHandler
from telegram.utils.helpers import escape_markdown


from . import keyboards, messages, enums, shortcuts
# from .admin import is_admin
from .models import Location, User, OrderBtcPayment, Channel, IdentificationStage, UserPermission, CourierLocation, \
    Product
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


# def enter_settings(bot, update):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     user = User.get(telegram_id=user_id)
#     chat_id, msg_id = update.effective_chat.id, update.callback_query.message.message_id
#     msg = _('⚙ Bot settings')
#     reply_markup = keyboards.bot_settings_keyboard(_, user)
#     bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
#     return enums.ADMIN_BOT_SETTINGS


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
    msg = '*Phone number*: {}'.format(user.phone_number)
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
    reply_markup = keyboards.delivery_fee_keyboard(_, config.delivery_fee_for_vip)
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


# def enter_state_identification(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     identification_stages = IdentificationStage.filter(active=True)
#     if len(identification_stages):
#         first_stage = identification_stages[0]
#         questions = first_stage.identification_questions
#         question = random.choice(list(questions))
#         user_data['order_identification'] = {'passed_ids': [], 'current_id': first_stage.id, 'current_q_id': question.id,'answers': []}
#         msg = escape_markdown(question.content)
#         bot.send_message(update.message.chat_id, msg, reply_markup=keyboards.create_cancel_keyboard(_))
#
#
# def enter_state_shipping_method(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     update.message.reply_text(text=_('Please choose pickup or delivery:'),
#                               reply_markup=create_shipping_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN, )
#     return BOT_CHECKOUT_SHIPPING
#
#
# def enter_state_courier_location(bot, update, user_data):
#     locations = Location.select()
#     location_names = [x.title for x in locations]
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     update.message.reply_text(
#         text=_('Please choose where do you want to pickup your order:'),
#         reply_markup=create_pickup_location_keyboard(_, location_names),
#         parse_mode=ParseMode.MARKDOWN, )
#     return BOT_CHECKOUT_LOCATION_PICKUP
#
#
# def enter_state_location_delivery(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     update.message.reply_text(
#         text=_('Please enter delivery address as text or send a location.'),
#         reply_markup=create_location_request_keyboard(_),
#         parse_mode=ParseMode.MARKDOWN)
#     return BOT_CHECKOUT_LOCATION_DELIVERY
#
#
# def enter_state_shipping_time(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     update.message.reply_text(text=_('When do you want to pickup your order?'),
#                               reply_markup=create_time_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN, )
#     return BOT_CHECKOUT_TIME
#
#
# def enter_state_shipping_time_text(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     update.message.reply_text(text=_(
#         'When do you want your order delivered? Please send the time as text.'),
#         reply_markup=create_cancel_keyboard(_),
#         parse_mode=ParseMode.MARKDOWN, )
#     return BOT_CHECKOUT_TIME_TEXT
#
#
# def enter_state_phone_number_text(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     update.message.reply_text(text=_('Please send your phone number.'),
#                               reply_markup=create_phone_number_request_keyboard(_),
#                               )
#     return BOT_CHECKOUT_PHONE_NUMBER
#
#
# def enter_state_order_confirm(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     is_pickup = user_data['shipping']['method'] == _('🏪 Pickup')
#     shipping_data = user_data['shipping']
#     total = cart.get_cart_total(user_data)
#     delivery_for_vip = config.delivery_fee_for_vip
#     product_info = cart.get_products_info(user_data)
#     user_data['shipping']['vip'] = is_vip_customer(bot, user_id)
#     btc_payment = user_data['shipping'].get('btc_payment')
#     if btc_payment:
#         text, btc_value = create_confirmation_text(user_id, is_pickup, shipping_data, total,
#                                                    delivery_for_vip, product_info, btc_payment)
#         if not btc_value:
#             enter_state_btc_conversion_failed(bot, update, user_data)
#         if btc_value <= Decimal(BtcSettings.DEFAULT_COMISSION):
#             enter_state_btc_too_low(bot, update, user_data)
#         user_data['shipping']['btc_value'] = str(btc_value)
#     else:
#         text, btc_value = create_confirmation_text(user_id, is_pickup, shipping_data, total,
#                                                    delivery_for_vip, product_info)
#     session_client.json_set(user_id, user_data)
#     keyboard = create_confirmation_keyboard(_)
#     update.message.reply_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
#     return BOT_ORDER_CONFIRMATION
#
#
# def enter_state_select_payment_type(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     update.message.reply_text(text=_('Please select payment type.'), reply_markup=create_select_order_payment_type(_))
#     return BOT_SELECT_PAYMENT_TYPE
#
#
# def enter_state_btc_conversion_failed(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     text = _('Failed to get BTC conversion rates.')
#     keyboard = create_btc_operation_failed_keyboard(_)
#     update.message.reply_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
#     return BOT_BTC_CONVERSION_FAILED
#
#
# def enter_state_btc_too_low(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     text = _('Order total is too low. Please make sure it\'s greater than *{}* BTC').format(BtcSettings.DEFAULT_COMISSION)
#     keyboard = create_btc_operation_failed_keyboard(_, retry=False)
#     update.message.reply_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
#     return BOT_BTC_TOO_LOW
#
#
# def enter_state_generating_address_failed(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     text = _('Failed to create BTC address to process payment.')
#     keyboard = create_btc_operation_failed_keyboard(_)
#     update.message.reply_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
#     return BOT_GENERATING_ADDRESS_FAILED
#
#
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
#
#
# def enter_state_init_order_cancelled(bot, update, user_data, msg=None):
#     user_data['cart'] = {}
#     user_data['shipping'] = {}
#     user_data['order_identification'] = {}
#     user_id = get_user_id(update)
#     username = get_username(update)
#     _ = get_trans(user_id)
#     user = get_user_update_username(user_id, username)
#     if not msg:
#         msg = _('Order cancelled.')
#     chat_id, msg_id = update.effective_chat.id, update.callback_query.message.id
#     bot.edit_message_text(msg, chat_id, msg_id)
#     admin = is_admin(bot, user_id)
#     first_name = escape_markdown(update.effective_user.first_name)
#     msg = config.welcome_text.format(first_name)
#     reply_markup = keyboards.main_keyboard(_, user, admin)
#     bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
#     if admin:
#         log_msg = 'Admin Cancel order process - From admin_id: %s, username: @%s'
#     else:
#         log_msg = 'Cancel order process - From user_id: %s, username: @%s'
#     logger.info(log_msg, user_id, username)
#     return BOT_STATE_INIT
