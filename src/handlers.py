import datetime
from decimal import Decimal
import random
import re

from telegram import ParseMode, ReplyKeyboardRemove
from telegram.ext import ConversationHandler
from telegram.utils.helpers import escape_markdown
from peewee import fn, JOIN

from . import keyboards, enums, shortcuts, messages, states
from .cart_helper import Cart
from .decorators import user_passes
from .btc_wrapper import BtcWallet, BtcSettings, BtcError
from .btc_processor import set_btc_proc, process_btc_payment
from .helpers import get_user_id, get_username, get_locale, get_trans, config, logger, \
    get_channel_trans, clear_user_data, get_service_channel, get_couriers_channel, calculate_discount
from .models import User, Product, ProductCategory, Order, Location, OrderBtcPayment, BitcoinCredentials, \
    Channel, UserPermission, IdentificationStage, IdentificationQuestion, UserIdentificationAnswer,\
    ChannelPermissions, WorkingHours, BtcStage, ProductWarehouse, CourierLocation, Currencies, CourierChat, \
    CourierChatMessage, IdentificationPermission, Lottery, LotteryParticipant, Review, ReviewQuestion, ReviewQuestionRank


@user_passes
def on_start(bot, update, user_data):
    user_id = get_user_id(update)
    username = get_username(update)
    locale = get_locale(update)
    clear_user_data(user_data, 'menu_id', 'cart', 'courier_menu')
    user = User.get(telegram_id=user_id)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if user.is_admin:
        log_msg = 'Starting session for Admin - From admin_id: %s, username: @%s, language: %s'
    else:
        log_msg = 'Starting - Session for user_id: %s, username: @%s, language: %s'
    logger.info(log_msg, user_id, username, locale)
    menu_allowed = (not config.only_for_registered or user.is_registered) or config.watch_non_registered or config.order_non_registered
    if menu_allowed:
        return states.enter_menu(bot, update, user_data)
    else:
        return states.enter_registration(_, bot, chat_id)


def get_channel_id(bot, update):
    print(update.effective_chat.id)


@user_passes
def on_menu(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    username = get_username(update)
    user = User.get(telegram_id=user_id)
    query = update.callback_query
    data = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    clear_user_data(user_data, 'menu_id', 'cart', 'products_msgs', 'category_id', 'courier_menu')
    if not config.only_for_registered or user.is_registered:
        if data == 'menu_products':
            products_msgs = user_data.get('products_msgs')
            if products_msgs:
                for p_msg_id in products_msgs:
                    bot.delete_message(chat_id, p_msg_id)
                del user_data['products_msgs']
            categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
            if categories:
                reply_markup = keyboards.general_select_one_keyboard(_, categories)
                msg = _('Please select a category:')
                bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
                query.answer()
                return enums.BOT_PRODUCT_CATEGORIES
            else:
                products = shortcuts.get_users_products(user)
                if products.exists():
                    bot.delete_message(chat_id, msg_id)
                    products_msgs = shortcuts.send_products(_, bot, user_data, chat_id, products, user)
                    user_data['products_msgs'] = products_msgs
                    return states.enter_menu(bot, update, user_data, query_id=query.id)
                else:
                    query.answer()
                    return enums.BOT_INIT
        elif data == 'menu_order':
            delivery_method = config.delivery_method
            if not delivery_method:
                msg = _('Sorry, we have technical issues. Cannot make order now.')
                query.answer(msg, show_alert=True)
                return enums.BOT_INIT
            if Cart.not_empty(user_data):
                unfinished_orders = Order.select()\
                    .where(Order.user == user, Order.status.in_((Order.PROCESSING, Order.CONFIRMED))).exists()
                if unfinished_orders:
                    msg = _('You cannot make new order if previous order is not finished')
                    query.answer(msg, show_alert=True)
                    return enums.BOT_INIT
                inactive_products = list(Cart.get_product_ids(user_data))
                inactive_products = Product.select().where(Product.id.in_(inactive_products), Product.is_active == False)
                if inactive_products.exists():
                    names = ', '.join(product.title for product in inactive_products)
                    msg = _('Sorry, products "{}" is not active now.').format(names)
                    query.answer(msg)
                    for product in inactive_products:
                        Cart.remove_all(user_data, product.id)
                    products_msgs = user_data.get('products_msgs')
                    if products_msgs:
                        for p_msg_id in products_msgs:
                            bot.delete_message(chat_id, p_msg_id)
                        del user_data['products_msgs']
                    category_id = user_data.get('category_id')
                    if category_id:
                        cat = ProductCategory.get(id=category_id)
                        cat_title = escape_markdown(cat.title)
                        msg = _('Category `{}` products:').format(cat_title)
                        cat_msg = bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
                        products_msgs = [cat_msg['message_id']]
                        products = shortcuts.get_users_products(user, cat)
                        if products.exists():
                            products_msgs += shortcuts.send_products(_, bot, user_data, chat_id, products, user)
                            user_data['products_msgs'] = products_msgs
                        return states.enter_menu(bot, update, user_data, query.id)
                    else:
                        products = shortcuts.get_users_products(user)
                        if products.exists():
                            products_msgs = shortcuts.send_products(_, bot, user_data, chat_id, products, user)
                            user_data['products_msgs'] = products_msgs
                        menu_msg_id = user_data['menu_id']
                        return states.enter_menu(bot, update, user_data, menu_msg_id, query.id)
                if user.is_admin:
                    log_msg = 'Starting order process for Admin - From admin_id: %s, username: @%s'
                else:
                    log_msg = 'Starting order process - From user_id: %s, username: @%s'
                logger.info(log_msg, user_id, username)
                user_data['order_details'] = {}
                if delivery_method == 'both':
                    return states.enter_order_delivery(_, bot, chat_id, msg_id, query.id)
                else:
                    action_map = {'delivery': Order.DELIVERY, 'pickup': Order.PICKUP}
                    user_data['order_details']['delivery'] = action_map[delivery_method]
                    if Location.select().exists():
                        user_data['listing_page'] = 1
                        return states.enter_order_locations(_, bot, chat_id,  delivery_method, msg_id, query.id)
                    else:
                        return states.enter_order_delivery_address(_, bot, chat_id, query.id)
            else:
                msg = _('Your cart is empty. Please add something to the cart.')
                query.answer(msg, show_alert=True)
                return enums.BOT_INIT
        elif data == 'menu_channels':
            channels = Channel.select(Channel.name, Channel.link).join(ChannelPermissions) \
                .where(ChannelPermissions.permission == user.permission).tuples()
            msg = _('⭐ Channels')
            user_data['listing_page'] = 1
            reply_markup = keyboards.channels_keyboard(_, channels)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return enums.BOT_CHANNELS
        elif data == 'menu_language':
            msg = _('🈚︎  Languages')
            language = user.locale
            reply_markup = keyboards.bot_language_keyboard(_, language)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.BOT_LANGUAGE_CHANGE
        elif data == 'menu_currency':
            msg = _('💲 Bot Currency')
            reply_markup = keyboards.create_currencies_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.BOT_CURRENCY_CHANGE
        elif data.startswith('menu_register'):
            return states.enter_registration(_, bot, chat_id, msg_id, query.id)
        elif data == 'menu_hours':
            msg = messages.get_working_hours_msg(_)
            reply_markup = keyboards.main_keyboard(_, user)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.BOT_INIT
        elif data == 'menu_contact':
            msg = config.contact_info
            reply_markup = keyboards.main_keyboard(_, user)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.BOT_INIT
        elif data.startswith('product'):
            action, product_id = data.split('|')
            menu_msg_id = user_data['menu_id']
            product_id = int(product_id)
            product = Product.get(id=product_id)
            if not product.is_active:
                query.answer(_('Sorry, this product is not active now.'))
                Cart.remove_all(user_data, product_id)
                products_msgs = user_data.get('products_msgs')
                if products_msgs:
                    for p_msg_id in products_msgs:
                        bot.delete_message(chat_id, p_msg_id)
                    del user_data['products_msgs']
                category_id = user_data.get('category_id')
                if category_id:
                    cat = ProductCategory.get(id=category_id)
                    cat_title = escape_markdown(cat.title)
                    msg = _('Category `{}` products:').format(cat_title)
                    cat_msg = bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
                    products_msgs = [cat_msg['message_id']]
                    products = shortcuts.get_users_products(user, cat)
                    if products.exists():
                        products_msgs += shortcuts.send_products(_, bot, user_data, chat_id, products, user)
                        user_data['products_msgs'] = products_msgs
                    return states.enter_menu(bot, update, user_data, menu_msg_id, query.id)
                else:
                    products = shortcuts.get_users_products(user)
                    if products.exists():
                        products_msgs = shortcuts.send_products(_, bot, user_data, chat_id, products, user)
                        user_data['products_msgs'] = products_msgs
                    return states.enter_menu(bot, update, user_data, menu_msg_id, query.id)
            product_count = Cart.get_product_count(user_data, product_id)
            if action == 'product_add':
                user_data = Cart.add(user_data, product_id, user)
            else:
                user_data = Cart.remove(user_data, product_id, user)
            new_count = Cart.get_product_count(user_data, product_id)
            if product_count == new_count:
                query.answer()
                return enums.BOT_INIT
            price_group = Cart.get_product_price_group(product, user)
            subtotal = Cart.get_product_subtotal(user_data, product, price_group)
            product_title, prices = shortcuts.get_full_product_info(product, price_group)
            msg = messages.create_product_description(_, user.currency, product_title, prices, new_count, subtotal)
            reply_markup = keyboards.create_product_keyboard(_, product_id, user_data)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return states.enter_menu(bot, update, user_data, menu_msg_id, query.id)
        elif data == 'menu_settings':
            msg = _('⚙️ Settings')
            if user.is_logistic_manager:
                reply_markup = keyboards.settings_logistic_manager_keyboard(_, user.allowed_settings)
            else:
                reply_markup = keyboards.settings_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.ADMIN_MENU
        elif data == 'menu_my_orders':
            msg = _('📖 My Orders')
            reply_markup = keyboards.create_my_orders_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.BOT_MY_ORDERS
        elif data == 'menu_chat':
            orders = Order.select().join(User, JOIN.LEFT_OUTER, on=Order.courier) \
                .where(Order.user == user, Order.status == Order.PROCESSING, User.permission == UserPermission.COURIER)\
                .order_by(Order.date_created.desc())
            date_pattern = '%d-%m-%Y'
            orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_pattern)), order.id) for order in orders]
            msg = _('Select an order')
            user_data['listing_page'] = 1
            reply_markup = keyboards.general_select_one_keyboard(_, orders)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.BOT_CHAT_ORDERS
        else:
            logger.warn('Unknown query: %s', query.data)
    else:
        return states.enter_registration(_, bot, chat_id, msg_id)


@user_passes
def on_bot_chat_orders(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user = User.get(telegram_id=user_id)
        orders = Order.select().where(Order.user == user, Order.status == Order.PROCESSING).order_by(
            Order.date_created.desc())
        date_pattern = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_pattern)), order.id) for order in
                  orders]
        msg = _('Select an order')
        user_data['listing_page'] = page
        reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_CHAT_ORDERS
    elif action == 'select':
        order = Order.get(id=val)
        try:
            btc_data = OrderBtcPayment.get(order=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        msg = messages.create_service_notice(_, order, btc_data)
        reply_markup = keyboards.chat_order_selected(_)
        user_data['chat_order_id'] = order.id
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_CHAT_ORDER_SELECTED
    else:
        return states.enter_menu(bot, update, user_data, msg_id, query.id)


@user_passes
def on_bot_chat_order_selected(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'back':
        page = user_data['listing_page']
        user = User.get(telegram_id=user_id)
        orders = Order.select().where(Order.user == user, Order.status == Order.PROCESSING).order_by(
            Order.date_created.desc())
        date_pattern = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_pattern)), order.id) for order in
                  orders]
        msg = _('Select an order')
        reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_CHAT_ORDERS
    else:
        msg = _('⌨️ Chat with courier')
        order_id = user_data['chat_order_id']
        user = User.get(telegram_id=user_id)
        order = Order.get(id=order_id)
        courier = order.courier
        try:
            chat = CourierChat.get(order=order, courier=courier, user=user)
        except:
            chat = CourierChat.create(order=order, courier=courier, user=user)
        if not chat.active:
            courier_id = courier.telegram_id
            courier_trans = get_trans(courier_id)
            msg = courier_trans('Order №{}:').format(order_id)
            msg += '\n'
            msg += courier_trans('Client has started a chat.')
            reply_markup = keyboards.chat_with_client_keyboard(_, order_id)
            menu_msg = bot.send_message(courier_id, msg, reply_markup=reply_markup)
            chat.courier_menu_id = menu_msg['message_id']
            chat.active = True
        reply_markup = keyboards.chat_with_courier_keyboard(_, order_id)
        menu_msg = bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        chat.user_menu_id = menu_msg['message_id']
        chat.save()
        query.answer()
        return enums.BOT_CHAT_WITH_COURIER


@user_passes
def on_chat_with_courier(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, order_id = query.data.split('|')
    user = User.get(telegram_id=user_id)
    order = Order.get(id=order_id)
    courier = order.courier
    chat = CourierChat.get(user=user, order=order, courier=courier)
    if not chat.active:
        msg = _('Chat is not active anymore.')
        query.answer(msg, show_alert=True)
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    if action == 'client_chat_send':
        unread_messages = CourierChatMessage.select() \
            .where(CourierChatMessage.chat == chat, CourierChatMessage.author == user,
                   CourierChatMessage.read == False).exists()
        if unread_messages:
            msg = _('Courier didn\'t read previous message. Can\'t send another yet.')
            query.answer(msg, show_alert=True)
            return enums.BOT_CHAT_WITH_COURIER
        user_data['chat_order_id'] = order_id
        msg = _('Please send text, photo or video:')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        chat.user_menu_id = None
        chat.save()
        query.answer()
        return enums.BOT_CHAT_SEND
    elif action == 'client_chat_finish':
        CourierChatMessage.update({CourierChatMessage.read: True, CourierChatMessage.replied: True})\
            .where(CourierChatMessage.chat == chat).execute()
        chat.active = False
        chat.save()
        courier_id = courier.telegram_id
        user_trans = get_trans(courier_id)
        msg = user_trans('Order №{}:').format(order_id)
        msg += '\n'
        msg = user_trans('Client has ended a chat.')
        bot.send_message(courier_id, msg)
        msg = _('Chat has been ended.')
        query.answer(msg)
        return states.enter_menu(bot, update, user_data, msg_id)
    elif action == 'client_chat_ping':
        msg = _('Notification was sent to courier')
        reply_markup = keyboards.chat_with_courier_keyboard(_, order_id)
        menu_msg = bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        chat.user_msg_id = menu_msg['message_id']
        chat.ping_sent = True
        chat.save()
        no_response_msgs = CourierChatMessage.select()\
            .where(CourierChatMessage.chat == chat, CourierChatMessage.author == user, CourierChatMessage.replied == False)
        for no_resp_msg in no_response_msgs:
            no_resp_msg.replied = True
            no_resp_msg.save()
        courier_id = courier.telegram_id
        user_trans = get_trans(courier_id)
        msg = user_trans('Is everything ok? The client is waiting for you!')
        reply_markup = keyboards.client_waiting_keyboard(_, chat.id)
        if chat.courier_menu_id:
            bot.edit_message_text(msg, courier_id, chat.courier_menu_id, reply_markup=reply_markup)
        else:
            bot.send_message(courier_id, msg, reply_markup=reply_markup)
        service_trans = get_channel_trans()
        msg = service_trans('Order №{}').format(order_id)
        msg += '\n'
        msg += service_trans('Courier don\'t respond to client messages.')
        msg += '\n'
        msg += service_trans('Courier: @{} Client: @{}').format(courier.username, user.username)
        service_channel = get_service_channel()
        shortcuts.send_channel_msg(bot, msg, service_channel, parse_mode=None)
        shortcuts.check_courier_available(chat.id, bot)
        return enums.BOT_CHAT_SEND


@user_passes
def on_chat_send(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    order_id = user_data['chat_order_id']
    user = User.get(telegram_id=user_id)
    order = Order.get(id=order_id)
    courier = order.courier
    chat = CourierChat.get(user=user, order=order, courier=courier)
    if query and query.data == 'back':
        msg = _('⌨️ Chat with courier')
        reply_markup = keyboards.chat_with_courier_keyboard(_, order_id)
        msg_id = query.message.message_id
        menu_msg = bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        chat.user_menu_id = menu_msg['message_id']
        chat.save()
        query.answer()
        return enums.BOT_CHAT_WITH_COURIER
    else:
        if not chat.active:
            msg = _('Chat is not active anymore.')
            bot.send_message(chat_id, msg)
            return states.enter_menu(bot, update, user_data)
        for msg_type in ('photo', 'video', 'text'):
            msg_data = getattr(update.message, msg_type)
            if msg_data:
                break
        status_msg = _('Message has been sent.')
        if msg_type in ('photo', 'video'):
            if type(msg_data) == list:
                msg_data = msg_data[-1]
            msg_data = msg_data.file_id
            if msg_type == 'video':
                sent_msg = bot.send_video(chat_id, msg_data, caption=status_msg)
            else:
                sent_msg = bot.send_photo(chat_id, msg_data, caption=status_msg)
        else:
            msg = msg_data
            msg += '\n\n'
            msg += status_msg
            sent_msg = bot.send_message(chat_id, msg)
        chat_msg = CourierChatMessage.create(chat=chat, msg_type=msg_type, message=msg_data,
                                             sent_msg_id=sent_msg['message_id'], author=user)
        msg = _('⌨️ Chat with courier')
        ping = False
        if not chat.ping_sent:
            unanswered_messages = CourierChatMessage.select() \
                .where(CourierChatMessage.author == user, CourierChatMessage.chat == chat, CourierChatMessage.replied == False).count()
            if unanswered_messages >= 2:
                ping = True
        reply_markup = keyboards.chat_with_courier_keyboard(_, order_id, ping)
        menu_msg = bot.send_message(chat_id, msg, reply_markup=reply_markup)
        chat.user_menu_id = menu_msg['message_id']
        chat.save()
        courier_id = courier.telegram_id
        courier_trans = get_trans(courier_id)
        msg = courier_trans('Order №{}:').format(order.id)
        msg += '\n'
        msg += courier_trans('You have new message from client').format(user.username)
        reply_markup = keyboards.chat_courier_msg_keyboard(_, chat_msg.id)
        if chat.courier_menu_id:
            bot.edit_message_text(msg, courier_id, chat.courier_menu_id, reply_markup=reply_markup)
        else:
            bot.send_message(courier_id, msg, reply_markup=reply_markup)
        chat.courier_menu_id = None
        chat.save()
        return enums.BOT_CHAT_WITH_COURIER


@user_passes
def on_open_chat_msg(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    chat_msg_id = query.data.split('|')[1]
    chat_msg = CourierChatMessage.get(id=chat_msg_id)
    chat = chat_msg.chat
    msg_type = chat_msg.msg_type
    courier = chat.courier
    courier_msg_id = chat_msg.sent_msg_id
    client_msg = chat_msg.message
    read_msg = _('Msg has been read. ✅')
    msg = _('⌨️ Chat with courier')
    if msg_type in ('video', 'photo'):
        bot.delete_message(chat_id, msg_id)
        caption = _('From courier')
        if msg_type == 'video':
            bot.send_video(chat_id, client_msg, caption=caption)
            bot.edit_message_caption(courier.telegram_id, courier_msg_id, caption=read_msg)
        else:
            bot.send_photo(chat_id, client_msg, caption=caption)
            bot.edit_message_caption(courier.telegram_id, courier_msg_id, caption=read_msg)
    else:
        open_msg = _('From courier:')
        open_msg += '\n\n'
        open_msg += client_msg
        bot.edit_message_text(open_msg, chat_id, msg_id)
        query.answer()
        client_msg = client_msg
        client_msg += '\n\n'
        client_msg += read_msg
        bot.edit_message_text(client_msg, courier.telegram_id, courier_msg_id)
    chat_msg.read = True
    chat_msg.save()
    reply_markup = keyboards.chat_with_courier_keyboard(_, chat.order.id)
    if not chat.user_menu_id:
        menu_msg = bot.send_message(chat_id, msg, reply_markup=reply_markup)
        chat.user_menu_id = menu_msg['message_id']
        chat.save()
    return enums.BOT_CHAT_WITH_COURIER


@user_passes
def on_order_delivery(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('pickup', 'delivery'):
        action_map = {'pickup': Order.PICKUP, 'delivery': Order.DELIVERY}
        user_data['order_details']['delivery'] = action_map[action]
        if Location.select().exists():
            user_data['listing_page'] = 1
            return states.enter_order_locations(_, bot, chat_id, action, msg_id, query.id)
        else:
            return states.enter_order_delivery_address(_, bot, chat_id, query.id)
    elif action == 'back':
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_locations(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        delivery_method = user_data['order_details']['delivery']
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_order_locations(_, bot, chat_id, delivery_method, msg_id, query.id, page)
    elif action == 'select':
        delivery_method = user_data['order_details']['delivery']
        user_data['order_details']['location_id'] = val
        if delivery_method == Order.PICKUP:
            return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
        else:
            return states.enter_order_delivery_address(_, bot, chat_id, query.id)
    elif action == 'back':
        del user_data['listing_page']
        if config.delivery_method == 'both':
            return states.enter_order_delivery(_, bot, chat_id, msg_id, query.id)
        else:
            return states.enter_menu(bot, update, user_data)
    elif action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_delivery_address(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    delivery_method = user_data['order_details']['delivery']
    location = update.message.location
    if location:
        loc = {'lat': location['latitude'], 'long': location['longitude']}
        user_data['order_details']['geo_location'] = loc
        return states.enter_order_shipping_time(_, bot, chat_id)
    answer = update.message.text
    if answer == _('↩ Back'):
        locations_exist = Location.select().exists()
        if locations_exist:
            return states.enter_order_locations(_, bot, chat_id, delivery_method)
        if config.delivery_method == 'both':
            return states.enter_order_delivery(_, bot, chat_id)
        else:
            return states.enter_menu(bot, update, user_data)
    elif answer == _('❌ Cancel'):
        msg = _('Order was cancelled')
        bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
        return states.enter_menu(bot, update, user_data)
    else:
        user_data['order_details']['address'] = answer
        msg = _('✅ Address set')
        bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
        return states.enter_order_shipping_time(_, bot, chat_id)


@user_passes
def on_order_datetime_select(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'now':
        now = datetime.datetime.now()
        if not shortcuts.check_order_datetime_allowed(now):
            msg = _('Cannot make order today.')
            msg += '\n'
            msg += messages.get_working_hours_msg(_)
            return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id, msg)
        user_data['order_details']['datetime'] = 'now'
        user = User.get(telegram_id=user_id)
        now = datetime.datetime.now()
        id_stages = None
        if not user.is_registered:
            id_stages = IdentificationStage.select().where(IdentificationStage.active == True)
        elif now - datetime.timedelta(hours=24) > user.registration_time:
            if not Order.select().where(Order.user == User).exists():
                id_stages = IdentificationStage.select().join(IdentificationPermission)\
                    .where(IdentificationStage.for_order == True, IdentificationStage.active == True,
                           IdentificationPermission.permission == user.permission)
        if id_stages and id_stages.exists():
            print(list(id_stages))
            return states.enter_order_identify(_, bot, chat_id, user_data, id_stages)
        if BitcoinCredentials.select().first().enabled:
            return states.enter_order_payment_type(_, bot, chat_id)
        else:
            return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id)
    elif action == 'datetime':
        msg = _('Please select day')
        msg += '\n'
        msg += messages.get_working_hours_msg(_)
        state = enums.BOT_CHECKOUT_DATE_SELECT
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id, msg, cancel=True)
    elif action == 'back':
        delivery_method = user_data['order_details']['delivery']
        if delivery_method == Order.DELIVERY:
            return states.enter_order_delivery_address(_, bot, chat_id, query.id)
        else:
            return states.enter_order_locations(_, bot, chat_id, action, msg_id, query.id)
    elif action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    else:
        return states.enter_unknown_command(_, bot, query)


# @user_passes
# def on_order_today_time_select(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     query = update.callback_query
#     chat_id, msg_id = query.message.chat_id, query.message.message_id
#     action = query.data
#     if action == 'closest':
#         user_data['order_details']['datetime'] = 'closest'
#         return states.enter_order_phone_number(_, bot, chat_id, query.id)
#     elif action == 'pick':
#         now = datetime.datetime.now()
#         user_data['order_details']['datetime'] = now
#         msg = _('Please select time')
#         msg += '\n\n'
#         msg += messages.get_working_hours_msg(_)
#         try:
#             open_time = WorkingHours.get(day=now.weekday()).open_time
#         except WorkingHours.DoesNotExist:
#             msg = _('Cannot make order today.')
#             msg += '\n'
#             msg += messages.get_working_hours_msg(_)
#             return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id, msg)
#         now_time = datetime.time(hour=now.hour, minute=now.minute)
#         start_time = max([now_time, open_time])
#         state = enums.BOT_CHECKOUT_TIME_SELECT
#         return shortcuts.initialize_time_picker(_, bot, user_data, chat_id, state, msg_id, query.id, msg, start_time, cancel=True)
#     elif action == 'back':
#         return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
#     else:
#         msg = _('Order was cancelled')
#         bot.edit_message_text(msg, chat_id, msg_id)
#         query.answer()
#         return states.enter_menu(bot, update, user_data)


@user_passes
def on_order_date_select(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'day':
        day = int(val)
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        now = datetime.datetime.now()
        order_datetime = now.replace(year=year, month=month, day=day)
        if order_datetime < now:
            msg = _('Delivery date can\'t be before current date')
            print(msg)
            query.answer(msg)
            return enums.BOT_CHECKOUT_DATE_SELECT
        try:
            WorkingHours.get(day=order_datetime.weekday())
        except WorkingHours.DoesNotExist:
            msg = _('Please select day according to working days')
            print(msg)
            query.answer(msg, show_alert=True)
            return enums.BOT_CHECKOUT_DATE_SELECT
        user_data['order_details']['datetime'] = order_datetime
        state = enums.BOT_CHECKOUT_TIME_SELECT
        msg = _('Please select time')
        msg += '\n\n'
        msg += messages.get_working_hours_msg(_)
        working_hours = WorkingHours.get(day=order_datetime.weekday())
        time_range = (working_hours.open_time, working_hours.close_time)
        return shortcuts.initialize_time_picker(_, bot, user_data, chat_id, state, msg_id, query.id, msg, time_range, cancel=True)
    elif action in ('year', 'month'):
        msg = _('Please select a day')
        query.answer(msg)
        return enums.BOT_CHECKOUT_DATE_SELECT
    elif action == 'back':
        return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
    elif action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_time_select(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'done':
        hour, minute = user_data['time_picker']['hour'], user_data['time_picker']['minute']
        order_date = user_data['order_details']['datetime']
        try:
            WorkingHours.get(day=order_date.weekday())
        except WorkingHours.DoesNotExist:
            msg = _('Please select working day')
            msg += '\n'
            msg += messages.get_working_hours_msg(_)
            state = enums.BOT_CHECKOUT_DATE_SELECT
            return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id, msg, cancel=True)
        order_datetime = datetime.datetime(year=order_date.year, month=order_date.month, day=order_date.day, hour=hour, minute=minute)
        now = datetime.datetime.now()
        if order_datetime.day == now.day and now > order_datetime:
            msg = _('Time should be later than current')
            query.answer(msg)
            return enums.BOT_CHECKOUT_TIME_SELECT
        user_data['order_details']['datetime'] = order_datetime
        user = User.get(telegram_id=user_id)
        now = datetime.datetime.now()
        id_stages = None
        if not user.is_registered:
            id_stages = IdentificationStage.select().where(IdentificationStage.active == True)
        elif now - datetime.timedelta(hours=24) > user.registration_time:
            if not Order.select().where(Order.user == User).exists():
                id_stages = IdentificationStage.select().join(IdentificationPermission) \
                    .where(IdentificationStage.for_order == True, IdentificationStage.active == True,
                           IdentificationPermission.permission == user.permission)
        if id_stages and id_stages.exists():
            return states.enter_order_identify(_, bot, chat_id, user_data, id_stages)
        if BitcoinCredentials.select().first().enabled:
            return states.enter_order_payment_type(_, bot, chat_id)
        else:
            return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id)
    elif action == 'back':
        msg = _('Pick working day')
        msg += '\n'
        msg += messages.get_working_hours_msg(_)
        state = enums.BOT_CHECKOUT_DATE_SELECT
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id, msg, cancel=True)
    elif action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_identification(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    id_data = user_data['order_details']['identification']
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query:
        msg_id = query.message.message_id
        if query.data == 'back':
            passed_ids = id_data['passed_ids']
            if passed_ids:
                prev_stage, prev_q = passed_ids.pop()
                id_data['current_id'] = prev_stage
                id_data['current_q_id'] = prev_q
                question = IdentificationQuestion.get(id=prev_q)
                msg = question.content
                prev_stage = IdentificationStage.get(id=prev_stage)
                if prev_stage.type == 'phone':
                    reply_markup = keyboards.phone_number_request_keyboard(_)
                    state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
                else:
                    reply_markup = keyboards.back_cancel_keyboard(_)
                    state = enums.BOT_CHECKOUT_IDENTIFY
                bot.send_message(chat_id, msg, reply_markup=reply_markup)
                return state
            else:
                del user_data['order_details']['identification']
                return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
        elif query.data == 'cancel':
            msg = _('Order was cancelled')
            bot.edit_message_text(msg, chat_id, msg_id)
            query.answer()
            return states.enter_menu(bot, update, user_data)
        else:
            return states.enter_unknown_command(_, bot, query)
    current_id = id_data['current_id']
    current_stage = IdentificationStage.get(id=current_id)
    answer_type = current_stage.type
    if answer_type in ('photo', 'video'):
        try:
            answer = getattr(update.message, answer_type)
            if type(answer) == list:
                answer = answer[-1]
            answer = answer.file_id
        except (IndexError, AttributeError):
            text = _(answer_type)
            msg = _('_Please upload a {} as an answer_').format(text)
            bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
            return enums.BOT_CHECKOUT_IDENTIFY
    else:
        answer = update.message.text
        if answer_type == 'id':
            answer = answer.replace(' ', '')
            match = re.search(r'^\d{9}$', answer)
            if not match:
                msg = _('Please enter correct ID number (9 numbers)')
                bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
                return enums.BOT_CHECKOUT_IDENTIFY
    current_q_id = id_data['current_q_id']
    id_data['answers'].append((current_id, current_q_id, answer))
    passed_ids = id_data['passed_ids']
    passed_ids.append((current_id, current_q_id))
    passed_stages_ids = [v[0] for v in passed_ids]
    user = User.get(telegram_id=user_id)
    if not user.is_registered:
        stages_left = IdentificationStage.select()\
            .where(IdentificationStage.id.not_in(passed_stages_ids), IdentificationStage.active == True)
    else:
        stages_left = IdentificationStage.select().join(IdentificationPermission)\
            .where(IdentificationStage.id.not_in(passed_stages_ids), IdentificationStage.for_order == True,
                   IdentificationStage.active == True, IdentificationPermission.permission == user.permission)
    if stages_left.exists():
        next_stage = stages_left[0]
        questions = next_stage.identification_questions
        question = random.choice(list(questions))
        id_data['current_id'] = next_stage.id
        id_data['current_q_id'] = question.id
        msg = question.content
        if next_stage.type == 'phone':
            reply_markup = keyboards.phone_number_request_keyboard(_)
            state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
        else:
            reply_markup = keyboards.back_cancel_keyboard(_)
            state = enums.BOT_CHECKOUT_IDENTIFY
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        return state
    if BitcoinCredentials.select().first().enabled:
        return states.enter_order_payment_type(_, bot, chat_id)
    else:
        return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id)


@user_passes
def on_order_identification_phone_number(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    answer = update.message.text
    id_data = user_data['order_details']['identification']
    if answer == _('↩ Back'):
        passed_ids = id_data['passed_ids']
        if passed_ids:
            prev_stage, prev_q = passed_ids.pop()
            id_data['current_id'] = prev_stage
            id_data['current_q_id'] = prev_q
            question = IdentificationQuestion.get(id=prev_q)
            msg = question.content
            prev_stage = IdentificationStage.get(id=prev_stage)
            if prev_stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY
            bot.send_message(chat_id, msg, reply_markup=reply_markup)
            return state
        else:
            del user_data['order_details']['identification']
            return states.enter_order_shipping_time(_, bot, chat_id)
    elif answer == _('❌ Cancel'):
        msg = _('Order was cancelled')
        bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
        return states.enter_menu(bot, update, user_data)
    answer = update.message.contact.phone_number
    if not answer:
        answer = answer.replace(' ', '')
        match = re.search(r'^(\+?\d{10}$)', answer)
        if not match:
            msg = _('✒️ Please enter correct phone number')
            bot.send_message(chat_id, msg, reply_markup=keyboards.phone_number_request_keyboard(_))
            return enums.BOT_CHECKOUT_IDENTIFY_PHONE
    msg = _('✅ Phone number set')
    bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
    current_id = id_data['current_id']
    current_q_id = id_data['current_q_id']
    id_data['answers'].append((current_id, current_q_id, answer))
    passed_ids = id_data['passed_ids']
    passed_ids.append((current_id, current_q_id))
    passed_stages_ids = [v[0] for v in passed_ids]
    user = User.get(telegram_id=user_id)
    if not user.is_registered:
        stages_left = IdentificationStage.select() \
            .where(IdentificationStage.id.not_in(passed_stages_ids), IdentificationStage.active == True)
    else:
        stages_left = IdentificationStage.select().join(IdentificationPermission) \
            .where(IdentificationStage.id.not_in(passed_stages_ids), IdentificationStage.for_order == True,
                   IdentificationStage.active == True, IdentificationPermission.permission == user.permission)
    if stages_left.exists():
        next_stage = stages_left[0]
        questions = next_stage.identification_questions
        question = random.choice(list(questions))
        id_data['current_id'] = next_stage.id
        id_data['current_q_id'] = question.id
        msg = question.content
        if next_stage.type == 'phone':
            reply_markup = keyboards.phone_number_request_keyboard(_)
            state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
        else:
            reply_markup = keyboards.back_cancel_keyboard(_)
            state = enums.BOT_CHECKOUT_IDENTIFY
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        return state
    if BitcoinCredentials.select().first().enabled:
        return states.enter_order_payment_type(_, bot, chat_id)
    else:
        return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id)


@user_passes
def on_order_payment_type(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('btc', 'delivery'):
        if action == 'btc':
            btc_payment = True
        else:
            btc_payment = False
        user_data['order_details']['btc_payment'] = btc_payment
        return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id, msg_id, query.id)
    elif action == 'back':
        id_data = user_data['order_details'].get('identification')
        if id_data:
            id_data['passed_ids'].pop()
            last_q_id = id_data['current_q_id']
            last_question = IdentificationQuestion.get(id=last_q_id)
            msg = last_question.content
            stage = IdentificationStage.get(id=id_data['current_id'])
            if stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return state
        else:
            return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
    elif action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_confirm(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'confirm':
        order_data = user_data['order_details']
        delivery_method = order_data['delivery']
        location = None
        if delivery_method == Order.DELIVERY:
            loc_id = order_data.get('location_id')
            if loc_id:
                location = Location.get(id=loc_id)
        shipping_time = order_data['datetime']
        if shipping_time == 'now':
            shipping_time = _('⏰ Closest time')
        else:
            shipping_time = shipping_time.strftime('%d %b, %H:%M')
        order_address = order_data.get('address')
        user = User.get(telegram_id=user_id)
        order = Order.create(user=user, location=location, shipping_method=delivery_method, shipping_time=shipping_time,
                             address=order_address)
        btc_payment = order_data.get('btc_payment')
        if btc_payment:
            btc_value = order_data['btc_value']
            btc_value = Decimal(btc_value)
            wallet = BtcWallet(_, BtcSettings.WALLET, BtcSettings.PASSWORD, BtcSettings.SECOND_PASSWORD)
            try:
                btc_address, xpub = wallet.create_hd_account_address('Order #{}'.format(order.id))
            except BtcError:
                order.delete_instance()
                return states.enter_generating_address_failed(bot, update, user_data)
            order.btc_payment = True
            order.save()
            btc_data = OrderBtcPayment.create(order=order, amount=btc_value, xpub=xpub, address=btc_address)
        else:
            btc_data = None
        _ = get_channel_trans()
        order_id = order.id
        logger.info('New order confirmed  - Order №%s, From user_id %s, username: @%s',
                          order_id,
                          update.effective_user.id,
                          update.effective_user.username)

        # ORDER CONFIRMED, send the details to service channel
        location_title = location.title if location else '-'
        text = _('Order №{}, Location: {}\nUser @{}').format(order_id, location_title, user.username)
        service_channel = get_service_channel()
        coordinates = order_data.get('geo_location')
        shortcuts.send_order_identification_answers(bot, service_channel, order, channel=True)
        if coordinates:
            lat, long = coordinates['lat'], coordinates['long']
            order.coordinates = lat + '|' + long + '|'
        total = Cart.fill_order(user_data, order, user)
        delivery_fee = shortcuts.calculate_delivery_fee(delivery_method, location, total, user.is_vip_client)
        discount = calculate_discount(total)
        order.delivery_fee = delivery_fee
        order.total_cost = total
        order.discount = discount
        order.save()
        reply_markup = keyboards.show_order_keyboard(_, order_id)
        channel_msg_id = shortcuts.send_channel_msg(bot, text, service_channel, reply_markup, order, parse_mode=None)
        order.order_text_msg_id = channel_msg_id
        order.save()
        if btc_payment:
            set_btc_proc(order.id)
            process_btc_payment(bot, order)
        user_data['cart'] = {}
        first_name = escape_markdown(update.effective_user.first_name)
        msg = config.order_complete_text.format(first_name)
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN)
        if btc_payment:
            msg = _('Please transfer *{}* BTC to address:').format(btc_data.amount)
            msg += '\n'
            msg += _('*{}*').format(btc_address)
            bot.send_message(chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
        return states.enter_menu(bot, update, user_data)
    elif action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    elif action == 'back':
        btc_enabled = BitcoinCredentials.select().first().enabled
        if btc_enabled:
            return states.enter_order_payment_type(_, bot, chat_id, msg_id, query.id)
        id_data = user_data['order_details'].get('identification')
        if id_data:
            id_data['passed_ids'].pop()
            last_q_id = id_data['current_q_id']
            last_question = IdentificationQuestion.get(id=last_q_id)
            msg = last_question.content
            stage = IdentificationStage.get(id=id_data['current_id'])
            if stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return state
        else:
            return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_btc_conversion_failed(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    elif action == 'back':
        id_data = user_data['order_details'].get('identification')
        if id_data:
            id_data['passed_ids'].pop()
            last_q_id = id_data['current_q_id']
            last_question = IdentificationQuestion.get(id=last_q_id)
            msg = last_question.content
            stage = IdentificationStage.get(id=id_data['current_id'])
            if stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return state
        else:
            return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
    elif action == '🔄try_again':
        return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_generating_address_failed(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    elif action == 'back':
        id_data = user_data['order_details'].get('identification')
        if id_data:
            id_data['passed_ids'].pop()
            last_q_id = id_data['current_q_id']
            last_question = IdentificationQuestion.get(id=last_q_id)
            msg = last_question.content
            stage = IdentificationStage.get(id=id_data['current_id'])
            if stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return state
        else:
            return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
    elif action == '🔄try_again':
        return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_order_btc_too_low(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'cancel':
        msg = _('Order was cancelled')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return states.enter_menu(bot, update, user_data)
    elif action == 'back':
        id_data = user_data['order_details'].get('identification')
        if id_data:
            id_data['passed_ids'].pop()
            last_q_id = id_data['current_q_id']
            last_question = IdentificationQuestion.get(id=last_q_id)
            msg = last_question.content
            stage = IdentificationStage.get(id=id_data['current_id'])
            if stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_CHECKOUT_IDENTIFY
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return state
        else:
            return states.enter_order_shipping_time(_, bot, chat_id, msg_id, query.id)
    elif action == '🔄try_again':
        return states.enter_order_confirmation(_, bot, chat_id, user_data, user_id, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_registration(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'register':
        user = User.get(telegram_id=user_id)
        if user.is_pending_registration:
            msg = _('You already completed registration process.')
            msg += '\n'
            msg += _('Would you like to clear previous answers and register again?')
            reply_markup = keyboards.are_you_sure_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return enums.BOT_REGISTRATION_REPEAT
        identification_stages = IdentificationStage.filter(active=True)
        if len(identification_stages):
            first_stage = identification_stages[0]
            questions = first_stage.identification_questions
            question = random.choice(list(questions))
            user_data['user_registration'] = {
                'identification': {'passed_ids': [], 'current_id': first_stage.id,
                                   'current_q_id': question.id, 'answers': []}
            }
            msg = _('Please complete identification process.')
            msg += '\n\n'
            msg += escape_markdown(question.content)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.back_cancel_keyboard(_))
            return enums.BOT_IDENTIFICATION
        else:
            msg = _('Registration is not allowed now')
            bot.edit_message_text(msg, chat_id, msg_id)
            if not config.only_for_registered:
                return states.enter_menu(bot, update, user_data)
    else:
        if config.only_for_registered:
            bot.delete_message(chat_id, msg_id)
            return ConversationHandler.END
        else:
            return states.enter_menu(bot, update, user_data, msg_id)


@user_passes
def on_registration_repeat(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'yes':
        user = User.get(telegram_id=user_id)
        shortcuts.remove_user_registration(user)
        identification_stages = IdentificationStage.filter(active=True)
        if len(identification_stages):
            first_stage = identification_stages[0]
            questions = first_stage.identification_questions
            question = random.choice(list(questions))
            user_data['user_registration'] = {
                'identification': {'passed_ids': [], 'current_id': first_stage.id,
                                   'current_q_id': question.id, 'answers': []}
            }
            msg = _('Please complete identification process.')
            msg += '\n\n'
            msg += escape_markdown(question.content)
            if first_stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_IDENTIFICATION_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_IDENTIFICATION
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            return state
        else:
            msg = _('Registration is not allowed now')
            bot.edit_message_text(msg, chat_id, msg_id)
            if not config.only_for_registered:
                return states.enter_menu(bot, update, user_data)
    elif action == 'no':
        if config.only_for_registered:
            return states.enter_registration(_, bot, chat_id, msg_id, query.id)
        else:
            return states.enter_menu(bot, update, user_data, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_registration_identification(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    id_data = user_data['user_registration']['identification']
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query:
        msg_id = query.message.message_id
        if query.data == 'back':
            passed_ids = id_data['passed_ids']
            if passed_ids:
                prev_stage, prev_q = passed_ids.pop()
                id_data['current_id'] = prev_stage
                id_data['current_q_id'] = prev_q
                question = IdentificationQuestion.get(id=prev_q)
                msg = question.content
                prev_stage = IdentificationStage.get(id=prev_stage)
                if prev_stage.type == 'phone':
                    reply_markup = keyboards.phone_number_request_keyboard(_)
                    state = enums.BOT_IDENTIFICATION_PHONE
                else:
                    reply_markup = keyboards.back_cancel_keyboard(_)
                    state = enums.BOT_IDENTIFICATION
                bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
                return state
            else:
                del user_data['user_registration']
                return states.enter_registration(_, bot, chat_id, msg_id)
        elif query.data == 'cancel':
            del user_data['user_registration']
            if config.only_for_registered:
                return states.enter_registration(_, bot, chat_id, msg_id)
            else:
                return states.enter_menu(bot, update, user_data, msg_id)
        else:
            return states.enter_unknown_command(_, bot, query)
    current_id = id_data['current_id']
    current_stage = IdentificationStage.get(id=current_id)
    answer_type = current_stage.type
    if answer_type in ('photo', 'video'):
        try:
            answer = getattr(update.message, answer_type)
            if type(answer) == list:
                answer = answer[-1]
            answer = answer.file_id
        except (IndexError, AttributeError):
            answer = None
    else:
        answer = update.message.text
    # trans here
    if not answer:
        text = _(answer_type)
        msg = _('Please upload a {} as an answer').format(text)
        bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_), )
        return enums.BOT_IDENTIFICATION
    current_q_id = id_data['current_q_id']
    id_data['answers'].append((current_id, current_q_id, answer))
    passed_ids = id_data['passed_ids']
    passed_ids.append((current_id, current_q_id))
    passed_stages_ids = [v[0] for v in passed_ids]
    stages_left = IdentificationStage.select().where(
        IdentificationStage.active == True & IdentificationStage.id.not_in(passed_stages_ids))
    if stages_left:
        next_stage = stages_left[0]
        questions = next_stage.identification_questions
        question = random.choice(list(questions))
        id_data['current_id'] = next_stage.id
        id_data['current_q_id'] = question.id
        msg = question.content
        if next_stage.type == 'phone':
            reply_markup = keyboards.phone_number_request_keyboard(_)
            state = enums.BOT_IDENTIFICATION_PHONE
        else:
            reply_markup = keyboards.back_cancel_keyboard(_)
            state = enums.BOT_IDENTIFICATION
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        return state
    else:
        user = User.get(telegram_id=user_id)
        for stage_id, q_id, answer in id_data['answers']:
            stage = IdentificationStage.get(id=stage_id)
            question = IdentificationQuestion.get(id=q_id)
            UserIdentificationAnswer.create(stage=stage, question=question, user=user, content=answer)
        del user_data['user_registration']
        user.permission = UserPermission.PENDING_REGISTRATION
        user.save()
        msg = _('Thank you for registration! Your application will be reviewed by admin.')
        bot.send_message(chat_id, msg)
        if not config.only_for_registered:
            return states.enter_menu(bot, update, user_data)
        else:
            return states.enter_registration(_, bot, chat_id)


@user_passes
def on_registration_identification_phone(bot, update, user_data):
    answer = update.message.text
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    id_data = user_data['user_registration']['identification']
    if answer == _('↩ Back'):
        if id_data:
            prev_stage, prev_q = id_data['passed_ids'].pop()
            id_data['current_id'] = prev_stage
            id_data['current_q_id'] = prev_q
            question = IdentificationQuestion.get(id=prev_q)
            msg = question.content
            prev_stage = IdentificationStage.get(id=prev_stage)
            if prev_stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_IDENTIFICATION_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_IDENTIFICATION
            bot.send_message(chat_id, msg, reply_markup=reply_markup)
            return state
        else:
            if id_data:
                del user_data['user_registration']
            return states.enter_registration(_, bot, chat_id)
    elif answer == _('❌ Cancel'):
        if id_data:
            del user_data['user_registration']
        if config.only_for_registered:
            return states.enter_registration(_, bot, chat_id)
        else:
            return states.enter_menu(bot, update, user_data)
    else:
        try:
            answer = update.message.contact.phone_number
        except AttributeError:
            answer = update.message.text
            answer = answer.replace(' ', '')
            match = re.search(r'^(\+?\d{10}$)', answer)
            if not match:
                error_msg = _('✒️ Please enter correct phone number')
                bot.send_message(chat_id, error_msg)
                return enums.BOT_IDENTIFICATION_PHONE
        current_q_id = id_data['current_q_id']
        current_id = id_data['current_id']
        id_data['answers'].append((current_id, current_q_id, answer))
        passed_ids = id_data['passed_ids']
        passed_ids.append((current_id, current_q_id))
        passed_stages_ids = [v[0] for v in passed_ids]
        stages_left = IdentificationStage.select().where(
            IdentificationStage.active == True & IdentificationStage.id.not_in(passed_stages_ids))
        msg = _('✅ Phone number set')
        bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
        if stages_left:
            next_stage = stages_left[0]
            questions = next_stage.identification_questions
            question = random.choice(list(questions))
            id_data['current_id'] = next_stage.id
            id_data['current_q_id'] = question.id
            msg = question.content
            if next_stage.type == 'phone':
                reply_markup = keyboards.phone_number_request_keyboard(_)
                state = enums.BOT_IDENTIFICATION_PHONE
            else:
                reply_markup = keyboards.back_cancel_keyboard(_)
                state = enums.BOT_IDENTIFICATION
            bot.send_message(chat_id, msg, reply_markup=reply_markup)
            return state
        user = User.get(telegram_id=user_id)
        if id_data:
            for stage_id, q_id, answer in id_data['answers']:
                stage = IdentificationStage.get(id=stage_id)
                question = IdentificationQuestion.get(id=q_id)
                UserIdentificationAnswer.create(stage=stage, question=question, user=user, content=answer)
            del user_data['user_registration']
        user.permission = UserPermission.PENDING_REGISTRATION
        user.save()
        msg = _('Thank you for registration! Your application will be reviewed by admin.')
        bot.send_message(chat_id, msg, reply_markup=ReplyKeyboardRemove())
        if not config.only_for_registered:
            return states.enter_menu(bot, update, user_data)
        else:
            return states.enter_registration(_, bot, chat_id)

@user_passes
def on_channels(bot, update, user_data):
    query = update.callback_query
    action = query.data
    if action == 'back':
        return states.enter_menu(bot, update, user_data, query.message.message_id, query.id)


def on_error(bot, update, error):
    logger.error('Error: %s', error)


def checkout_fallback_command_handler(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    msg = _('Cannot process commands when checking out')
    query.answer(msg, show_alert=True)


@user_passes
def on_my_orders(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    data = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if data == 'back':
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    elif data == 'by_date':
        state = enums.BOT_MY_ORDERS_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state
    elif data == 'last_order':
        user = User.get(telegram_id=user_id)
        order = Order.select().where(Order.user == user).order_by(Order.date_created.desc()).get()
        order_id = order.id
        msg = _('Order №{}').format(order.id)
        can_cancel = order.status in (Order.CONFIRMED, Order.PROCESSING)
        reply_markup = keyboards.create_my_order_keyboard(_, order_id, can_cancel)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_MY_LAST_ORDER


@user_passes
def on_my_order_date(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        msg = _('📖 My Orders')
        reply_markup = keyboards.create_my_orders_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.BOT_MY_ORDERS
    elif action in ('day', 'month', 'year'):
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = datetime.date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.BOT_MY_ORDERS_DATE
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = datetime.date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.BOT_MY_ORDERS_DATE
                del user_data['calendar']
                date_query = shortcuts.get_date_subquery(Order, first_date=first_date, second_date=second_date)
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Order, year=year)
        else:
            date_query = shortcuts.get_date_subquery(Order, month=month, year=year)
        user = User.get(telegram_id=user_id)
        orders = Order.select().where(Order.user == user, *date_query)
        if len(orders) == 1:
            order = orders[0]
            msg = _('Order №{}').format(order.id)
            can_cancel = order.status in (Order.CONFIRMED, Order.PROCESSING)
            reply_markup = keyboards.create_my_order_keyboard(_, order.id, can_cancel)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.BOT_MY_LAST_ORDER
        else:
            orders_data = [(order.id, order.date_created.strftime('%d/%m/%Y')) for order in orders]
            orders = [(_('Order №{} {}').format(order_id, order_date), order_id) for order_id, order_date in orders_data]
            user_data['my_orders'] = {'page': 1, 'orders_list': orders}
            msg = _('Select order')
            reply_markup = keyboards.general_select_one_keyboard(_, orders)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.BOT_MY_ORDERS_SELECT
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_my_order_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        del user_data['my_orders']
        state = enums.BOT_MY_ORDERS_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state
    elif action == 'page':
        page = int(val)
        orders = user_data['my_orders']['orders_list']
        user_data['my_orders']['page'] = page
        reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
        msg = _('Select order:')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_MY_ORDERS_SELECT
    elif action == 'select':
        order = Order.get(id=val)
        msg = _('Order №{}').format(order.id)
        can_cancel = order.status in (Order.CONFIRMED, Order.PROCESSING)
        reply_markup = keyboards.create_my_order_keyboard(_, order.id, can_cancel)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_MY_LAST_ORDER
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_my_last_order(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        listing_data = user_data.get('my_orders')
        if listing_data:
            orders = listing_data['orders_list']
            page = listing_data['page']
            reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
            msg = _('Select order:')
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.BOT_MY_ORDERS_SELECT
        msg = _('📖 My Orders')
        reply_markup = keyboards.create_my_orders_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.BOT_MY_ORDERS
    order_id = int(val)
    order = Order.get(id=order_id)
    if action == 'cancel':
        if order.status in (Order.PROCESSING, Order.CONFIRMED):
            msg = _('Are you sure?')
            user_data['my_order'] = {'id': order_id}
            reply_markup = keyboards.are_you_sure_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.BOT_MY_LAST_ORDER_CANCEL
        elif order.status == Order.CANCELLED:
            error_msg = _('Cannot cancel - order was cancelled already.')
        elif order.status == Order.DELIVERED:
            error_msg = _('Cannot cancel - order was delivered already.')
        query.answer(error_msg, show_alert=True)
        return enums.BOT_MY_LAST_ORDER
    elif action == 'show':
        try:
            btc_data = OrderBtcPayment.get(order=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        msg = messages.create_service_notice(_, order, btc_data)
        can_cancel = order.status in (Order.CONFIRMED, Order.PROCESSING)
        reply_markup = keyboards.create_my_order_keyboard(_, order_id, can_cancel)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.BOT_MY_LAST_ORDER


@user_passes
def on_my_last_order_cancel(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    username = get_username(update)
    _ = get_trans(user_id)
    action = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    order_id = user_data['my_order']['id']
    order = Order.get(id=order_id)
    if action in ('yes', 'no'):
        if action == 'yes':
            order.status = order.CANCELLED
            order.save()
            service_chat = get_service_channel()
            channel_trans = get_channel_trans()
            msg = channel_trans('Order №{} was cancelled by client @{}.').format(order.id, username)
            shortcuts.send_channel_msg(bot, msg, service_chat, order=order, parse_mode=None)
            logger.info('Order № %s was cancelled by user: @%s', order.id, username)
            msg = _('Order №{} was cancelled.').format(order.id)
        elif action == 'no':
            msg = _('Order №{}').format(order.id)
        reply_markup = keyboards.create_my_order_keyboard(_, order.id, False)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.BOT_MY_LAST_ORDER
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_bot_language_change(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    if data in ('back', 'iw', 'en'):
        if data in ('iw', 'en'):
            user = User.get(telegram_id=user_id)
            user.locale = data
            user.save()
        return states.enter_menu(bot, update, user_data, query.message.message_id)
    else:
        states.enter_unknown_command(_, bot, query)


@user_passes
def on_bot_currency_change(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in Currencies.CURRENCIES:
        user = User.get(telegram_id=user_id)
        user.currency = action
        user.save()
        currency_repr = '{} {}'.format(*Currencies.CURRENCIES[action])
        msg = _('Currency was set to {}').format(currency_repr)
        reply_markup = keyboards.create_currencies_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_CURRENCY_CHANGE
    elif action == 'back':
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


def service_channel_sendto_courier_handler(bot, update, user_data):
    query = update.callback_query
    data = query.data
    label, telegram_id, order_id, message_id = data.split('|')
    order = Order.get(id=order_id)
    _ = get_channel_trans()
    courier = User.get(telegram_id=telegram_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    warehouse_error_msg = None
    for item in order.order_items:
        product = item.product
        if product.warehouse_active:
            try:
                warehouse_count = ProductWarehouse.get(courier=courier, product=product).count
            except ProductWarehouse.DoesNotExist:
                warehouse_count = 0
            if item.count > warehouse_count:
                warehouse_error_msg = _('Courier don\'t have enough credits in warehouse')
                warehouse_error_msg += '\n'
                warehouse_error_msg += _('Product: `{}`\nCount: {}\nCourier credits: {}\n').format(product.title,
                                                                                                  item.count,
                                                                                                  warehouse_count)
                break
    if warehouse_error_msg:
        couriers = User.select(User.username, User.telegram_id).join(UserPermission) \
            .where(UserPermission.permission == UserPermission.COURIER, User.banned == False).tuples()
        keyboard = keyboards.couriers_choose_keyboard(_, couriers, order_id, msg_id)
        bot.edit_message_text(warehouse_error_msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return
    order.courier = courier
    order.status = order.PROCESSING
    shortcuts.change_order_products_credits(order, courier=order.courier)
    order.save()
    shortcuts.delete_channel_msg(bot, chat_id, msg_id)
    user_trans = get_trans(telegram_id)
    try:
        btc_data = OrderBtcPayment.get(order=order)
    except OrderBtcPayment.DoesNotExist:
        btc_data = None
    msg = messages.create_service_notice(user_trans, order, btc_data, for_courier=True)
    reply_markup = keyboards.courier_order_status_keyboard(user_trans, order_id, courier)
    bot.send_message(telegram_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    query.answer(text=_('Message sent'), show_alert=True)


@user_passes
def on_service_order_message(bot, update, user_data):
    query = update.callback_query
    action, order_id = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    order = Order.get(id=order_id)
    if action == 'order_btc_refresh':
        _ = get_channel_trans()
        btc_data = OrderBtcPayment.get(order=order)
        service_msg = messages.create_service_notice(_, order, btc_data)
        if not order.order_hidden_text == service_msg:
            keyboard = keyboards.service_channel_keyboard(_, order)
            msg_id = shortcuts.edit_channel_msg(bot, service_msg, chat_id, msg_id, keyboard, order)
            order.order_hidden_text = service_msg
            order.order_text_msg_id = msg_id
            order.save()
        query.answer()
    elif action == 'order_btc_notification':
        user_id = order.user.telegram_id
        _ = get_trans(user_id)
        btc_data = OrderBtcPayment.get(order=order)
        if btc_data.payment_stage == BtcStage.SECOND:
            msg = _('Client made payment already')
            query.answer(msg, show_alert=True)
        else:
            user_notice = messages.create_user_btc_notice(_, order)
            bot.send_message(user_id, user_notice, parse_mode=ParseMode.MARKDOWN)
            query.answer(_('Client was notified'))
        _ = get_channel_trans()
        service_msg = messages.create_service_notice(_, order, btc_data)
        if not order.order_hidden_text == service_msg:
            keyboard = keyboards.service_channel_keyboard(_, order)
            msg_id = shortcuts.edit_channel_msg(bot, service_msg, chat_id, msg_id, keyboard, order)
            order.order_hidden_text = service_msg
            order.order_text_msg_id = msg_id
            order.save()
    elif action == 'order_show':
        _ = get_channel_trans()
        shortcuts.send_order_identification_answers(bot, chat_id, order, channel=True)
        try:
            shortcuts.delete_channel_msg(bot, chat_id, msg_id)
        except Exception as e:
            logger.exception("Failed to delete message\nException: " + str(e))
        if order.coordinates:
            lat, long, msg_id = order.coordinates.split('|')
            coords_msg_id = shortcuts.send_channel_location(bot, chat_id, lat, long)
            order.coordinates = lat + '|' + long + '|' + coords_msg_id
        try:
            btc_data = OrderBtcPayment.get(order=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        msg = messages.create_service_notice(_, order,  btc_data)
        keyboard = keyboards.service_channel_keyboard(_, order)
        msg_id = shortcuts.send_channel_msg(bot, msg, chat_id, keyboard, order)
        order.order_text_msg_id = msg_id
        order.order_hidden_text = msg
        order.save()
    elif action == 'order_hide':
        _ = get_channel_trans()
        for answer in order.identification_answers:
            answer_msg_id = answer.msg_id
            if answer_msg_id:
                shortcuts.delete_channel_msg(bot, chat_id, msg_id)
        if order.coordinates:
            msg_id = order.coordinates.split('|')[-1]
            shortcuts.delete_channel_msg(bot, chat_id, msg_id)
        location = order.location.title if order.location else '-'
        msg = _('Order №{}, Location {}\nUser @{}').format(order_id, location, order.user.username)
        reply_markup = keyboards.show_order_keyboard(_, order.id)
        msg_id = shortcuts.edit_channel_msg(bot, msg, chat_id, msg_id, reply_markup, order, parse_mode=None)
        order.order_text_msg_id = msg_id
        order.save()
    elif action == 'order_send_to_specific_courier':
        _ = get_channel_trans()
        if order.status == Order.DELIVERED:
            msg = _('Order is delivered. Cannot send it to couriers again.')
            query.answer(text=msg, show_alert=True)
            return
        couriers = User.select(User.username, User.telegram_id).join(UserPermission)\
            .where(UserPermission.permission == UserPermission.COURIER, User.banned == False).tuples()
        msg = ''
        for username, user_id in couriers:
            locations = CourierLocation.select().join(User).where(User.id == user_id)
            locations = ', '.join([loc.title for loc in locations])
            msg += 'Courier: @{} Locations: {}'.format(username, locations)
            msg += '\n'
        msg += '\n'
        msg = _('Please choose who to send:')
        keyboard = keyboards.couriers_choose_keyboard(_, couriers, order_id, msg_id)
        shortcuts.send_channel_msg(bot, msg, get_service_channel(), keyboard, order)
        query.answer()
    elif action == 'order_send_to_couriers':
        _ = get_channel_trans()
        if config.has_courier_option:
            _ = get_channel_trans()
            if order.status in (order.DELIVERED, order.CANCELLED):
                msg_map = {order.DELIVERED: 'delivered',  order.CANCELLED: 'cancelled'}
                msg = _('Order is {}. Cannot send it to couriers again.').format(msg_map[order.status])
                query.answer(text=msg, show_alert=True)
            else:
                couriers_channel = get_couriers_channel()
                msgs_ids = ''
                if len(order.identification_answers):
                    answers_ids = shortcuts.send_order_identification_answers(bot, couriers_channel, order, send_one=True, channel=True)
                    msgs_ids += ','.join(answers_ids)
                if order.coordinates:
                    lat, lng = order.coordinates.split('|')[:2]
                    coords_msg_id = shortcuts.send_channel_location(bot, chat_id, lat, lng)
                    msgs_ids += ',' + coords_msg_id
                delivery_method = order.shipping_method
                order_location = order.location
                if order_location:
                    order_location = order_location.title
                keyboard = keyboards.service_notice_keyboard(order_id, _, msgs_ids, order_location, delivery_method)
                try:
                    btc_data = OrderBtcPayment.get(order=order)
                except OrderBtcPayment.DoesNotExist:
                    btc_data = None
                msg = messages.create_service_notice(_, order, btc_data)
                shortcuts.send_channel_msg(bot, msg, couriers_channel, keyboard, order)
                query.answer(text=_('Order sent to couriers channel'), show_alert=True)
        query.answer(text=_('You have disabled courier\'s option'), show_alert=True)
    elif action == 'order_cancel':
        _ = get_channel_trans()
        if order.status == order.CANCELLED:
            msg = _('Order is cancelled already')
            query.answer(text=msg, show_alert=True)
        else:
            msg = _('Are you sure?')
            keyboard = keyboards.cancel_order_confirm(_, order_id)
            shortcuts.send_channel_msg(bot, msg, chat_id, keyboard, order)
            query.answer()
    elif action == 'order_send_to_self':
        _ = get_channel_trans()
        if order.status in (order.DELIVERED, order.CANCELLED):
            msg_map = {order.DELIVERED: 'delivered', order.CANCELLED: 'cancelled'}
            msg = _('Order is {}. Cannot send it to couriers again.').format(msg_map[order.status])
            query.answer(text=msg, show_alert=True)
        else:
            usr_id = get_user_id(update)
            _ = get_trans(usr_id)
            user = User.get(telegram_id=usr_id)
            order.courier = user
            order.status = order.CONFIRMED
            order.save()
            shortcuts.change_order_products_credits(order)
            try:
                btc_data = OrderBtcPayment.get(order=order)
            except OrderBtcPayment.DoesNotExist:
                btc_data = None
            msg = messages.create_service_notice(_, order, btc_data, for_courier=True)
            reply_markup = keyboards.courier_order_status_keyboard(_, order.id, user)
            bot.send_message(usr_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer(text=_('Message sent'), show_alert=True)
    elif action == 'order_ban_client':
        user = order.user
        if user.is_admin:
            _ = get_channel_trans()
            msg = _('Admin couldn\'t be added to black-list')
            query.answer(msg, show_alert=True)
        else:
            user.banned = True
            user.save()
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, you have been black-listed').format(user.username)
            bot.send_message(user.telegram_id, msg)
            username = escape_markdown(user.username)
            _ = get_channel_trans()
            msg = _('*{}* has been added to black-list!').format(username)
            shortcuts.send_channel_msg(bot, msg, chat_id, order=order)
            query.answer()
    elif action == 'order_chat_log':
        _ = get_channel_trans()
        try:
            chat = CourierChat.get(user = order.user, order = order, courier = order.courier)
        except CourierChat.DoesNotExist:
            msg = _('Courier and client didn\'t chat yet')
            query.answer(msg, show_alert=True)
        else:
            chat_messages = CourierChatMessage.select().where(CourierChatMessage.chat == chat)\
                .order_by(CourierChatMessage.date_created.asc())
            if chat_messages.exists():
                for answer in order.identification_answers:
                    answer_msg_id = answer.msg_id
                    if answer_msg_id:
                        shortcuts.delete_channel_msg(bot, chat_id, msg_id)
                if order.coordinates:
                    msg_id = order.coordinates.split('|')[-1]
                    shortcuts.delete_channel_msg(bot, chat_id, msg_id)

                msg = _('Order №{} chat log:').format(order.id)
                shortcuts.edit_channel_msg(bot, msg, chat_id, msg_id, order=order, parse_mode=None)
                for chat_msg in chat_messages:
                    time_sent = chat_msg.date_created.strftime('%d %b, %H:%M')
                    msg = _('{}\nFrom @{}:').format(time_sent, chat_msg.author.username)
                    msg_data = chat_msg.message
                    msg_type = chat_msg.msg_type
                    if msg_type == 'photo':
                        shortcuts.send_channel_photo(bot, msg_data, chat_id, caption=msg, order=order)
                    elif msg_type == 'video':
                        shortcuts.send_channel_video(bot, msg_data, chat_id, caption=msg, order=order)
                    else:
                        msg += '\n'
                        msg += msg_data
                        shortcuts.send_channel_msg(bot, msg, chat_id, order=order, parse_mode=None)

                location = order.location.title if order.location else '-'
                msg = _('Order №{}, Location {}\nUser @{}').format(order_id, location, order.user.username)
                reply_markup = keyboards.show_order_keyboard(_, order.id)
                msg_id = shortcuts.send_channel_msg(bot, msg, chat_id, reply_markup, order, parse_mode=None)
                order.order_text_msg_id = msg_id
                order.save()
            else:
                msg = _('There are no messages yet.')
                query.answer(msg, show_alert=True)
    else:
        logger.info('That part is not handled yet: {}'.format(action))


def cancel_order_confirm(bot, update):
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    _ = get_channel_trans()
    action, order_id = query.data.split('|')
    if action in ('cancel_order_yes', 'cancel_order_delete'):
        order = Order.get(Order.id == order_id)
        order.status = Order.CANCELLED
        order.save()
        if action == 'cancel_order_delete':
            shortcuts.delete_order_channels_msgs(bot, order)
            msg = _('Order messages were deleted!')
            query.answer(msg)
    shortcuts.delete_channel_msg(bot, chat_id, msg_id)


@user_passes
def on_service_order_finished_message(bot, update, user_data):
    query = update.callback_query
    action, order_id = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    order = Order.get(id=order_id)
    _ = get_channel_trans()
    if action == 'finished_order_delete':
        shortcuts.delete_order_channels_msgs(bot, order)
        msg = _('Order messages were deleted!')
        query.answer(msg)
    elif action == 'finished_order_show':
        try:
            shortcuts.delete_channel_msg(bot, chat_id, msg_id)
        except Exception as e:
            logger.exception("Failed to delete message\nException: " + str(e))
        shortcuts.send_order_identification_answers(bot, chat_id, order, channel=True)
        if order.coordinates:
            lat, long, msg_id = order.coordinates.split('|')
            coords_msg_id = shortcuts.send_channel_location(bot, chat_id, lat, long)
            order.coordinates = lat + '|' + long + '|' + coords_msg_id
        try:
            btc_data = OrderBtcPayment.get(order=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        msg = messages.create_service_notice(_, order, btc_data)
        lottery_available = shortcuts.check_lottery_available(order)
        keyboard = keyboards.order_finished_keyboard(_, order_id, False, lottery_available)
        msg_id = shortcuts.send_channel_msg(bot, msg, chat_id, keyboard, order)
        order.order_text_msg_id = msg_id
        order.save()
    elif action == 'finished_order_hide':
        courier = order.courier
        status = courier.permission.get_permission_display()
        msg = _('Order №{} was delivered by {} @{}\n').format(order.id, status, courier.username)
        msg += _('Client: @{}').format(order.user.username)
        keyboard = keyboards.order_finished_keyboard(_, order_id)
        msg_id = shortcuts.edit_channel_msg(bot, msg, chat_id, msg_id, keyboard, order, parse_mode=None)
        order.order_text_msg_id = msg_id
        order.save()
    elif action == 'finished_order_lottery':
        if shortcuts.check_lottery_available(order):
            lottery = Lottery.get(completed_date=None, active=True)
            tickets_used = LotteryParticipant.select()\
                .where(LotteryParticipant.lottery == lottery, LotteryParticipant.is_pending == False).count()
            if lottery.num_tickets > tickets_used:
                is_pending = False
                msg = _('User has been added to lottery')
            else:
                is_pending = True
                msg = _('There are no tickets left')
                msg += '\n'
                msg += _('User has been added to lottery queue')
            all_codes = LotteryParticipant.filter(is_pending=False, lottery=lottery)
            all_codes = [item.code for item in all_codes]
            shortcuts.add_client_to_lottery(lottery, order.user, all_codes, is_pending)
        else:
            msg = _('Lottery is not available for this user')
        query.answer(msg, show_alert=True)


@user_passes
def on_client_order_delivered(bot, update, user_data):
    query = update.callback_query
    action, order_id = query.data.split('|')
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    order = Order.get(id=order_id)
    if action == 'delivered_order_lottery':
        lottery_available = shortcuts.check_lottery_available(order)
        if not lottery_available:
            msg = _('Lottery is not available anymore')
        else:
            lottery = Lottery.get(completed_date=None, active=True)
            tickets_used = LotteryParticipant.select() \
                .where(LotteryParticipant.lottery == lottery, LotteryParticipant.is_pending == False).count()
            if lottery.num_tickets > tickets_used:
                is_pending = False
                msg = _('You have been added to lottery')
            else:
                is_pending = True
                msg = _('There are no tickets left')
                msg += '\n'
                msg += _('User have been added to lottery queue')
            all_codes = LotteryParticipant.filter(is_pending=False, lottery=lottery)
            all_codes = [item.code for item in all_codes]
            shortcuts.add_client_to_lottery(lottery, order.user, all_codes, is_pending)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.client_order_finished_keyboard(_, order_id, lottery_available))
        query.answer()
        return enums.BOT_ORDER_DELIVERED
    elif action == 'delivered_order_review':
        user_data['review_order'] = {'order_id': order_id, 'answers': {}}
        msg = _('Please send a review')
        reply_markup = keyboards.client_order_review_keyboard(_, {})
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_ORDER_REVIEW


@user_passes
def on_order_review(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action.startswith('review_question'):
        q_id, rank = (int(val) for val in action.split('_')[-2:])
        answers = user_data['review_order']['answers']
        if rank != answers.get(q_id):
            answers[q_id] = rank
            msg = _('Please send a review')
            reply_markup = keyboards.client_order_review_keyboard(_, answers)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_ORDER_REVIEW
    elif action == 'review_words':
        msg = _('Please add a few words:')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.BOT_ORDER_REVIEW_FEW_WORDS
    elif action == 'review_send':
        review_data = user_data['review_order']
        order_id = review_data['order_id']
        order = Order.get(id=order_id)
        text = review_data.get('text')
        user = User.get(telegram_id=user_id)
        review = Review.create(user=user, order=order, text=text)
        answers = review_data['answers']
        for q_id, rank in answers.items():
            question = ReviewQuestion.get(id=q_id)
            ReviewQuestionRank.create(question=question, review=review, rank=rank)
        msg = _('Thank you. Review is sent!')
        bot.edit_message_text(msg, chat_id, msg_id)
        return states.enter_menu(bot, update, user_data, query_id=query.id)
    elif action == 'review_back':
        order_id = user_data['review_order']['order_id']
        order = Order.get(id=order_id)
        lottery_available = shortcuts.check_lottery_available(order)
        msg = _('Order №{} is completed.').format(order.id)
        msg += '\n'
        msg += _('We would love to hear about your experience with our products and service')
        reply_markup = keyboards.client_order_finished_keyboard(_, order_id, lottery_available)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.BOT_ORDER_DELIVERED
    else:
        query.answer()
        return enums.BOT_ORDER_REVIEW


@user_passes
def on_order_review_few_words(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    reply_markup = keyboards.client_order_review_keyboard(_, user_data['review_order']['answers'])
    if query and query.data == 'back':
        msg = _('Please send a review')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=reply_markup)
        query.answer()
    else:
        text = update.message.text
        user_data['review_order']['text'] = text
        msg = _('Review message is saved.')
        msg += '\n'
        msg += _('Please send a review')
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.BOT_ORDER_REVIEW


def delete_message(bot, update):
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    shortcuts.delete_channel_msg(bot, chat_id, msg_id)
    query.answer()


def service_channel_courier_query_handler(bot, update, user_data):
    query = update.callback_query
    data = query.data
    courier_nickname = get_username(update)
    courier_id = get_user_id(update)
    action, order_id, answers_ids = data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    _ = get_channel_trans()
    try:
        order = Order.get(id=order_id)
    except Order.DoesNotExist:
        order = None
        msg = _('Cannot find order #{}').format(order.id)
    if order.status in (Order.DELIVERED, Order.CANCELLED):
        order = None
        msg_map = {order.DELIVERED: 'delivered', order.CANCELLED: 'cancelled'}
        msg = _('Order is {} already.').format(msg_map[order.status])
    if not order:
        query.answer(text=msg, show_alert=True)
        if answers_ids:
            for answer_id in answers_ids:
                bot.delete_message(chat_id, answer_id)
        bot.delete_message()
    else:
        courier = User.get(telegram_id=courier_id)
        if courier.banned:
            msg = _('You are black-listed')
            query.answer(msg, show_alert=True)
        elif not courier.is_courier:
            msg = _('You don\'t have courier status')
            query.answer(msg, show_alert=True)
        else:
            if order.location:
                try:
                    CourierLocation.get(courier=courier, location=order.location)
                except CourierLocation.DoesNotExist:
                    query.answer(
                        text=_('{}\n your location and customer locations are different').format(courier_nickname),
                        show_alert=True)
                    return
            warehouse_error_msg = None
            for item in order.order_items:
                product = item.product
                if product.warehouse_active:
                    try:
                        warehouse_count = ProductWarehouse.get(courier=courier, product=product).count
                    except ProductWarehouse.DoesNotExist:
                        warehouse_count = 0
                    if item.count > warehouse_count:
                        courier_trans = get_trans(courier_id)
                        warehouse_error_msg = courier_trans('You don\'t have enough credits in warehouse')
                        warehouse_error_msg += '\n'
                        product_title = escape_markdown(product.title)
                        msg_ending = 'Product: `{}`\nCount: {}\nCredits: {}'.format(product_title, item.count, warehouse_count)
                        break
            if warehouse_error_msg:
                warehouse_error_msg += courier_trans(msg_ending)
                query.answer(_('Cannot take this order'), show_alert=True)
                bot.send_message(courier_id, warehouse_error_msg, parse_mode=ParseMode.MARKDOWN)
                _ = get_channel_trans()
                service_msg = _('Order №{}').format(order.id)
                service_msg += '\n'
                courier_username = escape_markdown(courier.username)
                service_msg = _('Courier `{}` doesn\'t have enough credits in warehouse').format(courier_username)
                service_msg += '\n'
                service_msg += _(msg_ending)
                bot.send_message(get_service_channel(), service_msg, parse_mode=ParseMode.MARKDOWN)
            else:
                shortcuts.change_order_products_credits(order, courier=courier)
                order.courier = courier
                order.save()
                keyboard = keyboards.courier_assigned_keyboard(courier_nickname, _)
                assigned_msg_id = shortcuts.edit_channel_msg(bot, query.message.text, chat_id, msg_id, keyboard, order)
                msg = _('Courier: @{}, apply for order №{}.\nConfirm this?').format(escape_markdown(courier_nickname), order_id)
                keyboard = keyboards.courier_confirmation_keyboard(order_id, _, answers_ids, assigned_msg_id)
                shortcuts.send_channel_msg(bot, msg, get_service_channel(), keyboard, order)
                query.answer(text=_('Courier {} assigned').format(courier_nickname), show_alert=True)


@user_passes
def on_courier_confirm(bot, update, user_data):
    query = update.callback_query
    label, order_id = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    shortcuts.delete_channel_msg(bot, get_service_channel(), msg_id)
    _ = get_channel_trans()
    try:
        order = Order.get(id=order_id)
    except Order.DoesNotExist:
        logger.info('Order № {} not found!'.format(order_id))
        msg = _('Order is not found')
        query.answer(msg, show_alert=True)
    else:
        order.status = Order.PROCESSING
        order.save()

        user_id = order.user.telegram_id
        _ = get_trans(user_id)
        courier = order.courier
        msg = _('Courier @{} assigned to your order').format(courier.username)
        bot.send_message(user_id, msg)
        courier_id = courier.telegram_id
        _ = get_trans(courier_id)
        try:
            btc_data = OrderBtcPayment.get(order=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        msg = messages.create_service_notice(_, order, btc_data, for_courier=True)
        reply_markup = keyboards.courier_order_status_keyboard(_, order_id, courier)
        bot.send_message(courier_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


@user_passes
def on_courier_unconfirm(bot, update, user_data):
    query = update.callback_query
    label, order_id, answers_ids, assigned_msg_id = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    shortcuts.delete_channel_msg(bot, chat_id, msg_id)
    couriers_channel = get_couriers_channel()
    if answers_ids:
        for answer_id in answers_ids.split(','):
            shortcuts.delete_channel_msg(bot, couriers_channel, answer_id)
    shortcuts.delete_channel_msg(bot, couriers_channel, assigned_msg_id)
    _ = get_channel_trans()
    try:
        order = Order.get(id=order_id)
    except Order.DoesNotExist:
        logger.info('Order № {} not found!'.format(order_id))
        msg = _('Order #{} does not exist').format(order_id)
        query.answer(msg)
    else:
        shortcuts.change_order_products_credits(order, True, order.courier)
        order.courier = None
        order.save()
        msg = _('The admin did not confirm. Please retake '
                'responsibility for order №{}').format(order_id)
        shortcuts.send_channel_msg(bot, msg, couriers_channel, order=order)
        msgs_ids = ''
        if len(order.identification_answers):
            answers_ids = shortcuts.send_order_identification_answers(bot, couriers_channel, order, send_one=True,
                                                                      channel=True)
            msgs_ids += ','.join(answers_ids)
        if order.coordinates:
            lat, lng = order.coordinates.split('|')[:2]
            coords_msg_id = shortcuts.send_channel_location(bot, chat_id, lat, lng)
            msgs_ids += ',' + coords_msg_id
        shipping_method = order.shipping_method
        order_location = order.location
        if order_location:
            order_location = order_location.title
        keyboard = keyboards.service_notice_keyboard(order_id, _, answers_ids, order_location, shipping_method)
        try:
            btc_data = OrderBtcPayment.get(order=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        msg = messages.create_service_notice(_, order, btc_data)
        shortcuts.send_channel_msg(bot, msg, couriers_channel, keyboard, order)


@user_passes
def on_product_categories(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
        keyboard = keyboards.general_select_one_keyboard(_, categories, page)
        msg = _('Please select a category')

        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
        query.answer()
        return enums.BOT_PRODUCT_CATEGORIES
    elif action == 'select':
        products_msgs = user_data.get('products_msgs')
        if products_msgs:
            for p_msg_id in products_msgs:
                bot.delete_message(chat_id, p_msg_id)
            del user_data['products_msgs']
        cat = ProductCategory.get(id=val)
        cat_title = escape_markdown(cat.title.replace('`', ''))
        msg = _('Category `{}` products:').format(cat_title)
        cat_msg = bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN)
        products_msgs = [cat_msg['message_id']]
        # send_products to current chat
        user = User.get(telegram_id=user_id)
        products = shortcuts.get_users_products(user, cat)
        if products.exists():
            msgs_ids = shortcuts.send_products(_, bot, user_data, chat_id, products, user)
            products_msgs += msgs_ids
        user_data['products_msgs'] = products_msgs
        user_data['category_id'] = cat.id
        return states.enter_menu(bot, update, user_data, query_id=query.id)
    elif action == 'back':
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_calendar_change(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    try:
        calendar_data = user_data['calendar']
        year, month = calendar_data['year'], calendar_data['month']
        state = calendar_data['state']
    except KeyError:
        msg = _('Failed to get calendar date, please initialize calendar again.')
        bot.send_message(msg, chat_id)
        return states.enter_menu(bot, update, user_data)
    else:
        data = query.data
        calendar_actions = [
            'calendar_next_year', 'calendar_previous_year', 'calendar_next_month',
            'calendar_previous_month', 'calendar_ignore'
        ]
        if data in calendar_actions:
            if data == 'calendar_ignore':
                query.answer()
                return state
            elif data == 'calendar_next_year':
                year += 1
            elif data == 'calendar_previous_year':
                year -= 1
            elif data == 'calendar_next_month':
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            elif data == 'calendar_previous_month':
                month -= 1
                if month < 1:
                    month = 12
                    year -= 1
            if year < 1:
                year = 1
            msg = calendar_data['msg']
            user_data['calendar']['year'] = year
            user_data['calendar']['month'] = month
            reply_markup = keyboards.calendar_keyboard(year, month, _, calendar_data['cancel'], calendar_data['first_date'])
            bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return state
        else:
            return states.enter_unknown_command(_, bot, query)


@user_passes
def on_time_picker_change(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    try:
        time_data = user_data['time_picker']
        hour, minute = time_data['hour'], time_data['minute']
        state = time_data['state']
    except KeyError:
        msg = _('Failed to get time picker time, please initialize time_picker again.')
        bot.send_message(msg, chat_id)
        return states.enter_menu(bot, update, user_data)
    else:
        action = query.data
        start_time, end_time = time_data['range']
        picked_time = datetime.datetime.today().replace(hour=hour, minute=minute)
        if action.startswith('time_picker_hour'):
            delta = datetime.timedelta(hours=1)
            if action == 'time_picker_hour_next':
                picked_time += delta
            else:
                picked_time -= delta
        elif action.startswith('time_picker_minute'):
            delta = datetime.timedelta(minutes=30)
            if action == 'time_picker_minute_next':
                picked_time += delta
            else:
                picked_time -= delta
        else:
            query.answer()
            return state
        picked_time = datetime.time(hour=picked_time.hour, minute=picked_time.minute)
        if start_time <= picked_time <= end_time:
            hour, minute = picked_time.hour, picked_time.minute
            user_data['time_picker']['hour'] = hour
            user_data['time_picker']['minute'] = minute
            msg = time_data['msg']
            reply_markup = keyboards.time_picker_keyboard(_, hour, minute, time_data['cancel'])
            bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=reply_markup,
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return state
