from telegram import ParseMode

from .decorators import user_passes
from .helpers import logger, config, get_channel_trans, get_trans, get_user_id, get_service_channel, get_couriers_channel
from .models import Order, User, OrderBtcPayment
from . import shortcuts, enums, keyboards, messages, states


@user_passes
def on_drop_order(bot, update, user_data):
    query = update.callback_query
    order_id = query.data.split('|')[1]
    try:
        order = Order.get(id=order_id)
    except Order.DoesNotExist:
        logger.info('Order № {} not found!'.format(order_id))
        user_id = get_user_id(update)
        _ = get_trans(user_id)
        msg = _('Order #{} does not exist')
        query.answer(msg, show_alert=True)
    else:
        chat_id, msg_id = query.message.chat_id, query.message.message_id
        shortcuts.change_order_products_credits(order, True, order.courier)
        order.status = Order.CONFIRMED
        order.courier = None
        order.save()
        _ = get_channel_trans()
        bot.delete_message(chat_id, msg_id)
        msg = _('Order №{} was dropped by courier').format(order_id)
        shortcuts.send_channel_msg(bot, msg, get_couriers_channel(), order=order)
    return states.enter_menu(bot, update, user_data)
    # return enums.BOT_INIT
        # order_pickup_state = order.shipping_method
    # order_location = order_info.location
    # if order_location:
    #     order_location = order_location.title
    # keyboard = keyboards.service_notice_keyboard(order_id, _, answers_ids, order_location, order_pickup_state)
    # send_channel_msg(bot, order_data.order_text, couriers_channel, keyboard, order)
    # query.answer(text=_('Order sent to couriers channel'), show_alert=True)


@user_passes
def on_courier_action_to_confirm(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, order_id = query.data.split('|')
    # user_data['courier_msg_id'] = msg_id
    msg = _('Are you sure?')
    user_data['courier_menu'] = {'msg_to_delete': msg_id, 'order_id': order_id}
    reply_markup = keyboards.are_you_sure_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup)
    query.answer()
    if action == 'courier_menu_delivered':
        return enums.COURIER_STATE_CONFIRM_ORDER
    elif action == 'courier_menu_report':
        return enums.COURIER_STATE_CONFIRM_REPORT


@user_passes
def on_courier_ping_choice(bot, update, user_data):
    print('entered ping')
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, order_id = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    # user_data['courier_msg_id'] = msg_id
    msg = _('📞 Ping Client')
    user_data['courier_menu'] = {'ping_admin': action == 'courier_menu_ping_admin', 'order_id': order_id}
    reply_markup = keyboards.create_ping_client_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup)
    query.answer()
    return enums.COURIER_STATE_PING


@user_passes
def on_courier_ping_client(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.COURIER_STATE_INIT
    order_id = user_data['courier_menu']['order_id']
    order = Order.get(id=order_id)
    if order.client_notified:
        msg = _('Client was notified already')
        query.answer(msg, show_alert=True)
        bot.delete_message(chat_id, msg_id)
        return enums.COURIER_STATE_INIT
    if action == 'now':
        user_id = order.user.telegram_id
        _ = get_trans(user_id)
        msg = _('Courier has arrived to deliver your order.')
        bot.send_message(chat_id=user_id,
                         text=msg)
        query.answer()
        order.client_notified = True
        order.save()
        bot.delete_message(chat_id, msg_id)
        return enums.COURIER_STATE_INIT
    elif action == 'soon':
        msg = _('Enter number of minutes left')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.COURIER_STATE_PING_SOON


@user_passes
def on_courier_ping_client_soon(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query and query.data == 'back':
        msg = _('📞 Ping Client')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=keyboards.create_ping_client_keyboard(_))
        query.answer()
        return enums.COURIER_STATE_PING
    try:
        time = int(update.message.text)
    except ValueError:
        msg = _('Enter number of minutes left (number is accepted)')
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
        return enums.COURIER_STATE_PING_SOON
    else:
        order_id = user_data['courier_menu']['ping_order_id']
        courier_msg = _('Client has been notified')
        if user_data['courier_menu']['ping_admin']:
            keyboard = keyboards.admin_order_status_keyboard(_, order_id)
        else:
            keyboard = keyboards.courier_order_status_keyboard(_, order_id)
        order = Order.get(id=order_id)
        user_id = order.user.telegram_id
        order.client_notified = True
        order.save()
        _ = get_trans(user_id)
        msg = _('Order #{} notice:').format(order.id)
        msg += '\n\n'
        msg += _('Courier will arrive in {} minutes.').format(time)
        bot.send_message(user_id, msg)
        bot.send_message(chat_id, courier_msg, reply_markup=keyboard)
        return enums.COURIER_STATE_INIT


@user_passes
def on_courier_confirm_order(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    action = query.data
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'yes':
        order_id = user_data['courier_menu']['order_id']
        order = Order.get(id=order_id)
        order.status = Order.DELIVERED
        order.save()
        courier_msg = _('Order №{} is completed!').format(order_id)
        _ = get_channel_trans()
        courier = User.get(telegram_id=user_id)
        status = courier.permission.get_permission_display()
        msg = _('Order №{} was delivered by {} @{}\n').format(order.id, status, courier.username)
        msg += _('Order can be finished now.')
        delete_msg_id = user_data['courier_menu']['msg_to_delete']
        bot.delete_message(chat_id, delete_msg_id)
        bot.edit_message_text(courier_msg, chat_id, msg_id)
        service_channel = get_service_channel()
        # shortcuts.bot_send_order_msg(bot, service_channel, msg, _, order_id, channel=True)
        shortcuts.send_channel_msg(bot, msg, service_channel, order=order)
        return states.enter_menu(bot, update, user_data)
        # return enums.BOT_INIT
    elif action == 'no':
        bot.delete_message(chat_id, msg_id)
        return enums.COURIER_STATE_INIT
        # return enums.BOT_INIT


@user_passes
def on_courier_confirm_report(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    action = query.data
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'yes':
        # order_id = user_data['courier_menu']['order_id']
        msg = _('Please enter report reason')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
        return enums.COURIER_STATE_REPORT_REASON
    elif action == 'no':
        bot.delete_message(chat_id, msg_id)
        return enums.COURIER_STATE_INIT
        # return enums.BOT_INIT


@user_passes
def on_courier_enter_reason(bot, update, user_data):
    report_reason = update.message.text
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    order_id = user_data['courier_menu']['order_id']
    order = Order.get(id=order_id)
    chat_id = update.message.chat_id
    courier_msg = _('User was reported!')
    bot.send_message(chat_id, text=courier_msg)
    try:
        btc_data = OrderBtcPayment.get(order=order)
    except OrderBtcPayment.DoesNotExist:
        btc_data = None
    order_msg = messages.create_service_notice(_, order, btc_data)
    reply_markup = keyboards.courier_order_status_keyboard(_, order_id)
    bot.send_message(chat_id, order_msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    reported_username = order.user.username
    courier_username = order.courier.username
    _ = get_channel_trans()
    report_msg = _('Order №{}:\n'
                   'Courier {} has reported {}\n'
                   'Reason: {}').format(order_id, reported_username, courier_username, report_reason)
    service_channel = get_service_channel()
    shortcuts.send_channel_msg(bot, report_msg, service_channel, order=order, parse_mode=None)
    return enums.COURIER_STATE_INIT
    # return enums.BOT_INIT


def on_courier_cancel_reason(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
    return enums.COURIER_STATE_INIT
    # return enums.BOT_INIT


def on_admin_drop_order(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, order_id = query.data.split('|')
    order = Order.get(id=order_id)
    shortcuts.change_order_products_credits(order, True)
    order.status = Order.CONFIRMED
    order.courier = None
    order.save()
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    # user_data['courier_msg_id'] = msg_id
    bot.delete_message(chat_id, msg_id)
    msg = _('Order №{} was dropped!').format(order.id)
    bot.send_message(chat_id, msg)
    return states.enter_menu(bot, update, user_data)
    # return enums.BOT_INIT

