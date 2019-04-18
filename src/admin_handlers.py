from decimal import Decimal, InvalidOperation
import threading

from telegram import ParseMode
from telegram import ReplyKeyboardRemove
from telegram.error import TelegramError
from telegram.ext import ConversationHandler
from telegram.utils.helpers import escape_markdown, escape

from . import enums, keyboards, shortcuts, messages, states
from . import shortcuts
from . import messages
from .btc_wrapper import wallet_enable_hd
from .decorators import user_passes
# from .btc_processor import process_btc_payment, set_btc_proc
from .helpers import get_user_id, config, get_trans, parse_discount, get_channel_trans, get_locale, get_username,\
    logger, is_admin, fix_markdown, init_bot_tables
from .models import Product, ProductCount, Location, ProductWarehouse, User, \
    ProductMedia, ProductCategory, IdentificationStage, Order, IdentificationQuestion, \
    ChannelMessageData, GroupProductCount, delete_db, create_tables, Currencies, BitcoinCredentials, \
    Channel, UserPermission, ChannelPermissions, CourierLocation


def on_cmd_add_product(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    update.message.reply_text(
        text=_('Enter new product title'),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return enums.ADMIN_TXT_PRODUCT_TITLE


@user_passes
def on_settings_menu(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if data == 'settings_statistics':
        msg = _('📈 Statistics')
        reply_markup = keyboards.statistics_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS
    elif data == 'settings_bot':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    elif data == 'settings_back':
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)

#
# def on_statistics_general(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, val = query.data.split('|')
#     chat_id, message_id = query.message.chat_id, query.message.message_id
#     if action == 'back':
#         bot.edit_message_text(chat_id=chat_id,
#                               message_id=message_id,
#                               text=_('📈 Statistics'),
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#     elif action == 'ignore':
#         return enums.ADMIN_STATISTICS_GENERAL
#     else:
#         year, month = user_data['calendar_date']
#         subquery = shortcuts.get_order_subquery(action, val, month, year)
#         count, price, product_text = shortcuts.get_order_count_and_price((Order.delivered == True),
#                                                                          (Order.canceled == False), *subquery)
#         cancel_count, cancel_price, cancel_product_text = shortcuts.get_order_count_and_price((Order.canceled == True),
#                                                                                               *subquery)
#         message = _('✅ <b>Total confirmed orders</b>\nCount: {}\n{}\n<b>Total cost: {}₪</b>').format(
#             count, product_text, price)
#         message += '\n\n'
#         message += _('❌ <b>Total canceled orders</b>\nCount: {}\n<b>Total cost: {}₪</b>').format(
#             cancel_count, cancel_price)
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message,
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.HTML)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#
#
# def on_statistics_courier_select(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, val = query.data.split('|')
#     chat_id, message_id = query.message.chat_id, query.message.message_id
#     if action == 'back':
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                               text=_('📈 Statistics'),
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#     elif action == 'page':
#         current_page = int(val)
#         couriers = Courier.select(Courier.username, Courier.id).where(Courier.is_active == True).tuples()
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                               text=_('Select a courier:'),
#                               reply_markup=general_select_one_keyboard(_, couriers, current_page),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS_COURIERS
#     else:
#         user_data['statistics'] = {'courier_id': val}
#         state = enums.ADMIN_STATISTICS_COURIERS_DATE
#         shortcuts.initialize_calendar(bot, user_data, chat_id, message_id, state, _, query.id)
#         return state
#
#
# def on_statistics_couriers(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, val = query.data.split('|')
#     chat_id, message_id = query.message.chat_id, query.message.message_id
#     try:
#         courier_id = user_data['statistics']['courier_id']
#     except KeyError:
#         action = 'back'
#     if action == 'back':
#         couriers = Courier.select(Courier.username, Courier.id).where(Courier.is_active == True).tuples()
#         msg = _('Select a courier:')
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                               text=msg, reply_markup=general_select_one_keyboard(_, couriers),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS_COURIERS
#     elif action == 'ignore':
#         return enums.ADMIN_STATISTICS_COURIERS_DATE
#     else:
#         courier = Courier.get(id=courier_id)
#         year, month = user_data['calendar_date']
#         subquery = shortcuts.get_order_subquery(action, val, month, year)
#         count, price, product_text = shortcuts.get_order_count_and_price(
#             (Order.delivered == True), (Order.canceled == False), (Order.courier == courier), *subquery)
#         courier_username = escape(courier.username)
#         message = _('<b>✅ Total confirmed orders for Courier</b> @{}\nCount: {}\n<b>Total cost: {}₪</b>').format(
#             courier_username, count, price)
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message,
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.HTML)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#
#
# def on_statistics_locations_select(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, val = query.data.split('|')
#     chat_id, message_id = query.message.chat_id, query.message.message_id
#     if action == 'back':
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                               text=_('📈 Statistics'),
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#     elif action == 'page':
#         current_page = int(val)
#         locations = Location.select(Location.title, Location.id).tuples()
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                               text=_('Select location:'),
#                               reply_markup=general_select_one_keyboard(_, locations, current_page),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS_LOCATIONS
#     else:
#         user_data['statistics'] = {'location_id': val}
#         state = enums.ADMIN_STATISTICS_LOCATIONS_DATE
#         shortcuts.initialize_calendar(bot, user_data, chat_id, message_id, state, _, query.id)
#         return state
#
#
# def on_statistics_locations(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, val = query.data.split('|')
#     chat_id, message_id = query.message.chat_id, query.message.message_id
#     try:
#         location_id = user_data['statistics']['location_id']
#     except KeyError:
#         action = 'back'
#     if action == 'back':
#         locations = Location.select(Location.title, Location.id).tuples()
#         msg = _('Select location:')
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                               text=msg, reply_markup=general_select_one_keyboard(_, locations),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS_LOCATIONS
#     elif action == 'ignore':
#         return enums.ADMIN_STATISTICS_LOCATIONS_DATE
#     else:
#         location = Location.get(id=location_id)
#         year, month = user_data['calendar_date']
#         subquery = shortcuts.get_order_subquery(action, val, month, year)
#         count, price, product_text = shortcuts.get_order_count_and_price((Order.delivered == True),
#                                                                          (Order.canceled == False),
#                                                                          (Order.location == location), *subquery)
#         location_title = escape(location.title)
#         message = _('✅ <b>Total confirmed orders for Location</b> <code>{}</code>\nCount: {}\n<b>Total cost: {}₪</b>').format(
#             location_title, count, price)
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message,
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.HTML)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#
#
# def on_statistics_username(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     if query and query.data == 'back':
#         msg = _('📈 Statistics')
#         bot.edit_message_text(msg, query.message.chat_id, query.message.message_id,
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#     username = update.message.text
#     users_ids = list(User.select(User.id).where(User.username == username))
#     chat_id, message_id = update.message.chat_id, update.message.message_id
#     if not users_ids:
#         username = escape_markdown(username)
#         msg = _('User `{}` was not found').format(username)
#         bot.send_message(chat_id=chat_id,
#                               text=msg, reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN)
#         return enums.ADMIN_STATISTICS
#     else:
#         user_data['statistics'] = {'users_ids': users_ids}
#         state = enums.ADMIN_STATISTICS_USER_DATE
#         shortcuts.initialize_calendar(bot, user_data, chat_id, message_id, state, _)
#         return state
#
#
# def on_statistics_user(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, val = query.data.split('|')
#     chat_id, message_id = query.message.chat_id, query.message.message_id
#     try:
#         user_ids = user_data['statistics']['users_ids']
#     except KeyError:
#         action = 'back'
#     if action == 'back':
#         msg = _('Enter username:')
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=msg, reply_markup=cancel_button(_))
#         return enums.ADMIN_STATISTICS_USER
#     elif action == 'ignore':
#         return enums.ADMIN_STATISTICS_USER_DATE
#     else:
#         users = User.filter(User.id.in_(user_ids))
#         text = ''
#         year, month = user_data['calendar_date']
#         subquery = shortcuts.get_order_subquery(action, val, month, year)
#         for user in users:
#             count, price, product_text = shortcuts.get_order_count_and_price((Order.delivered == True),
#                                                                              (Order.canceled == False),
#                                                                              (Order.user == user), *subquery)
#             cancel_count, cancel_price, cancel_product_text = shortcuts.get_order_count_and_price(
#                 (Order.canceled == True), *subquery)
#             username = escape(user.username)
#             message = _('✅ <b>Total confirmed orders for client</b> @{}\nCount: {}\n<b>Total cost: {}₪</b>').format(
#                 username, count, price)
#             message += '\n\n'
#             message += _('❌ <b>Total canceled orders for client</b>\nCount: {}\n<b>Total cost: {}₪</b>').format(
#                 cancel_count, cancel_price)
#             text += message
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text,
#                               reply_markup=statistics_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS
#
#
# def on_statistics_menu(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     chat_id = query.message.chat_id
#     message_id = query.message.message_id
#     if data == 'statistics_back':
#         bot.edit_message_text(chat_id=chat_id,
#                               message_id=message_id,
#                               text=_('⚙️ Settings'),
#                               reply_markup=admin_keyboard(_),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_MENU
#     elif data == 'statistics_general':
#         state = enums.ADMIN_STATISTICS_GENERAL
#         shortcuts.initialize_calendar(bot, user_data, chat_id, message_id, state, _, query.id)
#         return state
#     elif data == 'statistics_couriers':
#         couriers = Courier.select(Courier.username, Courier.id).where(Courier.is_active == True).tuples()
#         msg = _('Select a courier:')
#         bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                               text=msg, reply_markup=general_select_one_keyboard(_, couriers),
#                               parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_STATISTICS_COURIERS
#     elif data == 'statistics_locations':
#         locations = Location.select().exists()
#         if not locations:
#             msg = _('You don\'t have locations')
#             query.answer(text=msg, show_alert=True)
#             return enums.ADMIN_STATISTICS
#         else:
#             locations = Location.select(Location.title, Location.id).tuples()
#             msg = _('Select location:')
#             bot.edit_message_text(chat_id=chat_id, message_id=message_id,
#                                   text=msg, reply_markup=general_select_one_keyboard(_, locations),
#                                   parse_mode=ParseMode.MARKDOWN)
#             query.answer()
#             return enums.ADMIN_STATISTICS_LOCATIONS
#     elif data == 'statistics_user':
#         msg = _('Enter username:')
#         bot.delete_message(chat_id, message_id)
#         bot.send_message(chat_id=chat_id, text=msg, reply_markup=cancel_button(_))
#         query.answer()
#         return enums.ADMIN_STATISTICS_USER


@user_passes
def on_bot_settings_menu(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if data == 'bot_settings_back':
        msg = _('⚙️ Settings')
        reply_markup = keyboards.admin_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_MENU
    elif data == 'bot_settings_couriers':
        msg = _('🛵 Couriers')
        couriers = User.select(User.username, User.id).join(UserPermission)\
            .where(UserPermission.permission == UserPermission.COURIER, User.banned == False).tuples()
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, couriers)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_COURIERS
    elif data == 'bot_settings_edit_messages':
        msg = _('⌨️ Edit bot messages')
        reply_markup = keyboards.edit_messages_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_MESSAGES
    elif data == 'bot_settings_channels':
        return states.enter_settings_channels(_, bot, chat_id, msg_id, query.id)
    elif data == 'bot_settings_order_options':
        msg = _('💳 Order options')
        reply_markup = keyboards.order_options_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDER_OPTIONS
    elif data == 'bot_settings_language':
        msg = _('🈚️ Default language:')
        reply_markup = keyboards.bot_language_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_BOT_LANGUAGE
    elif data == 'bot_settings_users':
        return states.enter_settings_users(_, bot, chat_id, msg_id, query.id)
    elif data == 'bot_settings_currency':
        currency = config.currency
        currency_name, currency_symbol = Currencies.CURRENCIES[currency]
        msg = _('Current currency: *{} {}*'.format(currency_name, currency_symbol))
        msg += '\n'
        msg += _('Select new currency:')
        reply_markup = keyboards.create_currencies_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_SET_CURRENCIES
    elif data == 'bot_settings_bitcoin_payments':
        btc_creds = BitcoinCredentials.select().first()
        wallet_id = btc_creds.wallet_id
        msg = _('💰 Bitcoin payments')
        msg += '\n'
        msg += _('Status: *{}*').format('Enabled' if btc_creds.enabled else 'Disabled')
        msg += '\n'
        msg += _('Wallet ID: *{}*').format(wallet_id if wallet_id else '')
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_creds.password else 'No')
        reply_markup = keyboards.create_btc_settings_keyboard(_, btc_creds.enabled)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BTC_PAYMENTS
    elif data == 'bot_settings_bot_status':
        msg = _('⚡️ Bot Status')
        reply_markup = keyboards.create_bot_status_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_BOT_STATUS
    elif data == 'bot_settings_reset_all_data':
        user = User.get(telegram_id=user_id)
        if user.is_admin:
            msg = _('You are about to delete your database, session and all messages in channels. Is that correct?')
            reply_markup = keyboards.create_reset_all_data_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_RESET_DATA
        else:
            query.answer('This function works only for admin')
            return enums.ADMIN_BOT_SETTINGS
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_bot_language(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('iw', 'en'):
        config.set_value('default_language', action)
        msg = _('🈚️ Default language:')
        reply_markup = keyboards.bot_language_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_BOT_LANGUAGE
    elif action == 'back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_couriers(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        msg = _('🛵 Couriers')
        couriers = User.select(User.username, User.id).join(UserPermission) \
            .where(UserPermission.permission == UserPermission.COURIER, User.banned == False).tuples()
        page = user_data['listing_page']
        page = int(page)
        user_data['listing_page'] = page
        reply_markup = keyboards.general_select_one_keyboard(_, couriers, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_COURIERS
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    elif action == 'select':
        user_data['courier_select'] = val
        return states.enter_courier_detail(_, bot, chat_id, msg_id, query.id, val)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_courier_detail(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    courier_id = user_data['courier_select']
    if action == 'change_locations':
        courier = User.get(id=courier_id)
        courier_locs = Location.select().join(CourierLocation)\
            .where(CourierLocation.user == courier)
        courier_locs = [loc.id for loc in courier_locs]
        print(courier_locs)
        all_locs = []
        for loc in Location.select():
            is_picked = True if loc.id in courier_locs else False
            all_locs.append((loc.title, loc.id, is_picked))
        user_data['courier_locations_select'] = {'page': 1, 'ids': courier_locs}
        reply_markup = keyboards.general_select_keyboard(_, all_locs)
        msg = '🎯 Change locations'
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_COURIER_LOCATIONS
    elif action == 'edit_warehouse':
        page = 1
        user_data['products_listing_page'] = page
        return states.enter_courier_warehouse_products(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'back':
        del user_data['courier_select']
        msg = _('🛵 Couriers')
        couriers = User.select(User.username, User.id).join(UserPermission) \
            .where(UserPermission.permission == UserPermission.COURIER, User.banned == False).tuples()
        page = user_data['listing_page']
        reply_markup = keyboards.general_select_one_keyboard(_, couriers, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_COURIERS


@user_passes
def on_courier_locations(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    locs_selected = user_data['courier_locations_select']['ids']
    if action in ('page', 'select'):
        if action == 'select':
            val = int(val)
            if val in locs_selected:
                locs_selected.remove(val)
            else:
                locs_selected.append(val)
            page = user_data['courier_locations_select']['page']
        else:
            page = int(val)
            user_data['courier_locations_select']['page'] = page
        all_locs = []
        for loc in Location.select():
            is_picked = True if loc.id in locs_selected else False
            all_locs.append((loc.title, loc.id, is_picked))
        msg = '🎯 Change locations'
        reply_markup = keyboards.general_select_keyboard(_, all_locs, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_COURIER_LOCATIONS
    elif action == 'done':
        courier_id = user_data['courier_select']
        courier = User.get(id=courier_id)
        for loc_id in locs_selected:
            location = Location.get(id=loc_id)
            try:
                CourierLocation.get(location=location)
            except CourierLocation.DoesNotExist:
                CourierLocation.create(user=courier, location=location)
        del user_data['courier_locations_select']
        return states.enter_courier_detail(_, bot, chat_id, msg_id, query.id, courier_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_courier_warehouse_products(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['products_listing_page'] = page
        return states.enter_courier_warehouse_products(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'select':
        product = Product.get(id=val)
        courier_id = user_data['courier_select']
        courier = User.get(id=courier_id)
        try:
            warehouse = ProductWarehouse.get(courier=courier, product=product)
        except ProductWarehouse.DoesNotExist:
            warehouse = ProductWarehouse.create(courier=courier, product=product)
        user_data['courier_warehouse_select'] = warehouse.id
        return states.enter_courier_warehouse_detail(_, bot, chat_id, warehouse, msg_id, query.id)
    elif action == 'back':
        del user_data['products_listing_page']
        courier_id = user_data['courier_select']
        return states.enter_courier_detail(_, bot, chat_id, msg_id, query.id, courier_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_courier_warehouse_detail(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'edit':
        warehouse_id = user_data['courier_warehouse_select']
        warehouse = ProductWarehouse.get(id=warehouse_id)
        msg = _('Courier credits: `{}`').format(warehouse.count)
        msg += '\n'
        msg += _('Please enter new amount')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_COURIER_WAREHOUSE_EDIT
    elif action == 'back':
        del user_data['courier_warehouse_select']
        page = user_data['products_listing_page']
        return states.enter_courier_warehouse_products(_, bot, chat_id, msg_id, query.id, page)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_courier_warehouse_edit(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    warehouse_id = user_data['courier_warehouse_select']
    warehouse = ProductWarehouse.get(id=warehouse_id)
    if query:
        if query.data == 'back':
            return states.enter_courier_warehouse_detail(_, bot, chat_id, warehouse, query.message.message_id, query.id)
        return states.enter_unknown_command(_, bot, query)
    text = update.message.text
    try:
        credits = int(text)
    except ValueError:
        msg = _('Please enter a number:')
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
        return enums.ADMIN_COURIER_WAREHOUSE_EDIT
    warehouse_id = user_data['courier_warehouse_select']
    warehouse = ProductWarehouse.get(id=warehouse_id)
    product = warehouse.product
    total_credits = product.credits + warehouse.count
    if credits > total_credits:
        msg = _('Cannot give to courier more credits than you have in warehouse: *{}*\n'
                'Please enter new number of credits:').format(total_credits)
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_COURIER_WAREHOUSE_EDIT
    admin_credits = product.credits - (credits - warehouse.count)
    product.credits = admin_credits
    warehouse.count = credits
    warehouse.save()
    product.save()
    courier_username = escape_markdown(warehouse.courier.username)
    msg = _('✅ You have given `{}` credits to courier *{}*').format(credits, courier_username)
    bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
    return states.enter_courier_warehouse_detail(_, bot, chat_id, warehouse)


@user_passes
def on_edit_messages_enter(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    if query and query.data == 'back':
        del user_data['edit_message']
        msg_id = query.message.message_id
        msg = _('⌨️ Edit bot messages')
        reply_markup = keyboards.edit_messages_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_MESSAGES
    new_message = update.message.text
    new_message = fix_markdown(new_message)
    conf_name, msg = user_data['edit_message']['name'], user_data['edit_message']['msg']
    config.set_value(conf_name, new_message)
    reply_markup = keyboards.edit_messages_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_EDIT_MESSAGES


@user_passes
def on_edit_messages(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action != 'back':
        if action == 'working_hours':
            config_msg = config.working_hours
            msg_remainder = _('Type new working hours message')
            user_data['edit_message'] = {'name': 'working_hours', 'msg': _('Working hours were changed.')}
        elif action == 'contact_info':
            config_msg = config.contact_info
            msg_remainder = _('Type new contact info')
            user_data['edit_message'] = {'name': 'contact_info', 'msg': _('Contact info were changed.')}
        elif action == 'welcome':
            config_msg = config.welcome_text
            msg_remainder = _('Type new welcome message')
            user_data['edit_message'] = {'name': 'welcome_text', 'msg': _('Welcome text was changed.')}
        elif action == 'order_details':
            config_msg = config.order_text
            msg_remainder = _('Type new order details message')
            user_data['edit_message'] = {'name': 'order_details', 'msg': _('Order details message was changed.')}
        else:
            config_msg = config.order_complete_text
            msg_remainder = _('Type new order final message')
            user_data['edit_message'] = {'name': 'order_complete_text', 'msg': _('Order final message was changed.')}
        msg = _('Raw:\n\n`{}`').format(config_msg)
        msg += '\n\n'
        msg += _('Displayed:\n\n{}').format(config_msg)
        msg += '\n\n'
        msg += msg_remainder
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_MESSAGES_ENTER
    else:
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)


@user_passes
def on_users(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('registered_users', 'pending_registrations', 'black_list'):
        user_data['listing_page'] = 1
        if action == 'registered_users':
            return states.enter_settings_registered_users(_, bot, chat_id, msg_id, query.id)
        elif action == 'pending_registrations':
            return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id)
        else:
            return states.enter_black_list(_, bot, chat_id, msg_id, query.id)
    if action == 'back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id=msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_registered_users(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_settings_registered_users(_, bot, chat_id, msg_id, query.id, page=page)
    elif action == 'select':
        user = User.get(id=val)
        username = escape_markdown(user.username)
        msg = '*{}*'.format(username)
        msg += '\n'
        msg += '*Status*: {}'.format(user.permission.get_permission_display())
        user_data['user_select'] = val
        return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_settings_users(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_registered_users_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    id_messages = user_data.get('user_id_messages')
    if id_messages:
        for msg_id in id_messages:
            bot.delete_message(chat_id, msg_id)
        del user_data['user_id_messages']
    msg_id = query.message.message_id
    action = query.data
    user_id = user_data['user_select']
    user = User.get(id=user_id)
    if action == 'show_registration':
        bot.delete_message(chat_id, msg_id)
        answers_ids = shortcuts.send_user_identification_answers(bot, chat_id, user)
        user_data['user_id_messages'] = answers_ids
        msg = '*Phone number*: {}'.format(user.phone_number)
        return states.enter_registered_users_select(_, bot, chat_id, msg, query.id)
    elif action == 'remove_registration':
        username = escape_markdown(user.username)
        msg = _('Remove registration for *{}*?').format(username)
        reply_markup = keyboards.are_you_sure_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_REGISTERED_USERS_REMOVE
    elif action == 'change_status':
        msg = _('⭐️ Change user status')
        registered_perms = (UserPermission.OWNER, UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION)
        perms = UserPermission.select().where(UserPermission.permission.not_in(registered_perms))\
            .order_by(UserPermission.permission.desc())
        perms = [(perm.get_permission_display(), perm.id) for perm in perms]
        reply_markup = keyboards.general_select_one_keyboard(_, perms, page_len=len(perms))
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REGISTERED_USERS_STATUS
    elif action == 'black_list':
        username = escape_markdown(user.username)
        msg = _('Black list user *{}*?').format(username)
        reply_markup = keyboards.are_you_sure_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_REGISTERED_USERS_BLACK_LIST
    if action == 'back':
        del user_data['user_select']
        page = user_data['listing_page']
        return states.enter_settings_registered_users(_, bot, chat_id, msg_id, query.id, page=page)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_registered_users_remove(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('yes', 'no'):
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        username = escape_markdown(user.username)
        if action == 'yes':
            shortcuts.remove_user_registration(user)
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, your registration has been removed').format(username)
            bot.send_message(user.telegram_id, msg)
            msg = _('Registration for *{}* has been removed!').format(username)
            page = user_data['listing_page']
            del user_data['user_select']
            return states.enter_settings_registered_users(_, bot, chat_id, msg_id, query.id, page=page, msg=msg)
        else:
            msg = '*{}*'.format(username)
            msg += '\n'
            msg += '*Status*: {}'.format(user.permission.get_permission_display())
            return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_registered_users_status(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('select', 'back'):
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        username = escape_markdown(user.username)
        if action == 'select':
            perm = UserPermission.get(id=val)
            user.permission = perm
            user.save()
            perm_display = perm.get_permission_display()
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, your status has been changed to: {}').format(username, perm_display)
            bot.send_message(user.telegram_id, msg)
            msg = _('User\'s *{}* status was changed to: {}').format(username, perm_display)
        else:
            msg = '*{}*'.format(username)
            msg += '\n'
            msg += '*Status*: {}'.format(user.permission.get_permission_display())
        return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_registered_users_black_list(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('yes', 'no'):
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        username = escape_markdown(user.username)
        if action == 'yes':
            user.banned = True
            user.save()
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, you have been black-listed').format(username)
            bot.send_message(user.telegram_id, msg)
            msg = _('*{}* has been added to black-list!').format(username)
            return states.enter_settings_registered_users(_, bot, chat_id, msg_id, query.id, msg=msg)
        else:
            msg = '*{}*'.format(username)
            msg += '\n'
            msg += '*Status*: {}'.format(user.permission.get_permission_display())
            return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_pending_registrations(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id, page=page)
    elif action == 'select':
        user_data['user_select'] = val
        return states.enter_pending_registrations_user(_, bot, chat_id, msg_id, query.id, user_data, val)
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_settings_users(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_pending_registrations_user(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    action = query.data
    id_messages = user_data.get('user_id_messages')
    if id_messages:
        for msg_id in id_messages:
            bot.delete_message(chat_id, msg_id)
        del user_data['user_id_messages']
    msg_id = query.message.message_id
    if action in ('approve_user', 'black_list', 'back'):
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        username = escape_markdown(user.username)
        if action == 'approve_user':
            msg = _('Select new status for user *{}*').format(username)
            registered_perms = (UserPermission.OWNER, UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION)
            perms = UserPermission.select().where(UserPermission.permission.not_in(registered_perms)) \
                .order_by(UserPermission.permission.desc())
            perms = [(perm.get_permission_display(), perm.id) for perm in perms]
            reply_markup = keyboards.general_select_one_keyboard(_, perms, page_len=len(perms))
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_PENDING_REGISTRATIONS_APPROVE
        elif action == 'black_list':
            msg = _('Black-list user *{}*?').format(username)
            reply_markup = keyboards.are_you_sure_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_PENDING_REGISTRATIONS_BLACK_LIST
        else:
            del user_data['user_select']
            page = user_data['listing_page']
            return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id, page=page)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_pending_registrations_approve(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('select', 'back'):
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        username = escape_markdown(user.username)
        if action == 'select':
            perm = UserPermission.get(id=val)
            user.permission = perm
            user.save()
            perm_display = perm.get_permission_display()
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, your registration has been approved. Your status is {}').format(username, perm_display)
            bot.send_message(user.telegram_id, msg)
            msg = _('User\'s *{}* registration approved!').format(username)
            page = user_data['listing_page']
            del user_data['user_select']
            return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id, page=page, msg=msg)
        else:
            return states.enter_pending_registrations_user(_, bot, chat_id, msg_id, query.id, user_data, user_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_pending_registrations_black_list(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('yes', 'no'):
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        if action == 'yes':
            user.banned = True
            user.save()
            username = escape_markdown(user.username)
            banned_trans = get_trans(user.telegram_id)
            msg = banned_trans('{}, you have been banned.').format(username)
            bot.send_message(user.telegram_id, msg)
            msg = _('User *{}* has been banned.').format(username)
            page = user_data['listing_page']
            del user_data['user_select']
            return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id, page=page, msg=msg)
        elif action == 'no':
            return states.enter_pending_registrations_user(_, bot, chat_id, msg_id, query.id, user_data, user_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_black_list(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_black_list(_, bot, chat_id, msg_id, query.id, page=page)
    elif action == 'select':
        user_data['user_select'] = val
        user = User.get(id=val)
        username = escape_markdown(user.username)
        msg = _('User *{}*').format(username)
        reply_markup = keyboards.banned_user_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BLACK_LIST_USER
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_settings_users(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_black_list_user(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    action = query.data
    id_messages = user_data.get('user_id_messages')
    if id_messages:
        for msg_id in id_messages:
            bot.delete_message(chat_id, msg_id)
        del user_data['user_id_messages']
    msg_id = query.message.message_id
    if action in 'show_registration':
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        bot.delete_message(chat_id, msg_id)
        answers_ids = shortcuts.send_user_identification_answers(bot, chat_id, user)
        user_data['user_id_messages'] = answers_ids
        msg = '*Phone number*: {}'.format(user.phone_number)
        reply_markup = keyboards.banned_user_keyboard(_)
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BLACK_LIST_USER
    elif action == 'black_list_remove':
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        user.banned = False
        user.save()
        username = escape_markdown(user.username)
        user_trans = get_trans(user.telegram_id)
        msg = user_trans('{}, you have been removed from black-list.').format(username)
        bot.send_message(user.telegram_id, msg)
        del user_data['user_select']
        page = user_data['listing_page']
        msg = _('*{}* has been removed from black list!').format(username)
        return states.enter_black_list(_, bot, chat_id, msg_id, query.id, page=page, msg=msg)
    elif action == 'back':
        del user_data['user_select']
        page = user_data['listing_page']
        return states.enter_black_list(_, bot, chat_id, msg_id, query.id, page=page)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_channels(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if data == 'bot_channels_back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id=msg_id)
    if data == 'bot_channels_view':
        msg = _('🔭 View channels')
        channels = Channel.select(Channel.name, Channel.id).tuples()
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, channels)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CHANNELS_VIEW
    elif data == 'bot_channels_add':
        user_data['admin_channel_edit'] = {'action': 'add'}
        msg = _('Please enter channel name')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CHANNELS_SET_NAME
    elif data == 'bot_channels_language':
        msg = _('🈚︎ Select language:')
        reply_markup = keyboards.bot_language_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CHANNELS_LANGUAGE
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_channels_view(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('page', 'select'):
        channels = Channel.select(Channel.name, Channel.id).tuples()
        if action == 'page':
            msg = _('🔭 View channels')
            page = int(val)
            user_data['listing_page'] = page
            reply_markup = keyboards.general_select_one_keyboard(_, channels, page_num=page)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_CHANNELS_VIEW
        else:
            return states.enter_channel_details(_, bot, chat_id, user_data, val, msg_id, query.id)
    del user_data['listing_page']
    if action == 'back':
        return states.enter_settings_channels(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_channel_details(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    channel_id = user_data['channel_select']
    del user_data['channel_select']
    if action == 'edit':
        msg = _('Please enter new channel name')
        user_data['admin_channel_edit'] = {'action': 'edit', 'id': channel_id}
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CHANNELS_SET_NAME
    elif action in ('remove', 'back'):
        if action == 'remove':
            channel = Channel.get(id=channel_id)
            channel_name = channel.name.replace('*', '')
            channel_name = escape_markdown(channel_name)
            ChannelPermissions.delete().where(ChannelPermissions.channel == channel).execute()
            channel.delete_instance()
            msg = _('Channel *{}* successfully deleted.').format(channel_name)
        else:
            msg = _('🔭 View channels')
        page = user_data['listing_page']
        channels = Channel.select(Channel.name, Channel.id).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, channels, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_CHANNELS_VIEW
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_channel_set_name(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    channel_data = user_data['admin_channel_edit']
    channel_action = channel_data['action']
    if query:
        if query.data == 'back':
            del user_data['admin_channel_edit']
            if channel_action == 'add':
                return states.enter_channels(_, bot, chat_id, query.message.message_id, query.id)
            else:
                channel_id = channel_data['id']
                return states.enter_channel_details(_, bot, chat_id, user_data, channel_id, query.message.message_id, query.id)
        else:
            return states.enter_unknown_command(_, bot, query)
    msg_text = update.message.text
    msg = _('Please enter channel ID')
    if channel_action == 'add':
        try:
            Channel.get(name=msg_text)
        except Channel.DoesNotExist:
            pass
        else:
             msg = _('Channel with that name already exists.')
             msg += '\n'
             msg += _('Please enter channel name')
             reply_markup = keyboards.cancel_button(_)
             bot.send_message(chat_id, msg, reply_markup=reply_markup)
             return enums.ADMIN_CHANNELS_SET_NAME
    else:
        channel = Channel.get(id=channel_data['id'])
        msg += '\n'
        msg += _('Current ID: *{}*').format(channel.channel_id)
    user_data['admin_channel_edit']['name'] = msg_text
    reply_markup = keyboards.cancel_button(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_CHANNELS_SET_ID


@user_passes
def on_channel_set_id(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    channel_data = user_data['admin_channel_edit']
    channel_action = channel_data['action']
    if query:
        if query.data == 'back':
            del user_data['admin_channel_edit']
            if channel_action == 'add':
                return states.enter_channels(_, bot, chat_id, query.message.message_id, query.id)
            else:
                channel_id = channel_data['id']
                return states.enter_channel_details(_, bot, chat_id, user_data, channel_id, query.message.message_id, query.id)
        else:
            return states.enter_unknown_command(_, bot, query)
    msg_text = update.message.text
    msg = _('Please enter channel link')
    if channel_action == 'add':
        try:
            Channel.get(channel_id=msg_text)
        except Channel.DoesNotExist:
            pass
        else:
            msg = _('Channel with that ID already exists.')
            msg += '\n'
            msg += _('Please enter channel ID')
            reply_markup = keyboards.cancel_button(_)
            bot.send_message(chat_id, msg, reply_markup=reply_markup)
            return enums.ADMIN_CHANNELS_SET_ID
    else:
        channel_id = channel_data['id']
        channel = Channel.get(id=channel_id)
        msg += '\n'
        msg += _('Current link: *{}*').format(channel.link)
    user_data['admin_channel_edit']['channel_id'] = msg_text
    reply_markup = keyboards.cancel_button(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_CHANNELS_SET_LINK


@user_passes
def on_channel_set_link(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    channel_data = user_data['admin_channel_edit']
    channel_action = channel_data['action']
    if query:
        if query.data == 'back':
            del user_data['admin_channel_edit']
            if channel_action == 'add':
                return states.enter_channels(_, bot, chat_id, query.message.message_id, query.id)
            else:
                channel_id = channel_data['id']
                return states.enter_channel_details(_, bot, chat_id, user_data, channel_id, query.message.message_id,
                                                    query.id)
        else:
            return states.enter_unknown_command(_, bot, query)
    msg_text = update.message.text
    if channel_action == 'add':
        try:
            Channel.get(link=msg_text)
        except Channel.DoesNotExist:
            pass
        else:
            msg = _('Channel with that link already exists.')
            msg += '\n'
            msg += _('Please enter channel link')
            reply_markup = keyboards.cancel_button(_)
            bot.send_message(chat_id, msg, reply_markup=reply_markup)
            return enums.ADMIN_CHANNELS_SET_LINK
        channel_perms = []
    else:
        channel_id = channel_data['id']
        channel = Channel.get(id=channel_id)
        channel_perms = ChannelPermissions.select().where(ChannelPermissions.channel == channel)
        channel_perms = [perm.permission.id for perm in channel_perms]
    msg = _('Please select permissions for channel.')
    user_data['admin_channel_edit']['link'] = msg_text
    perms = UserPermission.select()
    perms_list = []
    for perm in perms:
        is_picked = True if perm.id in channel_perms else False
        perms_list.append((perm.get_permission_display(), perm.id, is_picked))
    user_data['admin_channel_edit']['perms'] = channel_perms
    reply_markup = keyboards.general_select_keyboard(_, perms_list, page_len=len(perms_list))
    bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_CHANNELS_ADD


@user_passes
def on_channel_add(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    channel_data = user_data['admin_channel_edit']
    if action == 'select':
        channel_perms = channel_data['perms']
        val = int(val)
        if val in channel_perms:
            channel_perms.remove(val)
        else:
            channel_perms.append(val)
        perms = UserPermission.select()
        perms_list = []
        for perm in perms:
            is_picked = True if perm.id in channel_perms else False
            perms_list.append((perm.get_permission_display(), perm.id, is_picked))
        user_data['admin_channel_edit']['perms'] = channel_perms
        msg = _('Please select permissions for channel.')
        reply_markup = keyboards.general_select_keyboard(_, perms_list, page_len=len(perms_list))
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CHANNELS_ADD
    elif action == 'done':
        channel_name = channel_data['name']
        channel_tg_id = channel_data['channel_id']
        channel_link = channel_data['link']
        channel_perms = channel_data['perms']
        channel_action = channel_data['action']
        msg_name = channel_name.replace('*', '')
        msg_name = escape_markdown(msg_name)
        del user_data['admin_channel_edit']
        if channel_action == 'add':
            channel = Channel.create(name=channel_name, link=channel_link, channel_id=channel_tg_id)
            for perm_id in channel_perms:
                user_perm = UserPermission.get(id=perm_id)
                ChannelPermissions.create(channel=channel, permission=user_perm)
            msg = _('Channel *{}* successfully added.').format(msg_name)
            bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN)
            return states.enter_channels(_, bot, chat_id)
        else:
            channel_id = channel_data['id']
            channel = Channel.get(id=channel_id)
            channel.name = channel_name
            channel.link = channel_link
            channel.channel_id = channel_tg_id
            channel.save()
            ChannelPermissions.delete().where(ChannelPermissions.channel == channel).execute()
            for perm_id in channel_perms:
                user_perm = UserPermission.get(id=perm_id)
                ChannelPermissions.create(channel=channel, permission=user_perm)
            msg = _('Channel *{}* has been updated!').format(msg_name)
            bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN)
            return states.enter_channel_details(_, bot, chat_id, user_data, channel_id)


@user_passes
def on_channels_language(bot, update):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('iw', 'en'):
        config.set_value('channels_language', action)
        msg = _('🈚︎ Select language:')
        reply_markup = keyboards.bot_language_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CHANNELS_LANGUAGE
    elif action == 'back':
        return states.enter_channels(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_order_options(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if data == 'bot_order_options_back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    if data == 'bot_order_options_orders':
        msg = _('📖 Orders')
        reply_markup = keyboards.create_bot_orders_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_ORDERS
    if data == 'bot_order_options_product':
        msg = _('🏪 My Products')
        reply_markup = keyboards.create_bot_products_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_PRODUCTS
    if data == 'bot_order_options_categories':
        msg = _('🛍 Categories')
        reply_markup = keyboards.create_categories_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CATEGORIES
    elif data == 'bot_order_options_warehouse':
        products = Product.filter(is_active=True)
        products = [(product.title, product.id) for product in products]
        msg = _('Select a product to add credit')
        user_data['listing_page'] = 1
        user_data['menu'] = 'order_options'
        reply_markup = keyboards.general_select_one_keyboard(_, products)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_WAREHOUSE_PRODUCTS
    elif data == 'bot_order_options_discount':
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=_('Enter discount like:\n'
                   '50 > 500: all deals above 500$ will be -50$\n'
                   '10% > 500: all deals above 500$ will be -10%\n'
                   'Current discount: {} > {}').format(config.discount, config.discount_min),
            reply_markup=keyboards.cancel_button(_),
            parse_mode=ParseMode.MARKDOWN,
        )
        query.answer()
        return enums.ADMIN_ADD_DISCOUNT
    elif data == 'bot_order_options_delivery_fee':
        msg = _('🚕 Delivery fee')
        reply_markup = keyboards.delivery_fee_keyboard(_, config.delivery_fee_for_vip)
        bot.edit_message_text(msg, chat_id, msg, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_DELIVERY_FEE
    elif data == 'bot_order_options_price_groups':
        msg = _('💸 Product price groups')
        bot.edit_message_text(msg, chat_id, msg, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.create_product_price_groups_keyboard(_))
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUPS
    elif data == 'bot_order_options_add_locations':
        return states.enter_locations(_, bot, chat_id, msg_id, query.id)
    elif data == 'bot_order_options_identify':
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.vip_required, first_question))
        msg = _('👨 Edit identification process')
        reply_markup = keyboards.create_edit_identification_keyboard(_, questions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_orders(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    action = query.data
    if action == 'back':
        return states.enter_order_options(_, bot, chat_id, msg_id, query.id)
    if action == 'pending':
        orders = Order.select().where(Order.delivered == False)
        orders_data = [(order.id, order.date_created.strftime('%d/%m/%Y')) for order in orders]
        orders = [(_('Order №{} {}').format(order_id, order_date), order_id) for order_id, order_date in orders_data]
        user_data['admin_pending_orders'] = orders
        keyboard = keyboards.general_select_one_keyboard(_, orders)
        msg = _('Please select an order\nBot will send it to service channel')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_ORDERS_PENDING_SELECT
    elif action == 'finished':
        state = enums.ADMIN_ORDERS_FINISHED_DATE
        shortcuts.initialize_calendar(bot, user_data, chat_id, msg_id, state, _, query.id)
        return state
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_orders_pending_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    action, val = query.data.split('|')
    if action == 'back':
        bot.edit_message_text(_('📖 Orders'), chat_id, message_id, reply_markup=keyboards.create_bot_orders_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS
    if action == 'page':
        orders = user_data['admin_pending_orders']
        keyboard = keyboards.general_select_one_keyboard(_, orders, int(val))
        msg = _('Please select an order\nBot will send it to service channel')
        bot.edit_message_text(msg, chat_id, message_id,
                              reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS_PENDING_SELECT
    elif action == 'select':
        service_trans = get_channel_trans()
        order = Order.get(id=val)
        user_name = escape_markdown(order.user.username)
        if order.location:
            location = escape_markdown(order.location.title)
        else:
            location = '-'
        msg = service_trans('Order №{}, Location {}\nUser @{}').format(val, location, user_name)
        shortcuts.bot_send_order_msg(bot, config.service_channel, msg, service_trans, val)
        msg = _('💳 Order options')
        bot.edit_message_text(msg, chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.order_options_keyboard(_))
        query.answer(text=_('Order has been sent to service channel'), show_alert=True)
    return enums.ADMIN_ORDER_OPTIONS


@user_passes
def on_admin_orders_finished_date(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    if action == 'ignore':
        return enums.ADMIN_ORDERS_FINISHED_DATE
    elif action == 'back':
        bot.edit_message_text(_('📖 Orders'), chat_id, message_id,
                              reply_markup=keyboards.create_bot_orders_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS
    elif action in ('day', 'month', 'year'):
        year, month = user_data['calendar_date']
        queries = shortcuts.get_order_subquery(action, val, month, year)
        orders = Order.select().where(*queries)
        orders = orders.select().where((Order.delivered == True), (Order.canceled == False))
        orders_data = [(order.id, order.user.username, order.date_created.strftime('%d/%m/%Y')) for order in orders]
        orders = [(_('Order №{} @{} {}').format(order_id, user_name, order_date), order_id) for order_id, user_name, order_date in orders_data]
        user_data['admin_finished_orders'] = orders
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=_('Select order'),
                              reply_markup=keyboards.general_select_one_keyboard(_, orders),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS_FINISHED_SELECT


# def on_admin_orders_finished_select(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, val = query.data.split('|')
#     chat_id = query.message.chat_id
#     message_id = query.message.message_id
#     if action == 'back':
#         state = enums.ADMIN_ORDERS_FINISHED_DATE
#         shortcuts.initialize_calendar(bot, user_data, chat_id, message_id, state, _, query.id)
#         return state
#     orders = user_data['admin_finished_orders']
#     if action == 'page':
#         page_num = int(val)
#         keyboard = keyboards.general_select_one_keyboard(_, orders, page_num)
#         msg = _('Select order')
#     elif action == 'select':
#         order = Order.get(id=val)
#         msg = OrderPhotos.get(order=order).order_text
#         courier_username = escape_markdown(order.courier.username)
#         courier_delivered = _('Courier: {}').format(courier_username)
#         msg += '\n\n' + courier_delivered
#         keyboard = keyboards.general_select_one_keyboard(_, orders)
#     bot.edit_message_text(msg, chat_id, message_id,
#                           reply_markup=keyboard)
#     query.answer()
#     return enums.ADMIN_ORDERS_FINISHED_SELECT


def on_delivery_fee(bot, update):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'add':
        return states.enter_delivery_fee_add(_, bot, chat_id, msg_id, query.id)
    elif action == 'back':
        return states.enter_order_options(_, bot, chat_id, msg_id, query.id)
    elif action == 'vip':
        conf_value = not config.delivery_fee_for_vip
        config.set_value('delivery_fee_for_vip', conf_value)
        return states.enter_delivery_fee(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


def on_delivery_fee_add(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'all':
        user_data['delivery_fee_location'] = 'all'
        return states.enter_delivery_fee_enter(_, bot, chat_id, msg_id, query.id)
    elif action == 'select':
        page = 1
        user_data['listing_page'] = page
        return states.enter_delivery_fee_location(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'back':
        return states.enter_delivery_fee(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


def on_add_delivery_for_location(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'back':
        del user_data['listing_page']
        return states.enter_delivery_fee_add(_, bot, chat_id, msg_id, query.id)
    elif action == 'select':
        user_data['delivery_fee_location'] = val
        return states.enter_delivery_fee_enter(_, bot, chat_id, msg_id, query.id)
    elif action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_delivery_fee_location(_, bot, chat_id, page, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


def on_delivery_fee_enter(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    for_location = user_data['delivery_fee_location']
    if query:
        if query.data == 'back':
            if for_location == 'all':
                return states.enter_delivery_fee_add(_, bot, chat_id, query.message.message_id, query.id)
            else:
                page = user_data['listing_page']
                return states.enter_delivery_fee_location(_, bot, chat_id, page, query.message.message_id, query.id)
        return states.enter_unknown_command(_, bot, query)
    delivery_text = update.message.text
    delivery_data = delivery_text.split('>')
    delivery_fee = delivery_data[0].strip()
    try:
        delivery_fee = int(delivery_fee)
    except ValueError:
        msg = _('Incorrect format')
        bot.send_message(msg, chat_id)
        return states.enter_delivery_fee_enter(_, bot, chat_id)
    try:
        delivery_min = delivery_data[1]
    except IndexError:
        delivery_min = 0
    else:
        delivery_min = int(delivery_min.strip())
    msg = _('Delivery fee was changed:')
    msg += '\n'
    msg += _('Delivery fee: {}').format(delivery_fee)
    msg += '\n'
    msg += _('Delivery treshold: {}').format(delivery_min)
    if for_location == 'all':
        config.set_value('delivery_fee', delivery_fee)
        config.set_value('delivery_min', delivery_min)
        for loc in Location.select():
            loc.delivery_fee = delivery_fee
            loc.delivery_min = delivery_min
            loc.save()
        bot.send_message(chat_id, msg)
        return states.enter_delivery_fee_add(_, bot, chat_id)
    else:
        loc = Location.get(id=for_location)
        loc.delivery_fee = delivery_fee
        loc.delivery_min = delivery_min
        loc.save()
        bot.send_message(chat_id, msg)
        page = user_data['listing_page']
        return states.enter_delivery_fee_location(_, bot, chat_id, page=page)


def on_admin_categories(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    action = query.data
    if action == 'add':
        msg = _('Please enter the name of category')
        bot.edit_message_text(msg, chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.ADMIN_CATEGORY_ADD
    elif action == 'back':
        bot.edit_message_text(_('💳 Order options'), chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.order_options_keyboard(_))
        query.answer()
        return enums.ADMIN_ORDER_OPTIONS
    categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
    keyboard = keyboards.general_select_one_keyboard(_, categories)
    msg = _('Please select a category:')
    bot.edit_message_text(msg, chat_id, message_id,
                          parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    query.answer()
    if action == 'products':
        return enums.ADMIN_CATEGORY_PRODUCTS_SELECT
    elif action == 'remove':
        return enums.ADMIN_CATEGORY_REMOVE_SELECT


def on_admin_category_add(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    if update.callback_query and update.callback_query.data == 'back':
        upd_msg = update.callback_query.message
        bot.edit_message_text(_('🛍 Categories'), upd_msg.chat_id, upd_msg.message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.create_categories_keyboard(_))
        query.answer()
        return enums.ADMIN_CATEGORIES
    answer = update.message.text
    try:
        cat = ProductCategory.get(title=answer)
        cat_title = escape_markdown(cat.title)
        msg = _('Category with name `{}` exists already').format(cat_title)
    except ProductCategory.DoesNotExist:
        categories = ProductCategory.select().exists()
        if not categories:
            def_cat = ProductCategory.create(title=_('Default'))
            for product in Product.filter(is_active=True):
                product.category = def_cat
                product.save()
        cat = ProductCategory.create(title=answer)
        cat_title = escape_markdown(cat.title)
        msg = _('Category `{}` has been created').format(cat_title)
    bot.send_message(update.message.chat_id, msg, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboards.create_categories_keyboard(_))
    return enums.ADMIN_CATEGORIES


def on_admin_category_products_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, categories, int(val))
        bot.edit_message_text(_('Please select a category'), chat_id, message_id,
                              reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_CATEGORY_PRODUCTS_SELECT
    elif action == 'back':
        bot.edit_message_text(_('🛍 Categories'), chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.create_categories_keyboard(_))
        query.answer()
        return enums.ADMIN_CATEGORIES
    elif action == 'select':
        user_data['category_products_add'] = {'category_id': val, 'page': 1, 'products_ids': []}
        products = []
        for product in Product.filter(is_active=True):
            category = product.category
            if category:
                product_title = '{} ({})'.format(product.title, category.title)
            else:
                product_title = product.title
            products.append((product_title, product.id, False))
        msg = _('Please select products to add')
        bot.edit_message_text(msg, chat_id, message_id, reply_markup=keyboards.general_select_keyboard(_, products),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_CATEGORY_PRODUCTS_ADD


def on_admin_category_remove(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, categories, int(val))
        bot.edit_message_text(_('Please select a category'), chat_id, message_id,
                              reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_CATEGORY_REMOVE_SELECT
    if action == 'back':
        bot.edit_message_text(_('🛍 Categories'), chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.create_categories_keyboard(_))
    elif action == 'select':
        cat_len = ProductCategory.select().count()
        cat = ProductCategory.get(id=val)
        if cat.title == 'Default' and cat_len > 1:
            msg = _('Cannot delete default category')
        else:
            default = ProductCategory.get(title=cat.title)
            if cat_len == 2:
                default.delete_instance()
            else:
                for product in cat.products:
                    product.category = default
                    product.save()
            cat.delete_instance()
            cat_title = escape_markdown(cat.title)
            msg = _('Category `{}` has been deleted').format(cat_title)
        bot.edit_message_text(msg, chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.create_categories_keyboard(_))
    query.answer()
    return enums.ADMIN_CATEGORIES


def on_admin_category_products_add(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    action, val = query.data.split('|')
    selected_ids = user_data['category_products_add']['products_ids']
    if action == 'done':
        cat_id = user_data['category_products_add']['category_id']
        cat = ProductCategory.get(id=cat_id)
        if selected_ids:
            products = Product.filter(Product.id << selected_ids)
            for product in products:
                product.category = cat
                product.save()
        cat_title = escape_markdown(cat.title)
        msg = _('Category `{}" was updated').format(cat_title)
        del user_data['category_products_add']
        bot.edit_message_text(msg, chat_id, message_id,
                              reply_markup=keyboards.create_categories_keyboard(_))
        query.answer()
        return enums.ADMIN_CATEGORIES
    products = []
    current_page = user_data['category_products_add']['page']
    if action == 'page':
        current_page = int(val)
        user_data['category_products_add']['page'] = current_page
    elif action == 'select':
        if val in selected_ids:
            selected_ids.remove(val)
        else:
            selected_ids.append(val)
    for product in Product.filter(is_active=True):
        if str(product.id) in selected_ids:
            selected = True
        else:
            selected = False
        category = product.category
        if category:
            product_title = '{} ({})'.format(product.title, category.title)
        else:
            product_title = product.title
        products.append((product_title, product.id, selected))
    products_keyboard = keyboards.general_select_keyboard(_, products, current_page)
    msg = _('Please select products to add')
    bot.edit_message_text(msg, chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                          reply_markup=products_keyboard)
    query.answer()
    return enums.ADMIN_CATEGORY_PRODUCTS_ADD


@user_passes
def on_warehouse_products(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_warehouse_products(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_order_options(_, bot, chat_id, msg_id, query.id)
    elif action == 'select':
        user_data['product_warehouse'] = {'product_id': val}
        product = Product.get(id=val)
        return states.enter_warehouse(_, bot, chat_id, product, msg_id, query.id)


@user_passes
def on_warehouse(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'warehouse_back':
        del user_data['product_warehouse']
        page = user_data['listing_page']
        return states.enter_warehouse_products(_, bot, chat_id, msg_id, query.id, page)
    elif action in ('warehouse_credits', 'warehouse_status'):
        product_id = user_data['product_warehouse']['product_id']
        product = Product.get(id=product_id)
        if action == 'warehouse_status':
            product.warehouse_active = not product.warehouse_active
            product.save()
            return states.enter_warehouse(_, bot, chat_id, product, msg_id, query.id)
        else:
            msg = _('Credits: `{}`').format(product.credits)
            msg += '\n'
            msg += _('Please enter new number of credits:')
            reply_markup = keyboards.cancel_button(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_WAREHOUSE_PRODUCT_EDIT
    elif action == 'warehouse_courier':
        page = 1
        user_data['couriers_listing_page'] = page
        return states.enter_warehouse_couriers(_, bot, chat_id, msg_id, query.id, page)


@user_passes
def on_warehouse_couriers(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['couriers_listing_page'] = page
        return states.enter_warehouse_couriers(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'back':
        del user_data['couriers_listing_page']
        product_id = user_data['product_warehouse']['product_id']
        product = Product.get(id=product_id)
        return states.enter_warehouse(_, bot, chat_id, product, msg_id, query.id)
    elif action == 'select':
        product_id = user_data['product_warehouse']['product_id']
        product = Product.get(id=int(product_id))
        courier = User.get(id=val)
        try:
            warehouse = ProductWarehouse.get(courier=courier, product=product)
        except ProductWarehouse.DoesNotExist:
            warehouse = ProductWarehouse(courier=courier, product=product)
            warehouse.save()
        user_data['product_warehouse']['courier_warehouse_id'] = warehouse.id
        return states.enter_warehouse_courier_detail(_, bot, chat_id, warehouse, msg_id, query.id)


@user_passes
def on_warehouse_product_credits(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    product_id = user_data['product_warehouse']['product_id']
    product = Product.get(id=product_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    if query:
        if query.data == 'back':
            return states.enter_warehouse(_, bot, chat_id, product, query.message.message_id, query.id)
        else:
            return states.enter_unknown_command(_, bot, query)
    text = update.message.text
    try:
        credits = int(text)
    except ValueError:
        msg = _('Please enter a number:')
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
        return enums.ADMIN_WAREHOUSE_PRODUCT_EDIT
    credits = abs(credits)
    if credits > 2**63-1:
        msg = _('Entered amount is too big.\n'
                'Please enter new number of credits:')
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
        return enums.ADMIN_WAREHOUSE_PRODUCT_EDIT
    product.credits = credits
    product.save()
    msg = _('✅ Product\'s credits were changed to `{}`.').format(credits)
    bot.send_message(chat_id, msg)
    return states.enter_warehouse(_, bot, chat_id, product)


@user_passes
def on_warehouse_courier_detail(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'edit':
        warehouse_id = user_data['product_warehouse']['courier_warehouse_id']
        warehouse = ProductWarehouse.get(id=warehouse_id)
        msg = _('Courier credits: `{}`').format(warehouse.count)
        msg += '\n'
        msg += _('Please enter new credits number.')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_WAREHOUSE_COURIER_EDIT
    elif action == 'back':
        page = user_data['couriers_listing_page']
        return states.enter_warehouse_couriers(_, bot, chat_id, msg_id, query.id, page)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_warehouse_courier_edit(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id

    if query:
        if query.data == 'back':
            warehouse_id = user_data['product_warehouse']['courier_warehouse_id']
            warehouse = ProductWarehouse.get(id=warehouse_id)
            return states.enter_warehouse_courier_detail(_, bot, chat_id, warehouse, query.message.message_id, query.id)
    text = update.message.text
    try:
        credits = int(text)
    except ValueError:
        msg = _('Please enter a number:')
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
        return enums.ADMIN_WAREHOUSE_COURIER_EDIT
    product_id = user_data['product_warehouse']['product_id']
    product = Product.get(id=product_id)
    warehouse_id = user_data['product_warehouse']['courier_warehouse_id']
    warehouse = ProductWarehouse.get(id=warehouse_id)
    total_credits = product.credits + warehouse.count
    if credits > total_credits:
        msg = _('Cannot give to courier more credits than you have in warehouse: `{}`\n'
                'Please enter new number of credits:').format(total_credits)
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_WAREHOUSE_COURIER_EDIT
    admin_credits = product.credits - (credits - warehouse.count)
    product.credits = admin_credits
    warehouse.count = credits
    warehouse.save()
    product.save()
    courier_username = escape_markdown(warehouse.courier.username)
    msg = _('✅ You have given *{}* credits to courier *{}*').format(credits, courier_username)
    bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
    return states.enter_warehouse_courier_detail(_, bot, chat_id, warehouse)


def on_products(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    if data == 'bot_products_back':
        bot.edit_message_text(chat_id=chat_id,
                              message_id=message_id,
                              text=_('💳 Order options'),
                              reply_markup=keyboards.order_options_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDER_OPTIONS
    elif data == 'bot_products_view':
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        if not products:
            query.answer(_('You don\'t have products'))
            return enums.ADMIN_PRODUCTS
        msg = _('Select a product to view')
        bot.edit_message_text(msg, chat_id, message_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.general_select_one_keyboard(_, products))
        query.answer()
        return enums.ADMIN_PRODUCTS_SHOW
    elif data == 'bot_products_add':
        bot.edit_message_text(chat_id=chat_id,
                              message_id=message_id,
                              text=_('➕ Add product'),
                              reply_markup=keyboards.create_bot_product_add_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_ADD
    elif data == 'bot_products_edit':
        products = Product.select(Product.title, Product.id).where(Product.is_active==True).tuples()
        products_keyboard = keyboards.general_select_one_keyboard(_, products)
        msg = _('Select a product to edit')
        bot.edit_message_text(msg, chat_id, message_id, parse_mode=ParseMode.MARKDOWN, reply_markup=products_keyboard)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_SELECT
    elif data == 'bot_products_remove':
        products = Product.filter(is_active=True)
        if not products:
            msg = _('No products to delete')
            query.answer(text=msg)
            return enums.ADMIN_PRODUCTS
        user_data['products_remove'] = {'ids': [], 'page': 1}
        products = [(product.title, product.id, False) for product in products]
        products_keyboard = keyboards.general_select_keyboard(_, products)
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text=_('Select a product which you want to remove'),
                              reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_DELETE_PRODUCT


def on_show_product(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, param = query.data.split('|')
    if action == 'back':
        msg = _('🏪 My Products')
        bot.edit_message_text(msg, chat_id, msg_id,
                              reply_markup=keyboards.create_bot_products_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCTS
    products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
    if action == 'page':
        current_page = int(param)
        msg = _('Select a product to view')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.general_select_one_keyboard(_, products, current_page))
        query.answer()
    elif action == 'select':
        product = Product.get(id=param)
        bot.delete_message(chat_id, msg_id)
        if product.group_price:
            product_prices = product.group_price.product_counts
        else:
            product_prices = product.product_counts
        product_prices = ((obj.count, obj.price) for obj in product_prices)
        shortcuts.send_product_media(bot, product, chat_id)
        msg = messages.create_admin_product_description(_, product.title, product_prices)
        bot.send_message(chat_id, msg)
        msg = _('Select a product to view')
        bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN,
                         reply_markup=keyboards.general_select_one_keyboard(_, products))
        query.answer()
    return enums.ADMIN_PRODUCTS_SHOW


def on_product_edit_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, param = query.data.split('|')
    if action == 'back':
        msg = _('🏪 My Products')
        bot.edit_message_text(msg, chat_id, msg_id,
                              reply_markup=keyboards.create_bot_products_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCTS
    if action == 'page':
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        msg = _('Select a product to edit')
        current_page = int(param)
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.general_select_one_keyboard(_, products, current_page))
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_SELECT
    elif action == 'select':
        product = Product.get(id=param)
        user_data['admin_product_edit_id'] = product.id
        product_title = escape_markdown(product.title)
        msg = _('Edit product {}').format(product_title)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT


def on_product_edit(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'back':
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        msg = _('Select a product to edit')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.general_select_one_keyboard(_, products))
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_SELECT
    product_id = user_data['admin_product_edit_id']
    product = Product.get(id=product_id)
    if action == 'title':
        product_title = escape_markdown(product.title)
        msg = _('Current title: {}\n\nEnter new title for product').format(product_title)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_TITLE
    elif action == 'price':
        prices_str = shortcuts.get_product_prices_str(_, product)
        keyboard = keyboards.create_product_price_type_keyboard(_)
        bot.edit_message_text(prices_str, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_PRICES
    elif action == 'media':
        bot.delete_message(chat_id, msg_id)
        shortcuts.send_product_media(bot, product, chat_id)
        msg = _('Upload new photos for product')
        bot.send_message(chat_id, msg, reply_markup=keyboards.create_product_edit_media_keyboard(_), parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT_MEDIA


def on_product_edit_title(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    product_id = user_data['admin_product_edit_id']
    product = Product.get(id=product_id)
    if update.callback_query and update.callback_query.data == 'back':
        upd_msg = update.callback_query.message
        product_title = escape_markdown(product.title)
        msg = _('Edit product {}').format(product_title)
        bot.edit_message_text(msg, upd_msg.chat_id, upd_msg.message_id, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        update.callback_query.answer()
    else:
        upd_msg = update.message
        product.title = upd_msg.text
        product.save()
        msg = _('Product\'s title has been updated')
        bot.send_message(upd_msg.chat_id, msg, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_PRODUCT_EDIT


def on_product_edit_price_type(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if query.data == 'text':
        product_id = user_data['admin_product_edit_id']
        product = Product.get(id=product_id)
        prices_str = shortcuts.get_product_prices_str(_, product)
        bot.edit_message_text(prices_str, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN)
        msg = _('Enter new product prices\none per line in the format\n*COUNT PRICE*, e.g. *1 10*')
        bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT_PRICES_TEXT
    elif query.data == 'select':
        msg = _('Select product price group to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, groups)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_PRICES_GROUP
    else:
        product_id = user_data['admin_product_edit_id']
        product = Product.get(id=product_id)
        product_title = escape_markdown(product.title)
        msg = _('Edit product {}').format(product_title)
        keyboard = keyboards.create_bot_product_edit_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT


def on_product_edit_prices_group(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'page':
        msg = _('Select product price group to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, groups, int(val))
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_PRICES_GROUP
    elif action == 'select':
        product_id = user_data['admin_product_edit_id']
        product = Product.get(id=product_id)
        price_group = GroupProductCount.get(id=val)
        product.group_price = price_group
        product.save()
        product_counts = product.product_counts
        if product_counts:
            for p_count in product_counts:
                p_count.delete_instance()
        msg = _('Product\'s price group was updated!')
        keyboard = keyboards.create_bot_product_edit_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT
    else:
        product_id = user_data['admin_product_edit_id']
        product = Product.get(id=product_id)
        prices_str = shortcuts.get_product_prices_str(_, product)
        keyboard = keyboards.create_product_price_type_keyboard(_)
        bot.edit_message_text(prices_str, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_PRICES


def on_product_edit_prices_text(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    product_id = user_data['admin_product_edit_id']
    product = Product.get(id=product_id)
    if update.callback_query and update.callback_query.data == 'back':
        upd_msg = update.callback_query.message
        product_title = escape_markdown(product.title)
        msg = _('Edit product {}').format(product_title)
        bot.edit_message_text(msg, upd_msg.chat_id, upd_msg.message_id,
                              reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
    else:
        upd_msg = update.message
        prices_list = []
        try:
            for line in upd_msg.text.split('\n'):
                count_str, price_str = line.split()
                count = int(count_str)
                price = float(price_str)
                prices_list.append((count, price))
        except ValueError:
            msg = _('Could not read prices, please try again')
        else:
            product.group_price = None
            product.save()
            for product_count in product.product_counts:
                product_count.delete_instance()
            for count, price in prices_list:
                ProductCount.create(product=product, count=count, price=price)
            msg = _('Product\'s prices have been updated')
        bot.send_message(upd_msg.chat_id, msg, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_PRODUCT_EDIT


def on_product_edit_media(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    upd_msg = update.message
    msg_text = upd_msg.text
    chat_id = update.message.chat_id
    product_id = user_data['admin_product_edit_id']
    product = Product.get(id=product_id)
    product_title = escape_markdown(product.title)
    if msg_text == _('Save Changes'):
        try:
            files = user_data['admin_product_edit_files']
        except KeyError:
            msg = _('Send photos/videos for new product')
            bot.send_message(chat_id, msg)
            return enums.ADMIN_PRODUCT_EDIT_MEDIA
        for media in product.product_media:
            media.delete_instance()
        for file_id, file_type in files:
            ProductMedia.create(product=product, file_id=file_id, file_type=file_type)
        del user_data['admin_product_edit_files']
        msg = _('Product\'s media has been updated\n✅')
        bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
        msg = _('Edit product {}').format(product_title)
        bot.send_message(upd_msg.chat_id, msg, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT
    elif msg_text == _('❌ Cancel'):
        bot.send_message(chat_id, _('Cancelled'), reply_markup=ReplyKeyboardRemove())
        msg = _('Edit product {}').format(product_title)
        bot.send_message(upd_msg.chat_id, msg, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT
    attr_list = ['photo', 'video']
    for file_type in attr_list:
        file = getattr(upd_msg, file_type)
        if file:
            break
    if type(file) == list:
        file = file[-1]
    if not user_data.get('admin_product_edit_files'):
        user_data['admin_product_edit_files'] = [(file.file_id, file_type)]
    else:
        user_data['admin_product_edit_files'].append((file.file_id, file_type))
    return enums.ADMIN_PRODUCT_EDIT_MEDIA


def on_delete_product(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, param = data.split('|')
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    selected_ids = user_data['products_remove']['ids']
    if action == 'done':
        if selected_ids:
            products = Product.filter(Product.id << selected_ids)
            for product in products:
                product.is_active = False
                product.save()
            msg = _('Products have been removed')
            query.answer(text=msg)
        del user_data['products_remove']
        bot.edit_message_text(chat_id=chat_id,
                              message_id=message_id,
                              text=_('🏪 My Products'),
                              reply_markup=keyboards.create_bot_products_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCTS
    products = []
    current_page = user_data['products_remove']['page']
    if action == 'page':
        current_page = int(param)
        user_data['products_remove']['page'] = current_page
    elif action == 'select':
        if param in selected_ids:
            selected_ids.remove(param)
        else:
            selected_ids.append(param)
    for product in Product.filter(is_active=True):
        if str(product.id) in selected_ids:
            selected = True
        else:
            selected = False
        products.append((product.title, product.id, selected))
    products_keyboard = keyboards.general_select_keyboard(_, products, current_page)
    bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                          text=_('Select a product which you want to remove'),
                          reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
    query.answer()
    return enums.ADMIN_DELETE_PRODUCT


def on_product_add(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    if data == 'bot_product_back':
        bot.edit_message_text(chat_id=query.message.chat_id,
                              message_id=query.message.message_id,
                              text=_('🏪 My Products'),
                              reply_markup=keyboards.create_bot_products_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCTS
    elif data == 'bot_product_new':
        bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=_('Enter new product title'),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboards.cancel_button(_),
            )
        query.answer()
        return enums.ADMIN_PRODUCT_TITLE
    elif data == 'bot_product_last':
        inactive_products = Product.filter(is_active=False)
        if not inactive_products:
            msg = _('You don\'t have last products')
            query.answer(text=msg)
            return enums.ADMIN_PRODUCT_ADD
        inactive_products = [(product.title, product.id, False) for product in inactive_products]
        user_data['last_products_add'] = {'ids': [], 'page': 1}
        products_keyboard = keyboards.general_select_keyboard(_, inactive_products)
        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text=_('Select a product which you want to activate again'),
                              reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_LAST_ADD


def on_product_last_select(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, param = data.split('|')
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    selected_ids = user_data['last_products_add']['ids']
    if action == 'done':
        if selected_ids:
            products = Product.filter(Product.id << selected_ids)
            for product in products:
                product.is_active = True
                product.save()
            msg = _('Products have been added')
            query.answer(text=msg)
        del user_data['last_products_add']
        bot.edit_message_text(_('➕ Add product'), chat_id, message_id,
                              reply_markup=keyboards.create_bot_product_add_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_ADD
    inactive_products = []
    current_page = user_data['last_products_add']['page']
    if action == 'page':
        current_page = int(param)
        user_data['last_products_add']['page'] = current_page
    elif action == 'select':
        if param in selected_ids:
            selected_ids.remove(param)
        else:
            selected_ids.append(param)
    for product in Product.filter(is_active=False):
        if str(product.id) in selected_ids:
            selected = True
        else:
            selected = False
        inactive_products.append((product.title, product.id, selected))
    products_keyboard = keyboards.general_select_keyboard(_, inactive_products, current_page)
    bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                          text=_('Select a product which you want to activate again'),
                          reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
    query.answer()
    return enums.ADMIN_PRODUCT_LAST_ADD


def on_product_title(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    if update.callback_query and update.callback_query.data == 'back':
        query = update.callback_query
        bot.edit_message_text(chat_id=query.message.chat_id,
                              message_id=query.message.message_id,
                              text=_('➕ Add product'),
                              reply_markup=keyboards.create_bot_product_add_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_ADD
    title = update.message.text
    # initialize new product data
    user_data['add_product'] = {}
    user_data['add_product']['title'] = title
    msg = _('Add product prices:')
    keyboard = keyboards.create_product_price_type_keyboard(_)
    bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_ADD_PRODUCT_PRICES


def on_add_product_prices(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'text':
        msg = _('Enter new product prices\none per line in the format\n*COUNT PRICE*, e.g. *1 10*')
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICES_TEXT
    elif action == 'select':
        msg = _('Select product price group to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, groups)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICES_GROUP
    else:
        msg = _('➕ Add product')
        keyboard = keyboards.create_bot_product_add_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_ADD


def on_product_price_group(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'page':
        msg = _('Select product price group to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, groups, int(val))
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICES_GROUP
    elif action == 'select':
        user_data['add_product']['prices'] = {'group_id': val}
        msg = _('Send photos/videos for new product')
        keyboard = keyboards.create_product_media_keyboard(_)
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_MEDIA
    else:
        msg = _('Add product prices:')
        keyboard = keyboards.create_product_price_type_keyboard(_)
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ADD_PRODUCT_PRICES


def on_product_price_text(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    if update.callback_query and update.callback_query.data == 'back':
        query = update.callback_query
        msg = _('Add product prices:')
        keyboard = keyboards.create_product_price_type_keyboard(_)
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ADD_PRODUCT_PRICES
    # check that prices are valid
    prices = update.message.text
    prices_list = []
    for line in prices.split('\n'):
        try:
            count_str, price_str = line.split()
            count = int(count_str)
            price = float(price_str)
            prices_list.append((count, price))
        except ValueError:
            update.message.reply_text(
                text=_('Could not read prices, please try again'))
            return enums.ADMIN_PRODUCT_PRICES_TEXT

    user_data['add_product']['prices'] = {'list': prices_list}
    msg = _('Send photos/videos for new product')
    keyboard = keyboards.create_product_media_keyboard(_)
    bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_PRODUCT_MEDIA


def on_product_media(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    upd_msg = update.message
    msg_text = upd_msg.text
    chat_id = update.message.chat_id
    if msg_text == _('Create Product'):
        title = user_data['add_product']['title']
        try:
            files = user_data['add_product']['files']
        except KeyError:
            msg = _('Send photos/videos for new product')
            bot.send_message(chat_id, msg)
            return enums.ADMIN_PRODUCT_MEDIA
        try:
            def_cat = ProductCategory.get(title=_('Default'))
        except ProductCategory.DoesNotExist:
            product = Product.create(title=title)
        else:
            product = Product.create(title=title, category=def_cat)
        prices = user_data['add_product']['prices']
        prices_group = prices.get('group_id')
        if prices_group is None:
            prices = prices['list']
            for count, price in prices:
                ProductCount.create(product=product, price=price, count=count)
        else:
            prices_group = GroupProductCount.get(id=prices_group)
            product.group_price = prices_group
            product.save()
        for file_id, file_type in files:
            ProductMedia.create(product=product, file_id=file_id, file_type=file_type)
        couriers = User.select().join(UserPermission).where(UserPermission.permission == UserPermission.COURIER)
        for courier in couriers:
            ProductWarehouse.create(product=product, courier=courier)
        # clear new product data
        del user_data['add_product']
        msg = _('New Product Created\n✅')
        bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
        bot.send_message(chat_id=chat_id,
                         text=_('🏪 My Products'),
                         reply_markup=keyboards.create_bot_products_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCTS
    elif msg_text == _('❌ Cancel'):
        del user_data['add_product']
        bot.send_message(chat_id, _('Cancelled'), reply_markup=ReplyKeyboardRemove())
        bot.send_message(chat_id=chat_id,
                         text=_('🏪 My Products'),
                         reply_markup=keyboards.create_bot_products_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCTS
    attr_list = ['photo', 'video']
    for file_type in attr_list:
        file = getattr(upd_msg, file_type)
        if file:
            break
    if type(file) == list:
        file = file[-1]
    if not user_data['add_product'].get('files'):
        user_data['add_product']['files'] = [(file.file_id, file_type)]
    else:
        user_data['add_product']['files'].append((file.file_id, file_type))
    return enums.ADMIN_PRODUCT_MEDIA


@user_passes
def on_locations(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'bot_locations_back':
        return states.enter_order_options(_, bot, chat_id, msg_id, query.id)
    elif action == 'bot_locations_view':
        page = 1
        user_data['listing_page'] = page
        return states.enter_locations_view(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'bot_locations_add':
        msg = _('Enter location title')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOCATION_ADD
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_locations_view(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_locations_view(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_locations(_, bot, chat_id, msg_id, query.id)
    elif action == 'select':
        user_data['location_select'] = val
        location = Location.get(id=val)
        msg_title = escape_markdown(location.title)
        msg = _('Location: `{}`').format(msg_title)
        msg += '\n'
        # currency here
        msg += _('Delivery fee: `{}`').format(location.delivery_fee)
        msg += '\n'
        msg += _('Delivery threshold: `{}`').format(location.delivery_min)
        reply_markup = keyboards.location_detail_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_LOCATION_DETAIL
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_location_detail(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('remove', 'back'):
        if action == 'remove':
            loc_id = user_data['location_select']
            location = Location.get(id=loc_id)
            msg_name = escape_markdown(location.title)
            location.delete_instance()
            msg = _('Location `{}` has been removed!').format(msg_name)
        else:
            msg = None
        del user_data['location_select']
        page = user_data['listing_page']
        return states.enter_locations_view(_, bot, chat_id, msg_id, query.id, page, msg)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_location_add(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query:
        if query.data == 'back':
            return states.enter_locations(_, bot, chat_id, query.message.message_id, query.id)
        return states.enter_unknown_command(_, bot, query)
    location_name = update.message.text
    msg_name = escape_markdown(location_name)
    try:
        Location.get(title=location_name)
    except Location.DoesNotExist:
        Location.create(title=location_name)
        msg = _('Location `{}` has been created!').format(msg_name)
        bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        return states.enter_locations(_, bot, chat_id)
    else:
        location_name = escape_markdown(msg_name)
        msg = _('Location `{}` already exists.').format(location_name)
        reply_markup = keyboards.cancel_button(_)
        bot.send_message(msg, chat_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_LOCATION_ADD


# additional cancel handler for admin commands
def on_cancel(update):
    update.message.reply_text(
        text='Admin command cancelled.',
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN,
    )
    return enums.BOT_INIT


def on_admin_fallback(bot, update):
    update.message.reply_text(
        text='Unknown input, type /cancel to exit admin mode',
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN,
    )
    return enums.ADMIN_INIT


def on_admin_edit_working_hours(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    if query and query.data == 'back':
        msg_id = query.message.message_id
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    new_working_hours = update.message.text
    new_working_hours = fix_markdown(new_working_hours)
    config.set_value('working_hours', new_working_hours)
    msg = _('Working hours were changed.')
    return states.enter_settings(_, bot, chat_id, user_id, msg=msg)

#
#
# def on_admin_edit_contact_info(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     if update.callback_query and update.callback_query.data == 'back':
#         option_back_function(
#             bot, update, keyboards.bot_settings_keyboard(_),
#             'Bot settings')
#         return enums.ADMIN_BOT_SETTINGS
#     contact_info = update.message.text
#     config_session = get_config_session()
#     config_session['contact_info'] = contact_info
#     set_config_session(config_session)
#     bot.send_message(chat_id=update.message.chat_id,
#                      text='Contact info was changed',
#                      reply_markup=keyboards.bot_settings_keyboard(_),
#                      parse_mode=ParseMode.MARKDOWN)
#     return enums.ADMIN_BOT_SETTINGS
#
#
# def on_admin_add_discount(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     if update.callback_query and update.callback_query.data == 'back':
#         option_back_function(
#             bot, update, keyboards.order_options_keyboard(_),
#             _('💳 Order options'))
#         return enums.ADMIN_ORDER_OPTIONS
#     discount = update.message.text
#     discount = parse_discount(discount)
#     if discount:
#         discount, discount_min = discount
#         config_session = get_config_session()
#         config_session['discount'] = discount
#         config_session['discount_min'] = discount_min
#         set_config_session(config_session)
#         bot.send_message(chat_id=update.message.chat_id,
#                          text=_('Discount was changed'),
#                          reply_markup=keyboards.order_options_keyboard(_),
#                          parse_mode=ParseMode.MARKDOWN)
#         return enums.ADMIN_ORDER_OPTIONS
#     else:
#         msg = _('Invalid format')
#         msg += '\n'
#         msg += _('Enter discount like:\n'
#                  '50 > 500: all deals above 500$ will be -50$\n'
#                  '10% > 500: all deals above 500$ will be -10%\n'
#                  'Current discount: {} > {}').format(config.get_discount(), config.get_discount_min())
#         bot.send_message(update.message.chat_id,
#                          msg, reply_markup=keyboards.cancel_button(_),
#                          parse_mode=ParseMode.MARKDOWN)
#         return enums.ADMIN_ADD_DISCOUNT
#
#


def on_admin_bot_status(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('bot_on_off', 'only_for_registered'):
        if action == 'bot_on_off':
            value = not config.bot_on_off
            config.set_value(action, value)
        else:
            value = not config.only_for_registered
            config.set_value(action, value)
        msg = _('⚡️ Bot Status')
        reply_markup = keyboards.create_bot_status_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_BOT_STATUS
    if action == 'back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_edit_identification_stages(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, data = query.data.split('|')
    if action == 'back':
        msg = _('💳 Order options')
        bot.edit_message_text(msg, chat_id, msg_id,
                              reply_markup=keyboards.order_options_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_ORDER_OPTIONS
    if action in ('toggle', 'vip_toggle', 'delete'):
        stage = IdentificationStage.get(id=data)
        question = IdentificationQuestion.get(stage=stage)
        if action == 'toggle':
            stage.active = not stage.active
            stage.save()
        elif action == 'vip_toggle':
            stage.vip_required = not stage.vip_required
            stage.save()
        elif action == 'delete':
            question.delete_instance(recursive=True)
            stage.delete_instance(recursive=True)
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.vip_required, first_question))
        msg = _('👨 Edit identification process')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_edit_identification_keyboard(_, questions),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES
    if action == 'add':
        user_data['admin_edit_identification'] = {'new': True}
    elif action == 'edit':
        user_data['admin_edit_identification'] = {'new': False, 'id': data}
    msg = _('Select type of identification question')
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_edit_identification_type_keyboard(_),
                          parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_EDIT_IDENTIFICATION_QUESTION_TYPE


@user_passes
def on_admin_edit_identification_question_type(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'back':
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.vip_required, first_question))
        msg = _('👨 Edit identification process')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_edit_identification_keyboard(_, questions),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES
    if action in ('photo', 'text', 'video'):
        edit_options = user_data['admin_edit_identification']
        edit_options['type'] = action
        msg = _('Enter new question or variants to choose randomly, e.g.:\n'
                'Send identification photo ✌️\n'
                'Send identification photo 🖖')
        if not edit_options['new']:
            questions = IdentificationStage.get(id=edit_options['id']).identification_questions
            q_msg = ''
            for q in questions:
                q_content = escape(q.content)
                q_msg += '<i>{}</i>\n'.format(q_content)
            msg = _('Current questions:\n'
                    '{}\n{}').format(q_msg, msg)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_),
                              parse_mode=ParseMode.HTML)
        return enums.ADMIN_EDIT_IDENTIFICATION_QUESTION


@user_passes
def on_admin_edit_identification_question(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    if update.callback_query and update.callback_query.data == 'back':
        upd_msg = update.callback_query.message
        msg = _('Select type of identification question')
        bot.edit_message_text(msg, upd_msg.chat_id, upd_msg.message_id, reply_markup=keyboards.create_edit_identification_type_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_IDENTIFICATION_QUESTION_TYPE

    upd_msg = update.message
    edit_options = user_data['admin_edit_identification']
    msg_text = upd_msg.text
    if edit_options['new']:
        stage = IdentificationStage.create(type=edit_options['type'])
        for q_text in msg_text.split('\n'):
            if q_text:
                IdentificationQuestion.create(content=q_text, stage=stage)
        msg = _('Identification question has been created')
    else:
        stage = IdentificationStage.get(id=edit_options['id'])
        stage.type = edit_options['type']
        stage.save()
        for q in stage.identification_questions:
            q.delete_instance()
        for q_text in msg_text.split('\n'):
            if q_text:
                IdentificationQuestion.create(content=q_text, stage=stage)
        msg = _('Identification question has been changed')
    questions = []
    for stage in IdentificationStage:
        first_question = stage.identification_questions[0]
        first_question = first_question.content
        questions.append((stage.id, stage.active, stage.vip_required, first_question))
    bot.send_message(upd_msg.chat_id, msg, reply_markup=keyboards.create_edit_identification_keyboard(_, questions),
                          parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_EDIT_IDENTIFICATION_STAGES


@user_passes
def on_admin_edit_restriction(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    callback_data = query.data
    first, second = user_data['edit_restricted_area']
    if callback_data == 'save':
        msg = _('Restriction options changed')
        bot.edit_message_text(msg, chat_id, msg_id,
                              reply_markup=keyboards.order_options_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDER_OPTIONS
    if callback_data == 'first':
        first = not first
    elif callback_data == 'second':
        second = not second
    user_data['edit_restricted_area'] = (first, second)
    msg = _('🔥 Edit restricted area')
    bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                          reply_markup=keyboards.create_edit_restriction_keyboard(_, (first, second)))
    query.answer()
    return enums.ADMIN_EDIT_RESTRICTION


@user_passes
def on_admin_reset_all_data(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'yes':
        msg = _('Are you *TOTALLY* sure you want to delete database, session and all messages in channels?')
        keyboard = keyboards.create_reset_confirm_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_RESET_CONFIRM
    elif action == 'no':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_reset_confirm(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'yes':
        # delete logic
        for msg_row in ChannelMessageData:
            try:
                bot.delete_message(msg_row.channel, msg_row.msg_id)
            except TelegramError:
                pass
        delete_db()
        create_tables()
        init_bot_tables()
        msg = _('Database, session and all channel messages were deleted.')
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id, msg)
    elif action == 'no':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


def on_admin_product_price_groups(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'add':
        msg = _('Please enter the name of new price group:')
        keyboard = keyboards.cancel_button(_)
        user_data['price_group'] = {'edit': None}
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_CHANGE
    elif action == 'list':
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, groups)
        msg = _('Please select a price group:')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_LIST
    else:
        msg = _('💳 Order options')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.order_options_keyboard(_))
        query.answer()
        return enums.ADMIN_ORDER_OPTIONS


def on_admin_product_price_groups_list(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        group = GroupProductCount.get(id=val)
        product_counts = ProductCount.select(ProductCount.count, ProductCount.price)\
            .where(ProductCount.product_group == group).tuples()
        products = Product.select(Product.title).where(Product.group_price == group)
        group_name = escape(group.name)
        msg = _('Product price group:\n<i>{}</i>').format(group_name)
        msg += '\n\n'
        msg += _('Prices configured for this group:')
        msg += '\n'
        for count, price in product_counts:
            msg += '{} x ${}\n'.format(count, price)
        msg += '\n'
        msg += _('Products in this group price:')
        msg += '\n'
        for p in products:
            product_title = escape(p.title)
            msg += '<i>{}</i>'.format(product_title)
            msg += '\n'
        keyboard = keyboards.create_product_price_group_selected_keyboard(_, group.id)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return enums.ADMIN_PRODUCT_PRICE_GROUPS_SELECTED
    elif action == 'page':
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, groups, int(val))
        msg = _('Please select a price group:')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_LIST
    elif action == 'back':
        msg = _('💸 Product price groups')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_product_price_groups_keyboard(_))
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUPS


def on_admin_product_price_group_selected(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'edit':
        msg = _('Please enter new name for the price group:')
        user_data['price_group'] = {'edit': val}
        keyboard = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_CHANGE
    elif action == 'delete':
        group = GroupProductCount.get(id=val)
        has_products = Product.select().where(Product.group_price == group).exists()
        if has_products:
            msg = _('Cannot delete group which has products, please remove price group from product')
            query.answer(msg, show_alert=True)
            return enums.ADMIN_PRODUCT_PRICE_GROUPS_SELECTED
        else:
            ProductCount.delete().where(ProductCount.product_group == group)
            group.delete_instance()
            msg = _('Group was successfully deleted!')
            keyboard = keyboards.create_product_price_groups_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
            query.answer()
            return enums.ADMIN_PRODUCT_PRICE_GROUPS
    else:
        if action == 'back':
            msg = _('💸 Product price groups')
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_product_price_groups_keyboard(_))
            query.answer()
            return enums.ADMIN_PRODUCT_PRICE_GROUPS
        group = GroupProductCount.get(id=val)
        product_counts = ProductCount.select(ProductCount.count, ProductCount.price) \
            .where(ProductCount.product_group == group).tuples()
        products = Product.select(Product.title).where(Product.group_price == group)
        group_name = escape(group.name)
        msg = _('Product price group:\n<i>{}</i>').format(group_name)
        msg += '\n\n'
        msg += _('Prices configured for this group:')
        msg += '\n'
        for count, price in product_counts:
            msg += 'x {} ${}\n'.format(count, price)
        msg += '\n'
        msg += _('Products in this group price:')
        msg += '\n'
        for p in products:
            product_title = escape(p.title)
            msg += '<i>{}</i>'.format(product_title)
            msg += '\n'
        keyboard = keyboards.create_product_price_group_selected_keyboard(_, group.id)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return enums.ADMIN_PRODUCT_PRICE_GROUPS_SELECTED


def on_admin_product_price_group_change(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    if update.callback_query and update.callback_query.data == 'back':
        query = update.callback_query
        chat_id, msg_id = query.message.chat_id, query.message.message_id
        msg = _('💸 Product price groups')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_product_price_groups_keyboard(_))
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUPS
    group_name = update.effective_message.text
    user_data['price_group']['name'] = group_name
    msg = _('Enter new product prices\none per line in the format\n*COUNT PRICE*, e.g. *1 10*')
    keyboard = keyboards.cancel_button(_)
    bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_PRODUCT_PRICE_GROUP_SAVE


def on_admin_product_price_group_save(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if update.callback_query and update.callback_query.data == 'back':
        del user_data['price_group']
        query = update.callback_query
        msg_id = query.message.message_id
        msg = _('💸 Product price groups')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_product_price_groups_keyboard(_))
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUPS
    group_prices = update.effective_message.text
    group_edit = user_data['price_group']['edit']
    group_name = user_data['price_group']['name']
    prices = []
    for price_str in group_prices.split('\n'):
        try:
            count, price = price_str.split(' ')
        except ValueError:
            break
        try:
            count = int(count)
            price = Decimal(price)
        except (ValueError, InvalidOperation):
            break
        prices.append((count, price))
    if not prices:
        msg = _('Incorrect prices entered!')
        bot.send_message(chat_id, msg)
        msg = _('Enter new product prices\none per line in the format\n*COUNT PRICE*, e.g. *1 10*')
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_PRICE_GROUP_SAVE
    if group_edit:
        group = GroupProductCount.get(id=group_edit)
        ProductCount.delete().where(ProductCount.product_group == group).execute()
    else:
        group = GroupProductCount()
    group.name = group_name
    group.save()
    for count, price in prices:
        ProductCount.create(count=count, price=price, product_group=group)
    action_format = _('changed') if group_edit else _('added')
    group_name = escape(group.name)
    msg = _('Group <i>{}</i>  was successfully {}!').format(group_name, action_format)
    keyboard = keyboards.create_product_price_groups_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    return enums.ADMIN_PRODUCT_PRICE_GROUPS


def on_admin_btc_settings(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    btc_creds = BitcoinCredentials.select().first()
    wallet_id = btc_creds.wallet_id
    password = btc_creds.password
    if action == 'change_wallet_id':
        msg = _('Current wallet ID: *{}*').format(wallet_id if wallet_id else '')
        msg += '\n'
        msg += _('Enter new BTC wallet ID:')
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BTC_NEW_WALLET_ID
    if action == 'change_wallet_password':
        msg = _('Enter new password:')
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BTC_NEW_PASSWORD
    if action == 'back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    if action == 'disable':
        btc_creds.enabled = False
        btc_creds.save()
    elif action == 'enable':
        if not wallet_id or not password:
            msg = _('Please set BTC wallet ID and password before enabling BTC payments')
            query.answer(msg, show_alert=True)
            return enums.ADMIN_BTC_PAYMENTS
        else:
            btc_creds.enabled = True
            btc_creds.save()
            wallet_enable_hd(_, wallet_id, password)
    msg = _('💰 Bitcoin payments')
    msg += '\n'
    msg += _('Status: *{}*').format(_('Enabled') if btc_creds.enabled else _('Disabled'))
    msg += '\n'
    msg += _('Wallet ID: *{}*').format(wallet_id if wallet_id else '')
    msg += '\n'
    msg += _('Password set: {}').format('Yes' if password else 'No')
    keyboard = keyboards.create_btc_settings_keyboard(_, btc_creds.enabled)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    query.answer()
    return enums.ADMIN_BTC_PAYMENTS


def on_admin_btc_new_wallet_id(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    btc_creds = BitcoinCredentials.select().first()
    btc_enabled = btc_creds.enabled
    msg = _('💰 Bitcoin payments')
    msg += '\n'
    msg += _('Status: *{}*').format(_('Enabled') if btc_enabled else _('Disabled'))
    msg += '\n'
    keyboard = keyboards.create_btc_settings_keyboard(_, btc_enabled)
    query = update.callback_query
    btc_password = btc_creds.password
    if query and query.data == 'back':
        btc_wallet = btc_creds.wallet_id
        msg += _('Wallet ID: *{}*').format(btc_wallet if btc_wallet else '')
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_password else 'No')
        bot.edit_message_text(msg, query.message.chat_id, query.message.message_id,
                              reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
    else:
        wallet_id = update.message.text
        btc_creds.wallet_id = wallet_id
        btc_creds.save()
        if btc_creds.password:
            wallet_enable_hd(_, wallet_id, btc_creds.password)
        msg += _('Wallet ID: *{}*').format(wallet_id)
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_password else 'No')
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_BTC_PAYMENTS


def on_admin_btc_new_password(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    btc_creds = BitcoinCredentials.select().first()
    btc_enabled = btc_creds.enabled
    msg = _('💰 Bitcoin payments')
    msg += '\n'
    msg += _('Status: *{}*').format(_('Enabled') if btc_enabled else _('Disabled'))
    msg += '\n'
    keyboard = keyboards.create_btc_settings_keyboard(_, btc_enabled)
    query = update.callback_query
    btc_wallet = btc_creds.wallet_id
    if query and query.data == 'back':
        btc_password = btc_creds.password
        msg += _('Wallet ID: *{}*').format(btc_wallet if btc_wallet else '')
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_password else 'No')
        bot.edit_message_text(msg, query.message.chat_id, query.message.message_id,
                              reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
    else:
        btc_password = update.message.text
        btc_creds.password = btc_password
        btc_creds.save()
        msg += _('Wallet ID: *{}*').format(btc_wallet if btc_wallet else '')
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_password else 'No')
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_BTC_PAYMENTS

#
# def on_admin_change_currency(bot, update):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     query = update.callback_query
#     chat_id, msg_id = query.message.chat_id, query.message.message_id
#     data = query.data
#     if data in Currencies.CURRENCIES:
#         session = get_config_session()
#         session['currency'] = data
#         set_config_session(session)
#         msg = _('Currency was set to *{} {}*').format(*Currencies.CURRENCIES[data])
#         keyboard = keyboards.create_currencies_keyboard(_)
#         bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_SET_CURRENCIES
#     else:
#         msg = _('⚙ Bot settings')
#         keyboard = keyboards.bot_settings_keyboard(_)
#         bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.ADMIN_BOT_SETTINGS
#
#
# def on_start_btc_processing(bot, update):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     query = update.callback_query
#     order_id = query.data.split('|')[1]
#     process_running = session_client.json_get('btc_procs')
#     if process_running:
#         process_running = order_id in process_running
#     if process_running:
#         msg = _('Process is running already.')
#         query.answer(msg, show_alert=True)
#     else:
#         order = Order.get(id=order_id)
#         set_btc_proc(order.id)
#         process_btc_payment(bot, order)
#         chat_id, msg_id = query.message.chat_id, query.message.message_id
#         shortcuts.delete_channel_msg(bot, chat_id, msg_id)
#         query.answer()



