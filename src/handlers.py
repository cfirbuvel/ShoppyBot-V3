import random
import re

from telegram import ParseMode, ReplyKeyboardRemove
from telegram.ext import ConversationHandler
from telegram.utils.helpers import escape_markdown

from . import keyboards, enums, shortcuts, messages, states
from .decorators import user_passes
from .helpers import get_user_id, get_username, get_locale, get_trans, config, is_vip_customer, \
    is_customer, logger, Cart, get_full_product_info, get_user_update_username, get_channel_trans, clear_user_data
from .models import User, Product, ProductCategory, Order, Location, OrderBtcPayment, Currencies, BitcoinCredentials, \
    Channel, UserPermission, IdentificationStage, IdentificationQuestion, UserIdentificationAnswer,\
    ChannelPermissions


@user_passes
def on_start(bot, update, user_data):
    user_id = get_user_id(update)
    username = get_username(update)
    locale = get_locale(update)
    clear_user_data(user_data, 'menu_id')
    try:
        user = get_user_update_username(user_id, username)
    except User.DoesNotExist:
        default_permission = UserPermission.get(permission=UserPermission.NOT_REGISTERED)
        user = User.create(telegram_id=user_id, username=username, locale=locale, permission=default_permission)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if user.is_admin:
        log_msg = 'Starting session for Admin - From admin_id: %s, username: @%s, language: %s'
    else:
        log_msg = 'Starting - Session for user_id: %s, username: @%s, language: %s'
    logger.info(log_msg, user_id, username, locale)
    if not config.only_for_registered or user.is_registered:
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
    try:
        user = User.get(telegram_id=user_id)
    except User.DoesNotExist:
        locale = get_locale(update)
        default_permission = UserPermission.get(permission=UserPermission.NOT_REGISTERED)
        user = User(telegram_id=user_id, username=username, locale=locale, permission=default_permission)
        user.save()
    else:
        if username != user.username:
            user.username = username
            user.save()

    query = update.callback_query
    data = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    clear_user_data(user_data, 'menu_id')
    if not config.only_for_registered or user.is_registered:
        if data == 'menu_products':
            categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
            if categories:
                reply_markup = keyboards.general_select_one_keyboard(_, categories)
                msg = _('Please select a category:')
                bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
                query.answer()
                return enums.BOT_PRODUCT_CATEGORIES
            else:
                bot.delete_message(chat_id, msg_id)
                for product in Product.filter(is_active=True):
                    product_id = product.id
                    product_count = Cart.get_product_count(user_data, product_id)
                    subtotal = Cart.get_product_subtotal(user_data, product_id)
                    product_title, prices = get_full_product_info(product_id)
                    shortcuts.send_product_media(bot, product, chat_id)
                    msg = messages.create_product_description(_, product_title, prices, product_count, subtotal)
                    reply_markup = keyboards.create_product_keyboard(_, product_id, user_data)
                    bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN, timeout=20)
                return states.enter_menu(bot, update, user_data, query.id)
        elif data == 'menu_order':
            if username is None:
                msg = _('You cannot order without username')
                query.answer(msg, show_alert=True)
                return enums.BOT_INIT
            if Cart.not_empty(user_data):
                unfinished_orders = Order.select().where(Order.user == user, Order.delivered == False, Order.canceled == False)
                if len(unfinished_orders):
                    msg = _('You cannot make new order if previous order is not finished')
                    query.answer(msg, show_alert=True)
                    return enums.BOT_INIT
                try:
                    del user_data['order_identification']
                except KeyError:
                    pass
                msg = _('Please choose pickup or delivery')
                reply_markup = keyboards.create_shipping_keyboard(_)
                bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
                if user.is_admin:
                    log_msg = 'Starting order process for Admin - From admin_id: %s, username: @%s'
                else:
                    log_msg = 'Starting order process - From user_id: %s, username: @%s'
                logger.info(log_msg, user_id, username)
                query.answer()
                user_data['shipping'] = {}
                return enums.BOT_CHECKOUT_SHIPPING
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
            reply_markup = keyboards.bot_language_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.BOT_LANGUAGE_CHANGE
        elif data.startswith('menu_register'):
            return states.enter_registration(_, bot, chat_id, msg_id, query.id)
        elif data == 'menu_hours':
            msg = config.working_hours
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
            product_id = int(product_id)
            product_count = Cart.get_product_count(user_data, product_id)
            if action == 'product_add':
                user_data = Cart.add(user_data, product_id)
            else:
                user_data = Cart.remove(user_data, product_id)
            if product_count == Cart.get_product_count(user_data, product_id):
                query.answer()
                return enums.BOT_INIT
            subtotal = Cart.get_product_subtotal(user_data, product_id)
            product_title, prices = get_full_product_info(product_id)
            product_count = Cart.get_product_count(user_data, product_id)
            msg = messages.create_product_description(_, product_title, prices, product_count, subtotal)
            reply_markup = keyboards.create_product_keyboard(_, product_id, user_data)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            msg_id = user_data['menu_id']
            return states.enter_menu(bot, update, user_data, msg_id)
        elif data == 'menu_settings':
            msg = _('⚙️ Settings')
            reply_markup = keyboards.admin_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.ADMIN_MENU
        elif data == 'menu_my_orders':
            msg = _('📖 My Orders')
            reply_markup = keyboards.create_my_orders_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.BOT_MY_ORDERS
        else:
            logger.warn('Unknown query: %s', query.data)
    else:
        return states.enter_registration(_, bot, chat_id, msg_id)


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
            msg = _('Please send your phone number.')
            bot.send_message(chat_id, msg, reply_markup=keyboards.create_phone_number_request_keyboard(_))
            query.answer()
            return enums.BOT_PHONE_NUMBER
    else:
        if config.only_for_registered:
            bot.delete_message(chat_id, msg_id)
        else:
            return states.enter_menu(bot, update, user_data, msg_id)
    return states.enter_unknown_command(_, bot, query)


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
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.back_cancel_keyboard(_))
            return enums.BOT_IDENTIFICATION
        else:
            msg = _('Please send your phone number.')
            bot.send_message(chat_id, msg, reply_markup=keyboards.create_phone_number_request_keyboard(_))
            query.answer()
            return enums.BOT_PHONE_NUMBER
    elif action == 'no':
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
                bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.back_cancel_keyboard(_))
                return enums.BOT_IDENTIFICATION
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
    if current_stage.type in ('photo', 'video'):
        try:
            if current_stage.type == 'photo':
                answer = update.message.photo
                answer = answer[-1].file_id
            else:
                answer = update.message.video
                answer = answer.file_id
        except (IndexError, AttributeError):
            text = _(current_stage.type)
            msg = _('_Please upload a {} as an answer_').format(text)
            bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
            return enums.BOT_IDENTIFICATION
    else:
        answer = update.message.text
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
        bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
        return enums.BOT_IDENTIFICATION
    else:
        msg = _('Please send your phone number.')
        bot.send_message(chat_id, msg, reply_markup=keyboards.create_phone_number_request_keyboard(_))
        return enums.BOT_PHONE_NUMBER


@user_passes
def on_registration_phone_number(bot, update, user_data):
    answer = update.message.text
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    reg_data = user_data.get('user_registration')
    if answer == _('↩ Back'):
        if reg_data:
            id_data = reg_data['identification']
            prev_stage, prev_q = id_data['passed_ids'].pop()
            id_data['current_id'] = prev_stage
            id_data['current_q_id'] = prev_q
            question = IdentificationQuestion.get(id=prev_q)
            msg = question.content
            bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
            return enums.BOT_IDENTIFICATION
        else:
            if reg_data:
                del user_data['user_registration']
            return states.enter_registration(_, bot, chat_id)
    elif answer == _('❌ Cancel'):
        if reg_data:
            del user_data['user_registration']
        if config.only_for_registered:
            return states.enter_registration(_, bot, chat_id)
        else:
            return states.enter_menu(bot, update, user_data)
    elif answer == _('✒️Enter phone manually'):
        return enums.BOT_PHONE_NUMBER
    else:
        try:
            phone_number_text = update.message.contact.phone_number
        except AttributeError:
            phone_number_text = update.message.text
            phone_number_text = phone_number_text.replace(' ', '')
            match = re.search(r'(\+?\d{10})', phone_number_text)
            if not match:
                error_msg = _('✒️ Please enter correct phone number')
                bot.send_message(chat_id, error_msg)
                return enums.BOT_PHONE_NUMBER
        user = User.get(telegram_id=user_id)
        user.phone_number = phone_number_text
        user.permission = UserPermission.PENDING_REGISTRATION
        user.save()
        if reg_data:
            id_data = reg_data['identification']
            for stage_id, q_id, answer in id_data['answers']:
                stage = IdentificationStage.get(id=stage_id)
                question = IdentificationQuestion.get(id=q_id)
                UserIdentificationAnswer.create(stage=stage, question=question, user=user, content=answer)
            del user_data['user_registration']
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
    return states.enter_unknown_command(_, bot, query)


def on_error(bot, update, error):
    logger.error('Error: %s', error)


def checkout_fallback_command_handler(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    msg = _('Cannot process commands when checking out')
    query.answer(msg, show_alert=True)

#
# def on_shipping_method(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action = query.data
#     if action == 'cancel':
#         return states.enter_state_init_order_cancelled(bot, update, user_data)
#     elif action in ('pickup', 'delivery'):
#         user_data['shipping']['method'] = action
#         if not Location.select().exists():
#             return states.enter_state_location_delivery(bot, update, user_data)
#         else:
#             return enter_state_courier_location(bot, update, user_data)
#     else:
#         return enter_state_shipping_method(bot, update, user_data)


@user_passes
def on_my_orders(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    data = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if data == 'back':
        return states.enter_menu(bot, update, user_data, msg_id)
    elif data == 'by_date':
        state = enums.BOT_MY_ORDERS_DATE
        shortcuts.initialize_calendar(bot, user_data, chat_id, msg_id, state, _, query.id)
        return state
    elif data == 'last_order':
        user = User.get(telegram_id=user_id)
        order = Order.select().where(Order.user == user).order_by(Order.date_created.desc()).get()
        order_id = order.id
        msg = _('Order №{}').format(order.id)
        reply_markup = keyboards.create_my_order_keyboard(_, order_id, not order.delivered and not order.canceled)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.BOT_MY_LAST_ORDER


def on_my_order_date(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'ignore':
        query.answer()
        return enums.BOT_MY_ORDERS_DATE
    elif action == 'back':
        msg = _('📖 My Orders')
        reply_markup = keyboards.create_my_orders_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.BOT_MY_ORDERS
    elif action in ('day', 'month', 'year'):
        year, month = user_data['calendar_date']
        queries = shortcuts.get_order_subquery(action, val, month, year)
        user = User.get(telegram_id=user_id)
        queries.append(Order.user == user)
        orders = Order.select().where(*queries)
        if len(orders) == 1:
            order = orders[0]
            msg = _('Order №{}').format(order.id)
            reply_markup = keyboards.create_my_order_keyboard(_, order.id, not order.delivered and not order.canceled)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.BOT_MY_LAST_ORDER
        else:
            orders_data = [(order.id, order.date_created.strftime('%d/%m/%Y')) for order in orders]
            orders = [(_('Order №{} {}').format(order_id, order_date), order_id) for order_id, order_date in orders_data]
            user_data['my_orders_by_date'] = orders_data
            msg = _('Select order')
            reply_markup = keyboards.general_select_one_keyboard(_, orders)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.BOT_MY_ORDERS_SELECT


def on_my_order_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        state = enums.BOT_MY_ORDERS_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, msg_id, state, query.id)
        return state
    elif action == 'page':
        current_page = int(val)
        orders = [(_('Order №{} {}').format(order_id, order_date), order_id) for order_id, order_date in user_data['my_orders_by_date']]
        reply_markup = keyboards.general_select_one_keyboard(_, orders, current_page)
        msg = _('Select order:')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.BOT_MY_ORDERS_SELECT
    else:
        order = Order.get(id=val)
        msg = _('Order №{}').format(order.id)
        reply_markup = keyboards.create_my_order_keyboard(_, order.id, not order.delivered and not order.canceled)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.BOT_MY_LAST_ORDER


def on_my_last_order(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        msg = _('📖 My Orders')
        reply_markup = keyboards.create_my_orders_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.BOT_MY_ORDERS
    order_id = int(val)
    order = Order.get(id=order_id)
    if action == 'cancel':
        if not order.delivered and not order.cancelled:
            msg = _('Are you sure?')
            mapping = {'yes': 'yes|{}'.format(order_id), 'no': 'no|{}'.format(order_id)}
            reply_markup = keyboards.are_you_sure_keyboard(_, mapping)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.BOT_MY_LAST_ORDER_CANCEL
        elif order.delivered:
            query.answer(text=_('Cannot cancel - order was delivered.'), show_alert=True)
        else:
            query.answer(text=_('Cannot cancel - order was cancelled already.'))
        return enums.BOT_MY_LAST_ORDER
    elif action == 'show':
        try:
            btc_data = OrderBtcPayment.get(order=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        user_vip = is_vip_customer(bot, user_id)
        msg = messages.create_service_notice(_, order, user_vip, btc_data)
        reply_markup = keyboards.create_my_order_keyboard(_, order_id, not order.delivered)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.BOT_MY_LAST_ORDER


def on_my_last_order_cancel(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    username = get_username(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    order = Order.get(id=val)
    if action == 'yes':
        order.cancelled = True
        order.save()
        service_chat = config.service_channel
        channel_trans = get_channel_trans()
        msg = channel_trans('Order was cancelled by client @{}.').format(order.id, username)
        shortcuts.bot_send_order_msg(channel_trans, bot, service_chat, msg, order.id, channel=True, parse_mode=None)
        logger.info('Order № %s was cancelled by user: @%s', order.id, username)
        # username = escape_markdown(username)
        msg = _('Order №{} was cancelled.').format(order.id)
    elif action == 'no':
        msg = _('Order №{}').format(order.id)
    reply_markup = keyboards.create_my_order_keyboard(_, order.id, not order.delivered)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.BOT_MY_LAST_ORDER


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

#
# def on_shipping_pickup_location(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     locations = Location.select()
#     location_names = [x.title for x in locations]
#     _ = get_trans(user_id)
#     if key == _('↩ Back'):
#         return enter_state_shipping_method(bot, update, user_data)
#     elif key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif any(key in s for s in location_names):
#         user_data['shipping']['pickup_location'] = key
#         session_client.json_set(user_id, user_data)
#
#         if user_data['shipping']['method'] == _('🚚 Delivery'):
#             return enter_state_location_delivery(bot, update, user_data)
#         else:
#             return enter_state_shipping_time(bot, update, user_data)
#     else:
#         return enter_state_courier_location(bot, update, user_data)
#
#
# def on_shipping_delivery_address(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('↩ Back'):
#         return enter_state_shipping_method(bot, update, user_data)
#     elif key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('✒️Enter location manually'):
#         return enums.BOT_CHECKOUT_LOCATION_DELIVERY
#     else:
#         try:
#             location = update.message.location
#             loc = {'latitude': location['latitude'], 'longitude': location['longitude']}
#             location = loc
#             user_data['shipping']['geo_location'] = location
#         except TypeError:
#             location = update.message.text
#             user_data['shipping']['location'] = location
#         session_client.json_set(user_id, user_data)
#         return enter_state_shipping_time(bot, update, user_data)
#
#
# def on_checkout_time(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('↩ Back'):
#         return enter_state_shipping_method(bot, update, user_data)
#     elif key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('⏰ Now'):
#         user_data['shipping']['time'] = key
#         session_client.json_set(user_id, user_data)
#
#         if config.get_phone_number_required():
#             return enter_state_phone_number_text(bot, update, user_data)
#         else:
#             identification_stages = IdentificationStage.filter(active=True)
#             if is_vip_customer(bot, user_id):
#                 identification_stages = identification_stages.filter(vip_required=True)
#             if len(identification_stages):
#                 first_stage = identification_stages[0]
#                 questions = first_stage.identification_questions
#                 question = random.choice(list(questions))
#                 user_data['order_identification'] = {'passed_ids': [], 'current_id': first_stage.id, 'current_q_id': question.id, 'answers': []}
#                 session_client.json_set(user_id, user_data)
#                 msg = escape_markdown(question.content)
#                 bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                                  parse_mode=ParseMode.MARKDOWN)
#                 return enums.BOT_CHECKOUT_IDENTIFY
#             btc_enabled = BitcoinCredentials.select().first().enabled
#             if btc_enabled:
#                 return enter_state_select_payment_type(bot, update, user_data)
#             else:
#                 return enter_state_order_confirm(bot, update, user_data)
#     elif key == _('📅 Set time'):
#         user_data['shipping']['time'] = key
#         session_client.json_set(user_id, user_data)
#
#         return enter_state_shipping_time_text(bot, update, user_data)
#     else:
#         enums.logger.warn("Unknown input %s", key)
#         return enter_state_shipping_time(bot, update, user_data)
#
#
# def on_shipping_time_text(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('↩ Back'):
#         return enter_state_shipping_time(bot, update, user_data)
#     elif key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     else:
#         user_data['shipping']['time_text'] = key
#         session_client.json_set(user_id, user_data)
#         return enter_state_phone_number_text(bot, update, user_data)
#
#
# def on_phone_number_text(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('↩ Back'):
#         return enter_state_shipping_time(bot, update, user_data)
#     elif key == _('✒️Enter phone manually'):
#         return enums.BOT_CHECKOUT_PHONE_NUMBER
#     else:
#         try:
#             phone_number_text = update.message.contact.phone_number
#         except AttributeError:
#             phone_number_text = update.message.text
#             match = re.search(r'(\+?\d{1,3})?\d{7,13}', phone_number_text)
#             if not match:
#                 error_msg = _('✒️ Please enter correct phone number')
#                 bot.send_message(update.message.chat_id, error_msg)
#                 return enums.BOT_CHECKOUT_PHONE_NUMBER
#
#         user_data['shipping']['phone_number'] = phone_number_text
#         session_client.json_set(user_id, user_data)
#         user = User.get(telegram_id=user_id)
#         user.phone_number = phone_number_text
#         user.save()
#         identification_stages = IdentificationStage.filter(active=True)
#         if is_vip_customer(bot, user_id):
#             identification_stages = identification_stages.filter(vip_required=True)
#         else:
#             identification_stages = identification_stages.filter(vip_required=False)
#         if len(identification_stages):
#             first_stage = identification_stages[0]
#             questions = first_stage.identification_questions
#             question = random.choice(list(questions))
#             user_data['order_identification'] = {'passed_ids': [], 'current_id': first_stage.id, 'current_q_id': question.id,'answers': []}
#             session_client.json_set(user_id, user_data)
#             msg = escape_markdown(question.content)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#         btc_enabled = BitcoinCredentials.select().first().enabled
#         if btc_enabled:
#             return enter_state_select_payment_type(bot, update, user_data)
#         else:
#             return enter_state_order_confirm(bot, update, user_data)
#
#
# def on_identify_general(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     data = user_data['order_identification']
#     if key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('↩ Back'):
#         passed_ids = data['passed_ids']
#         if passed_ids:
#             prev_stage, prev_q = passed_ids.pop()
#             data['current_id'] = prev_stage
#             data['current_q_id'] = prev_q
#             session_client.json_set(user_id, user_data)
#             question = IdentificationQuestion.get(id=prev_q)
#             msg = escape_markdown(question.content)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#         elif config.get_phone_number_required():
#             return enter_state_phone_number_text(bot, update, user_data)
#         else:
#             return enter_state_shipping_time(bot, update, user_data)
#     current_id = data['current_id']
#     current_stage = IdentificationStage.get(id=current_id)
#     if current_stage.type in ('photo', 'video'):
#         try:
#             if current_stage.type == 'photo':
#                 answer = update.message.photo
#                 answer = answer[-1].file_id
#             else:
#                 answer = update.message.video
#                 answer = answer.file_id
#         except (IndexError, AttributeError):
#             text = _(current_stage.type)
#             msg = _('_Please upload a {} as an answer_').format(text)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#     else:
#         answer = key
#     current_q_id = data['current_q_id']
#     data['answers'].append((current_id, current_q_id, answer))
#     passed_ids = data['passed_ids']
#     passed_ids.append((current_id, current_q_id))
#     passed_stages_ids = [v[0] for v in passed_ids]
#     stages_left = IdentificationStage.select().where(IdentificationStage.active == True & IdentificationStage.id.not_in(passed_stages_ids))
#     if is_vip_customer(bot, user_id):
#         stages_left = stages_left.filter(vip_required=True)
#         user_data['shipping']['vip'] = True
#     session_client.json_set(user_id, user_data)
#     if stages_left:
#         next_stage = stages_left[0]
#         questions = next_stage.identification_questions
#         question = random.choice(list(questions))
#         data['current_id'] = next_stage.id
#         data['current_q_id'] = question.id
#         session_client.json_set(user_id, user_data)
#         msg = escape_markdown(question.content)
#         bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                          parse_mode=ParseMode.MARKDOWN)
#         return enums.BOT_CHECKOUT_IDENTIFY
#     btc_enabled = BitcoinCredentials.select().first().enabled
#     if btc_enabled:
#         return enter_state_select_payment_type(bot, update, user_data)
#     else:
#         return enter_state_order_confirm(bot, update, user_data)

#
# def on_order_payment_type(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('↩ Back'):
#         identification_stages = IdentificationStage.filter(active=True)
#         if len(identification_stages):
#             last_stage_id = user_data['order_identification']['current_id']
#             last_q_id = user_data['order_identification']['current_q_id']
#             last_question = IdentificationQuestion.get(id=last_q_id)
#             msg = escape_markdown(last_question.content)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#         elif config.get_phone_number_required():
#             return enter_state_phone_number_text(bot, update, user_data)
#         else:
#             return enter_state_shipping_time(bot, update, user_data)
#     elif key in (_('💸 Pay with Bitcoin'), _('🚚 Pay on delivery')):
#         if key == _('💸 Pay with Bitcoin'):
#             btc_payment = True
#         else:
#             btc_payment = False
#         user_data['shipping']['btc_payment'] = btc_payment
#         session_client.json_set(user_data, user_id)
#         return enter_state_order_confirm(bot, update, user_data)
#     else:
#         enums.logger.warn("Unknown input %s", key)
#         return enter_state_select_payment_type(bot, update, user_data)
#
#
# def btc_conversion_failed(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('↩ Back'):
#         identification_stages = IdentificationStage.filter(active=True)
#         if len(identification_stages):
#             last_stage_id = user_data['order_identification']['current_id']
#             last_q_id = user_data['order_identification']['current_q_id']
#             last_question = IdentificationQuestion.get(id=last_q_id)
#             msg = escape_markdown(last_question.content)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#         elif config.get_phone_number_required():
#             return enter_state_phone_number_text(bot, update, user_data)
#         else:
#             return enter_state_shipping_time(bot, update, user_data)
#     elif key == '🔄 Try again':
#         return enter_state_order_confirm(bot, update, user_data)
#     else:
#         enums.logger.warn("Unknown input %s", key)
#         return enter_state_btc_conversion_failed(bot, update, user_data)
#
#
# def generating_address_failed(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('↩ Back'):
#         btc_enabled = BitcoinCredentials.select().first().enabled
#         if btc_enabled:
#             return enter_state_select_payment_type(bot, update, user_data)
#         identification_stages = IdentificationStage.filter(active=True)
#         if len(identification_stages):
#             last_stage_id = user_data['order_identification']['current_id']
#             last_q_id = user_data['order_identification']['current_q_id']
#             last_question = IdentificationQuestion.get(id=last_q_id)
#             msg = escape_markdown(last_question.content)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#         elif config.get_phone_number_required():
#             return enter_state_phone_number_text(bot, update, user_data)
#         else:
#             return enter_state_shipping_time(bot, update, user_data)
#     elif key == '🔄 Try again':
#         return enter_state_order_confirm(bot, update, user_data)
#     else:
#         enums.logger.warn("Unknown input %s", key)
#         return enter_state_generating_address_failed(bot, update, user_data)
#
#
# def btc_too_low(bot, update, user_data):
#     key = update.message.text
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     if key == _('❌ Cancel'):
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('↩ Back'):
#         btc_enabled = BitcoinCredentials.select().first().enabled
#         if btc_enabled:
#             return enter_state_select_payment_type(bot, update, user_data)
#         identification_stages = IdentificationStage.filter(active=True)
#         if len(identification_stages):
#             last_stage_id = user_data['order_identification']['current_id']
#             last_q_id = user_data['order_identification']['current_q_id']
#             last_question = IdentificationQuestion.get(id=last_q_id)
#             msg = escape_markdown(last_question.content)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#         elif config.get_phone_number_required():
#             return enter_state_phone_number_text(bot, update, user_data)
#         else:
#             return enter_state_shipping_time(bot, update, user_data)
#     else:
#         enums.logger.warn("Unknown input %s", key)
#         return enter_state_btc_too_low(bot, update, user_data)

#
# def on_confirm_order(bot, update, user_data):
#     key = update.message.text
#     # order data
#     user_id = get_user_id(update)
#     username = get_username(update)
#     user_data = get_user_session(user_id)
#     locale = get_locale(update)
#     _ = get_trans(user_id)
#     if key == _('✅ Confirm'):
#         shipping_data = user_data['shipping']
#         try:
#             user = User.get(telegram_id=user_id)
#             if username != user.username:
#                 user.username = username
#                 user.save()
#         except User.DoesNotExist:
#             if not username:
#                 user = User.create(telegram_id=user_id, locale=locale)
#             else:
#                 user = User.create(telegram_id=user_id, locale=locale, username=username)
#         pickup_location = shipping_data.get('pickup_location')
#         if pickup_location:
#             location = Location.get(
#                 title=pickup_location)
#         else:
#             location = None
#         if shipping_data['method'] == _('🚚 Delivery'):
#             shipping_method = DeliveryMethod.DELIVERY.value
#         else:
#             shipping_method = Order.shipping_method.default
#         shipping_time = shipping_data['time']
#         order_address = shipping_data.get('location', '')
#         is_pickup = shipping_data['method'] == _('🏪 Pickup')
#         time_text = shipping_data.get('time_text', '')
#         phone_number = shipping_data.get('phone_number', '')
#         order = Order.create(user=user, location=location, shipping_method=shipping_method, shipping_time=shipping_time,
#                              address=order_address, is_pickup=is_pickup, time_text=time_text, phone_number=phone_number)
#         btc_payment = shipping_data['btc_payment']
#         if btc_payment:
#             btc_value = shipping_data['btc_value']
#             btc_value = Decimal(btc_value)
#             wallet = BtcWallet(_, BtcSettings.WALLET, BtcSettings.PASSWORD, BtcSettings.SECOND_PASSWORD)
#             try:
#                 btc_address, xpub = wallet.create_hd_account_address('Order #{}'.format(order.id))
#             except BtcError:
#                 order.delete_instance()
#                 return enter_state_generating_address_failed(bot, update, user_data)
#             order.btc_payment = True
#             order.save()
#             btc_data = OrderBtcPayment.create(order=order, amount=btc_value, xpub=xpub, address=btc_address)
#             # order.btc_enabled = True
#             # order.btc_amount = btc_value
#             # order.btc_xpub = xpub
#             # order.btc_address = btc_address
#             # order.save()
#         else:
#             btc_data = None
#         _ = get_channel_trans()
#         order_id = order.id
#         enums.logger.info('New order confirmed  - Order №%s, From user_id %s, username: @%s',
#                           order_id,
#                           update.effective_user.id,
#                           update.effective_user.username)
#         is_vip = is_vip_customer(bot, user_id)
#         order_identification = user_data.get('order_identification')
#         if order_identification:
#             for stage_id, q_id, answer in order_identification['answers']:
#                 stage = IdentificationStage.get(id=stage_id)
#                 question = IdentificationQuestion.get(id=q_id)
#                 OrderIdentificationAnswer.create(stage=stage, question=question, order=order, content=answer)
#
#         # ORDER CONFIRMED, send the details to service channel
#         user_name = escape_markdown(order.user.username)
#         if location:
#             location = escape_markdown(location.title)
#         else:
#             location = '-'
#
#         txt = _('Order №{}, Location {}\nUser @{}').format(order_id, location, user_name)
#         service_channel = config.get_service_channel()
#
#         shipping_geo_location = shipping_data.get('geo_location')
#         coordinates = None
#         if shipping_geo_location:
#             coordinates = '|'.join(map(str, shipping_geo_location.values())) + '|'
#
#         cart.fill_order(user_data, order)
#         text = create_service_notice(_, order, is_vip, btc_data)
#         order_data = OrderPhotos(order=order, coordinates=coordinates, order_text=text)
#         shortcuts.bot_send_order_msg(bot, service_channel, txt, _, order_id, order_data, channel=True)
#         if btc_payment:
#             set_btc_proc(order.id)
#             process_btc_payment(bot, order)
#         user_data['cart'] = {}
#         user_data['shipping'] = {}
#         session_client.json_set(user_id, user_data)
#         return enter_state_init_order_confirmed(bot, update, user_data, order)
#
#     elif key == _('❌ Cancel'):
#         # ORDER CANCELLED, send nothing
#         cancel_process(bot, update)
#         return enter_state_init_order_cancelled(bot, update, user_data)
#     elif key == _('↩ Back'):
#         btc_enabled = BitcoinCredentials.select().first().enabled
#         if btc_enabled:
#             return enter_state_select_payment_type(bot, update, user_data)
#         identification_stages = IdentificationStage.filter(active=True)
#         if len(identification_stages):
#             last_q_id = user_data['order_identification']['current_q_id']
#             last_question = IdentificationQuestion.get(id=last_q_id)
#             msg = escape_markdown(last_question.content)
#             bot.send_message(update.message.chat_id, msg, reply_markup=create_cancel_keyboard(_),
#                              parse_mode=ParseMode.MARKDOWN)
#             return enums.BOT_CHECKOUT_IDENTIFY
#         elif config.get_phone_number_required():
#             return enter_state_phone_number_text(bot, update, user_data)
#         else:
#             return enter_state_shipping_time(bot, update, user_data)
#     else:
#         enums.logger.warn("Unknown input %s", key)

#
# def service_channel_sendto_courier_handler(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     label, telegram_id, order_id, message_id = data.split('|')
#     order = Order.get(id=order_id)
#     user_id = get_user_id(update)
#     _ = get_channel_trans()
#     courier = Courier.get(telegram_id=telegram_id)
#     msg = shortcuts.check_order_products_credits(order, _, courier)
#     if msg and msg != True:
#         bot.send_message(user_id, msg, parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return
#     order.confirmed = True
#     order.courier = Courier.get(telegram_id=telegram_id)
#     shortcuts.change_order_products_credits(order, courier=order.courier)
#     order.save()
#     user_data = get_user_session(telegram_id)
#     user_data['courier']['order_id'] = order_id
#     session_client.json_set(telegram_id, user_data)
#     order_data = OrderPhotos.get(order=order)
#     shortcuts.delete_channel_msg(bot, update.callback_query.message.chat_id, update.callback_query.message.message_id)
#     _ = get_trans(telegram_id)
#     bot.send_message(chat_id=telegram_id,
#                      text=order_data.order_text,
#                      reply_markup=create_courier_order_status_keyboard(_, order_id),
#                      parse_mode=ParseMode.MARKDOWN)
#     query.answer(text=_('Message sent'), show_alert=True)
#
#
# def on_service_send_order_to_courier(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     label, order_id = data.split('|')
#     chat_id, msg_id = query.message.chat_id, query.message.message_id
#     order = Order.get(id=order_id)
#     if label == 'order_btc_refresh':
#         _ = get_channel_trans()
#         user_id = order.user.telegram_id
#         is_vip = is_vip_customer(bot, user_id)
#         btc_data = OrderBtcPayment.get(order=order)
#         service_msg = create_service_notice(_, order, is_vip, btc_data)
#         order_data = OrderPhotos.get(order=order)
#         if not order_data.order_text == service_msg:
#             keyboard = create_service_channel_keyboard(_, order)
#             msg_id = shortcuts.edit_channel_msg(bot, service_msg, chat_id, msg_id, keyboard, order)
#             order_data.order_text = service_msg
#             order_data.order_text_msg_id = msg_id
#             order_data.save()
#         query.answer()
#     elif label == 'order_btc_notification':
#         user_id = order.user.telegram_id
#         _ = get_trans(user_id)
#         btc_data = OrderBtcPayment.get(order=order)
#         if btc_data.payment_stage == BtcStage.SECOND:
#             msg = _('Client made payment already')
#             query.answer(msg, show_alert=True)
#         else:
#             user_notice = create_user_btc_notice(_, order)
#             bot.send_message(user_id, user_notice, parse_mode=ParseMode.MARKDOWN)
#             query.answer(_('Client was notified'))
#         _ = get_channel_trans()
#         is_vip = is_vip_customer(bot, user_id)
#         service_msg = create_service_notice(_, order, is_vip, btc_data)
#         order_data = OrderPhotos.get(order=order)
#         if not order_data.order_text == service_msg:
#             keyboard = create_service_channel_keyboard(_, order)
#             msg_id = shortcuts.edit_channel_msg(bot, service_msg, chat_id, msg_id, keyboard, order)
#             order_data.order_text = service_msg
#             order_data.order_text_msg_id = msg_id
#             order_data.save()
#     elif label == 'order_show':
#         order_data = OrderPhotos.get(order=order)
#         _ = get_channel_trans()
#         shortcuts.send_order_identification_answers(bot, chat_id, order, channel=True)
#         try:
#             shortcuts.delete_channel_msg(bot, chat_id, msg_id)
#         except Exception as e:
#             enums.logger.exception("Failed to delete message\nException: " + str(e))
#         if order_data.coordinates:
#             lat, long, msg_id = order_data.coordinates.split('|')
#             coords_msg_id = shortcuts.send_channel_location(bot, chat_id, lat, long)
#             order_data.coordinates = lat + '|' + long + '|' + coords_msg_id
#         keyboard = create_service_channel_keyboard(_, order)
#         msg_id = shortcuts.send_channel_msg(bot, order_data.order_text, chat_id, keyboard, order)
#         order_data.order_text_msg_id = msg_id
#         order_data.save()
#     elif label == 'order_hide':
#         _ = get_channel_trans()
#         order_data = OrderPhotos.get(order=order)
#         if order_data.order.canceled is True:
#             client_username = escape_markdown(order_data.order.user.username)
#             txt = _('Order №{} was cancelled by the client @{}').format(order_data.order_id, client_username)
#         else:
#             txt = order_data.order_hidden_text
#         shortcuts.delete_channel_msg(bot, chat_id, msg_id)
#         if order_data.coordinates:
#             coord1, coord2, msg_id = order_data.coordinates.split('|')
#             shortcuts.delete_channel_msg(bot, chat_id, msg_id)
#         for answer in order_data.order.identification_answers:
#             answer_msg_id = answer.msg_id
#             if answer_msg_id:
#                 shortcuts.delete_channel_msg(bot, chat_id, msg_id)
#
#         shortcuts.bot_send_order_msg(bot, update.callback_query.message.chat_id, txt, _, order_id, order_data.order, channel=True)
#
#     elif label == 'order_send_to_specific_courier':
#         _ = get_channel_trans()
#         if order.delivered:
#             msg = _('Order is delivered. Cannot send it to couriers again.')
#             query.answer(text=msg, show_alert=True)
#             return
#         couriers = Courier.select(Courier.username, Courier.telegram_id, Courier.location).where(Courier.is_active == True)
#         msg = _('Please choose who to send')
#         keyboard = couriers_choose_keyboard(_, couriers, order_id, update.callback_query.message.message_id)
#         shortcuts.send_channel_msg(bot, msg, config.get_service_channel(), keyboard, order)
#         query.answer()
#     elif label == 'order_send_to_couriers':
#         _ = get_channel_trans()
#         if config.get_has_courier_option():
#             _ = get_channel_trans()
#             if order.delivered:
#                 msg = _('Order is delivered. Cannot send it to couriers again.')
#                 query.answer(text=msg, show_alert=True)
#             else:
#                 couriers_channel = config.get_couriers_channel()
#                 order_data = OrderPhotos.get(order=order)
#                 answers_ids = shortcuts.send_order_identification_answers(bot, couriers_channel, order, send_one=True, channel=True)
#                 if len(answers_ids) > 1:
#                     answers_ids = ','.join(answers_ids)
#                 order_pickup_state = order.shipping_method
#                 order_location = order.location
#                 if order_location:
#                     order_location = order_location.title
#                 keyboard = create_service_notice_keyboard(order_id, _, answers_ids, order_location, order_pickup_state)
#                 shortcuts.send_channel_msg(bot, order_data.order_text, couriers_channel, keyboard, order)
#                 query.answer(text=_('Order sent to couriers channel'), show_alert=True)
#
#         query.answer(text=_('You have disabled courier\'s option'), show_alert=True)
#     elif label == 'order_finished':
#         if not order.delivered:
#             _ = get_channel_trans()
#             not_delivered_msg = _('Order cannot be finished because it was not delivered yet')
#             query.answer(text=not_delivered_msg, show_alert=True)
#         else:
#             shortcuts.delete_order_channels_msgs(bot, order)
#     elif label == 'order_cancel':
#         _ = get_channel_trans()
#         if order.canceled:
#             msg = _('Order is cancelled already')
#             query.answer(text=msg, show_alert=True)
#         else:
#             msg = _('Are you sure?')
#             keyboard = create_cancel_order_confirm(_, order_id)
#             shortcuts.send_channel_msg(bot, msg, update.callback_query.message.chat_id, keyboard, order)
#             query.answer()
#     elif label == 'order_send_to_self':
#         _ = get_channel_trans()
#         if order.delivered:
#             msg = _('Order is delivered. Cannot send it to couriers again.')
#             query.answer(text=msg, show_alert=True)
#             return
#         usr_id = get_user_id(update)
#         _ = get_trans(usr_id)
#         order_data = OrderPhotos.get(order=order)
#         order.courier = User.get(telegram_id=usr_id)
#         order.confirmed = True
#         order.save()
#         bot.send_message(chat_id=usr_id,
#                          text=order_data.order_text,
#                          reply_markup=create_admin_order_status_keyboard(_, order_id),
#                          parse_mode=ParseMode.MARKDOWN)
#         query.answer(text=_('Message sent'), show_alert=True)
#     elif label == 'order_ban_client':
#         usr = order.usr
#         username = usr.username
#         banned = config.get_banned_users()
#         if username not in banned:
#             banned.append(username)
#         config_session = get_config_session()
#         config_session['banned'] = banned
#         set_config_session(config_session)
#         usr_id = get_user_id(update)
#         _ = get_trans(usr_id)
#         username = escape_markdown(username)
#         msg = _('@{} was banned').format(username)
#         shortcuts.send_channel_msg(bot, msg, query.message.chat_id, order=order)
#     elif label == 'order_add_to_vip':
#         user_id = order.user.telegram_id
#         _ = get_trans(user_id)
#         bul = is_vip_customer(bot, user_id)
#         if bul:
#             query.answer(text=_('Client is already VIP'), show_alert=True)
#         else:
#             query.answer(text=_('You should no manually add this user to VIP, '
#                                 'while we working on API to do it via bot'), show_alert=True)
#     else:
#         enums.logger.info('that part is not handled yet')

#
# def cancel_order_confirm(bot, update):
#     query = update.callback_query
#     chat_id, msg_id = query.message.chat_id, query.message.message_id
#     _ = get_channel_trans()
#     action, order_id = query.data.split('|')
#     if action == 'cancel_order_no':
#         shortcuts.delete_channel_msg(bot, chat_id, msg_id)
#     if action in ('cancel_order_yes', 'cancel_order_delete'):
#         order = Order.get(Order.id == order_id)
#         order.canceled = True
#         order.confirmed = True
#         order.delivered = True
#         order.save()
#         shortcuts.delete_channel_msg(bot, chat_id, msg_id)
#     if action == 'cancel_order_delete':
#         shortcuts.delete_order_channels_msgs(bot, order)


def delete_message(bot, update):
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    shortcuts.delete_channel_msg(bot, chat_id, msg_id)
    query.answer()
#
#
# def on_cancel(bot, update, user_data):
#     return enter_state_init_order_cancelled(bot, update, user_data)

#
# def service_channel_courier_query_handler(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     courier_nickname = get_username(update)
#     courier_id = get_user_id(update)
#     label, order_id, answers_ids = data.split('|')
#     _ = get_channel_trans()
#     try:
#         if order_id:
#             order = Order.get(id=order_id)
#         else:
#             raise Order.DoesNotExist()
#     except Order.DoesNotExist:
#         enums.logger.info('Order №{} not found!'.format(order_id))
#     else:
#         try:
#             courier = Courier.get(telegram_id=courier_id)
#         except Courier.DoesNotExist:
#             query.answer(
#                 text=_('Courier: {}\nID: {}\nCourier not found, please contact admin').format(courier_nickname, courier_id),
#                 show_alert=True)
#         else:
#             if order.location:
#                 try:
#                     CourierLocation.get(courier=courier, location=order.location)
#                 except CourierLocation.DoesNotExist:
#                     query.answer(
#                         text=_('{}\n your location and customer locations are different').format(courier_nickname),
#                         show_alert=True)
#                     return
#             courier_trans = get_trans(courier_id)
#             msg = shortcuts.check_order_products_credits(order, courier_trans, courier)
#             if msg is str:
#                 bot.send_message(courier_id, msg, parse_mode=ParseMode.MARKDOWN)
#                 query.answer(text=_('Can\'t take responsibility for order'), show_alert=True)
#                 return
#             order.courier = courier
#             order.save()
#             if not msg:
#                 shortcuts.change_order_products_credits(order, courier=courier)
#             couriers_channel = config.get_couriers_channel()
#             shortcuts.delete_channel_msg(bot, couriers_channel, query.message.message_id)
#             keyboard = create_courier_assigned_keyboard(courier_nickname, order_id, _)
#             assigned_msg_id = shortcuts.send_channel_msg(bot, query.message.text, couriers_channel, keyboard, order)
#             msg = _('Courier: @{}, apply for order №{}.\nConfirm this?').format(escape_markdown(courier_nickname), order_id)
#             keyboard = create_courier_confirmation_keyboard(order_id, courier_nickname, _, answers_ids, assigned_msg_id)
#             shortcuts.send_channel_msg(bot, msg, config.get_service_channel(), keyboard, order)
#             bot.answer_callback_query(query.id, text=_('Courier {} assigned').format(courier_nickname), show_alert=True)


# def send_welcome_message(bot, update):
#     _ = get_channel_trans()
#     if str(update.message.chat_id) == config.couriers_channel:
#         users = update.message.new_chat_members
#         for user in users:
#             if user:
#                 username = user.username
#                 try:
#                     Courier.get(telegram_id=user.id)
#                 except Courier.DoesNotExist:
#                     Courier.create(username=username, telegram_id=user.id, is_active=False)
#                 username = escape_markdown(username)
#                 msg = _('Hello `@{}`').format(username)
#                 shortcuts.send_channel_msg(bot, msg, config.couriers_channel)

#
# def on_courier_action_to_confirm(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, order_id = data.split('|')
#     callback_mapping = {
#         'yes': 'yes|{}'.format(order_id),
#         'no': 'no|{}'.format(order_id)
#     }
#     msg = _('Are you sure?')
#     user_data['courier_menu_msg_to_delete'] = query.message.message_id
#     bot.send_message(
#         chat_id=query.message.chat_id,
#         text=msg,
#         reply_markup=are_you_sure_keyboard(_, callback_mapping)
#     )
#     query.answer()
#     if action == 'confirm_courier_order_delivered':
#         return enums.COURIER_STATE_CONFIRM_ORDER
#     elif action == 'confirm_courier_report_client':
#         return enums.COURIER_STATE_CONFIRM_REPORT
#
#
# def on_courier_ping_choice(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, order_id = data.split('|')
#     chat_id, msg_id = query.message.chat_id, query.message.message_id
#     msg = _('📞 Ping Client')
#     user_data['courier_ping_admin'] = action == 'ping_client_admin'
#     user_data['courier_ping_order_id'] = order_id
#     bot.send_message(chat_id, msg, reply_markup=create_ping_client_keyboard(_))
#     query.answer()
#     return enums.COURIER_STATE_PING
#
#
# def on_courier_ping_client(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action = query.data
#     chat_id, msg_id = query.message.chat_id, query.message.message_id
#     if action == 'back':
#         bot.delete_message(chat_id, msg_id)
#         query.answer()
#         return enums.COURIER_STATE_INIT
#     order_id = user_data['courier_ping_order_id']
#     order = Order.get(id=order_id)
#     if order.client_notified:
#         msg = _('Client was notified already')
#         query.answer(msg)
#         bot.delete_message(chat_id, msg_id)
#         return enums.COURIER_STATE_INIT
#     if action == 'now':
#         user_id = order.user.telegram_id
#         _ = get_trans(user_id)
#         msg = _('Courier has arrived to deliver your order.')
#         bot.send_message(chat_id=user_id,
#                          text=msg)
#         query.answer()
#         order.client_notified = True
#         order.save()
#         bot.delete_message(chat_id, msg_id)
#         del user_data['courier_ping_order_id']
#         del user_data['courier_ping_admin']
#         return enums.COURIER_STATE_INIT
#     elif action == 'soon':
#         msg = _('Enter number of minutes left')
#         bot.edit_message_text(msg, chat_id, msg_id, reply_markup=cancel_button(_))
#         query.answer()
#         return enums.COURIER_STATE_PING_SOON
#
#
# def on_courier_ping_client_soon(bot, update, user_data):
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     if update.callback_query and update.callback_query.data == 'back':
#         upd_msg = update.callback_query.message
#         msg = _('📞 Ping Client')
#         bot.edit_message_text(msg, upd_msg.chat_id, upd_msg.message_id, reply_markup=create_ping_client_keyboard(_))
#         update.callback_query.answer()
#         return enums.COURIER_STATE_PING
#     chat_id = update.message.chat_id
#     try:
#         time = int(update.message.text)
#     except ValueError:
#         msg = _('Enter number of minutes left (number is accepted)')
#         bot.send_message(chat_id, msg, reply_markup=cancel_button(_))
#         return enums.COURIER_STATE_PING_SOON
#     else:
#         order_id = user_data['courier_ping_order_id']
#         order = Order.get(id=order_id)
#         courier_msg = _('Client has been notified')
#         if user_data['courier_ping_admin']:
#             keyboard = create_admin_order_status_keyboard(_, order_id)
#         else:
#             keyboard = create_courier_order_status_keyboard(_, order_id)
#         user_id = order.user.telegram_id
#         _ = get_trans(user_id)
#         msg = _('Courier will arrive in {} minutes.').format(time)
#         bot.send_message(chat_id=user_id,
#                          text=msg)
#         order.save()
#         bot.send_message(chat_id, courier_msg, reply_markup=keyboard)
#         del user_data['courier_ping_order_id']
#         del user_data['courier_ping_admin']
#         return enums.COURIER_STATE_INIT
#
#
# def on_courier_confirm_order(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     user_id = get_user_id(update)
#     action, order_id = data.split('|')
#     _ = get_trans(user_id)
#     chat_id = query.message.chat_id
#     message_id = query.message.message_id
#     if action == 'yes':
#         order = Order.get(id=order_id)
#         order.delivered = True
#         order.save()
#         courier_msg = _('Order №{} is completed!').format(order_id)
#         _ = get_channel_trans()
#         try:
#             courier = Courier.get(telegram_id=user_id)
#             username = escape_markdown(courier.username)
#             msg = _('Order №{} was delivered by courier @{}\n').format(order.id, username)
#         except Courier.DoesNotExist:
#             user = User.get(telegram_id=user_id)
#             username = escape_markdown(user.username)
#             msg = _('Order №{} was delivered by admin {}\n').format(order.id, username)
#         msg += _('Order can be finished now.')
#         delete_msg_id = user_data['courier_menu_msg_to_delete']
#         bot.delete_message(chat_id, delete_msg_id)
#         bot.edit_message_text(chat_id=chat_id,
#                               message_id=message_id,
#                               text=courier_msg,
#                               parse_mode=ParseMode.MARKDOWN)
#         service_channel = config.get_service_channel()
#         shortcuts.bot_send_order_msg(bot, service_channel, msg, _, order_id, channel=True)
#         return enums.COURIER_STATE_INIT
#     elif action == 'no':
#         bot.delete_message(chat_id=chat_id,
#                            message_id=message_id)
#         return enums.COURIER_STATE_INIT

#
# def on_courier_confirm_report(bot, update):
#     query = update.callback_query
#     data = query.data
#     user_id = get_user_id(update)
#     action, order_id = data.split('|')
#     _ = get_trans(user_id)
#     chat_id = query.message.chat_id
#     message_id = query.message.message_id
#     if action == 'yes':
#         msg = _('Please enter report reason')
#         bot.delete_message(chat_id=chat_id,
#                            message_id=message_id)
#         bot.send_message(chat_id =chat_id,
#                          text=msg,
#                          reply_markup=cancel_button(_)
#                          )
#         return enums.COURIER_STATE_REPORT_REASON
#     elif action == 'no':
#         bot.delete_message(chat_id=chat_id,
#                            message_id=message_id)
#         return enums.COURIER_STATE_INIT
#
#
# def on_courier_enter_reason(bot, update):
#     data = update.message.text
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     order_id = get_user_session(user_id)['courier']['order_id']
#     order = Order.get(id=order_id)
#     order_data = OrderPhotos.get(order=order)
#     chat_id = update.message.chat_id
#     courier_msg = _('User was reported!')
#     bot.send_message(chat_id, text=courier_msg)
#     bot.send_message(chat_id=chat_id,
#                      text=order_data.order_text,
#                      reply_markup=create_courier_order_status_keyboard(_, order_id),
#                      parse_mode=ParseMode.MARKDOWN)
#     reported_username = Order.get(id=order_id).user.username
#     courier_username = Courier.get(telegram_id=user_id).username
#     _ = get_channel_trans()
#     msg_args = (escape_markdown(val) for val in (courier_username, reported_username, data))
#     report_msg = _('Order №{}:\n'
#                                'Courier {} has reported {}\n'
#                                'Reason: {}').format(order_id, *msg_args)
#     service_channel = config.get_service_channel()
#     shortcuts.bot_send_order_msg(bot, service_channel, report_msg, _, order_id, channel=True)
#     return enums.COURIER_STATE_INIT
#
#
# def on_courier_cancel_reason(bot, update):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
#     return enums.COURIER_STATE_INIT
#
#
# def on_admin_drop_order(bot, update):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     action, order_id = query.data.split('|')
#     order = Order.get(id=order_id)
#     shortcuts.change_order_products_credits(order, True)
#     order.courier = None
#     order.save()
#     chat_id = query.message.chat_id
#     message_id = query.message.message_id
#     bot.delete_message(chat_id, message_id)
#     msg = _('Order №{} was dropped!').format(order.id)
#     bot.send_message(chat_id, msg)
#
#
# def on_product_categories(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     user_data = get_user_session(user_id)
#     _ = get_trans(user_id)
#     chat_id, message_id = query.message.chat_id, query.message.message_id
#     try:
#         action, val = query.data.split('|')
#     except ValueError:
#         action = query.data
#     if action == 'page':
#         categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
#         keyboard = general_select_one_keyboard(_, categories, int(val))
#         bot.edit_message_text(_('Please select a category'), chat_id, message_id,
#                               reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
#         query.answer()
#         return enums.BOT_PRODUCT_CATEGORIES
#     user = User.get(telegram_id=user_id)
#     total = cart.get_cart_total(get_user_session(user_id))
#     if action == 'select':
#         cat = ProductCategory.get(id=val)
#         cat_title = escape_markdown(cat.title.replace('`', ''))
#         msg = _('Category `{}` products:').format(cat_title)
#         bot.edit_message_text(msg, chat_id, message_id, parse_mode=ParseMode.MARKDOWN)
#         # send_products to current chat
#         for product in Product.filter(category=cat, is_active=True):
#             product_count = cart.get_product_count(
#                 user_data, product.id)
#             subtotal = cart.get_product_subtotal(
#                 user_data, product.id)
#             product_title, prices = cart.product_full_info(
#                 user_data, product.id)
#             shortcuts.send_product_media(bot, product, chat_id)
#             bot.send_message(chat_id,
#                              text=create_product_description(
#                                  user_id,
#                                  product_title, prices,
#                                  product_count, subtotal),
#                              reply_markup=create_product_keyboard(_,
#                                                                   product.id, user_data, cart),
#                              parse_mode=ParseMode.MARKDOWN,
#                              timeout=20, )
#         user = User.get(telegram_id=user_id)
#         total = cart.get_cart_total(get_user_session(user_id))
#         user_data = get_user_session(user_id)
#         products_info = cart.get_products_info(user_data)
#         if products_info:
#             msg = create_cart_details_msg(user_id, products_info)
#         else:
#             msg = config.get_order_text()
#         main_msg = bot.send_message(chat_id,
#                          text=msg,
#                          reply_markup=main_keyboard(_,
#                                                            config.get_reviews_channel(),
#                                                            user,
#                                                            is_admin(bot, user_id), total),
#                          parse_mode=ParseMode.MARKDOWN)
#         user_data['menu_id'] = main_msg['message_id']
#         session_client.json_set(user_id, user_data)
#     elif action == 'back':
#         user_data = get_user_session(user_id)
#         products_info = cart.get_products_info(user_data)
#         if products_info:
#             msg = create_cart_details_msg(user_id, products_info)
#         else:
#             msg = config.get_order_text()
#         bot.edit_message_text(msg, chat_id, message_id,
#                               reply_markup=main_keyboard(_,
#                                                                 config.get_reviews_channel(),
#                                                                 user,
#                                                                 is_admin(bot, user_id), total),
#                               parse_mode=ParseMode.MARKDOWN
#                               )
#     query.answer()
#     return enums.BOT_STATE_INIT
#
#
# def on_calendar_change(bot, update, user_data):
#     query = update.callback_query
#     user_id = get_user_id(update)
#     _ = get_trans(user_id)
#     chat_id = query.message.chat_id
#     try:
#         saved_date = user_data['calendar_date']
#         calendar_state = user_data['calendar_state']
#     except KeyError:
#         msg = _('Failed to get calendar date, please initialize calendar again.')
#         bot.send_message(msg, chat_id)
#     else:
#         data = query.data
#         year, month = saved_date
#         msg = _('Pick year, month or day')
#         if data == 'calendar_next_year':
#             year += 1
#         elif data == 'calendar_previous_year':
#             year -= 1
#         elif data == 'calendar_next_month':
#             month += 1
#             if month > 12:
#                 month = 1
#                 year += 1
#         elif data == 'calendar_previous_month':
#             month -= 1
#             if month < 1:
#                 month = 12
#                 year -= 1
#         if year < 1:
#             year = 1
#         user_data['calendar_date'] = year, month
#         bot.edit_message_text(chat_id=chat_id, message_id=query.message.message_id,
#                               text=msg, reply_markup=calendar_keyboard(year, month, _))
#         query.answer()
#         return calendar_state


