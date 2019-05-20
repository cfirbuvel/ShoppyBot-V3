from telegram import ParseMode
from telegram.utils.helpers import escape_markdown

from .decorators import user_passes
from .helpers import logger, config, get_channel_trans, get_trans, get_user_id, get_service_channel, get_couriers_channel
from .models import Order, User, OrderBtcPayment, CourierChatMessage, CourierChat
from . import shortcuts, enums, keyboards, messages, states


@user_passes
def on_courier_menu(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, order_id = query.data.split('|')
    order = Order.get(id=order_id)
    user = User.get(telegram_id=user_id)
    if order.courier != user:
        msg = _('You are not responsible for this order anymore')
        bot.edit_message_text(msg, chat_id, msg_id)
        query.answer()
        return enums.BOT_INIT
    user_data['courier_menu'] = {'order_id': order_id, 'msg_id': msg_id}
    if action in ('courier_menu_delivered', 'courier_menu_report', 'courier_menu_dropped'):
        msg = _('Are you sure?')
        reply_markup = keyboards.are_you_sure_keyboard(_)
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        query.answer()
        if action == 'courier_menu_delivered':
            state = enums.COURIER_STATE_CONFIRM_ORDER
        elif action == 'courier_menu_report':
            state = enums.COURIER_STATE_CONFIRM_REPORT
        else:
            state = enums.COURIER_STATE_CONFIRM_DROPPED
        return state
    elif action == 'courier_menu_ping':
        msg = _('📞 Ping Client')
        reply_markup = keyboards.create_ping_client_keyboard(_)
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        query.answer()
        return enums.COURIER_STATE_PING
    elif action == 'courier_menu_chat':
        client = order.user
        try:
            chat = CourierChat.get(order=order, courier=user, user=client)
        except:
            chat = CourierChat.create(order=order, courier=user, user=client)
        if not chat.active:
            client_id = client.telegram_id
            user_trans = get_trans(client_id)
            msg = user_trans('Order №{}:').format(order_id)
            msg += '\n'
            msg += user_trans('Courier has started a chat.')
            reply_markup = keyboards.chat_with_courier_keyboard(_, order_id)
            menu_msg = bot.send_message(client_id, msg, reply_markup=reply_markup)
            chat.active = True
            chat.user_menu_id = menu_msg['message_id']
        msg = _('⌨️ Chat with client')
        reply_markup = keyboards.chat_with_client_keyboard(_, order_id)
        menu_msg = bot.send_message(chat_id, msg, reply_markup=reply_markup)
        chat.courier_menu_id = menu_msg['message_id']
        chat.save()
        query.answer()
        return enums.COURIER_STATE_CHAT


@user_passes
def on_courier_chat(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, order_id = query.data.split('|')
    order = Order.get(id=order_id)
    user = User.get(telegram_id=user_id)
    if order.courier != user:
        msg = _('You are not responsible for this order anymore')
        bot.edit_message_text(msg, chat_id, msg_id)
        msg_id = user_data['courier_menu']['msg_id']
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.BOT_INIT
    client = order.user
    chat = CourierChat.get(order=order, courier=user, user=client)
    if not chat.active:
        msg = _('Chat is not active anymore.')
        query.answer(msg, show_alert=True)
        return states.enter_courier_main_menu(_, bot, chat_id, user, order, msg_id, query.id)
    if action == 'courier_chat_send':
        user_data['chat_order_id'] = order_id
        msg = _('Please send text, photo or video:')
        reply_markup = keyboards.cancel_button(_)
        menu_msg = bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        chat.courier_menu_id = menu_msg['message_id']
        chat.save()
        query.answer()
        return enums.COURIER_STATE_CHAT_SEND
    elif action == 'courier_chat_finish':
        CourierChatMessage.update({CourierChatMessage.read: True, CourierChatMessage.replied: True})\
            .where(CourierChatMessage.chat == chat).execute()
        chat.active = False
        chat.save()
        client_id = client.telegram_id
        user_trans = get_trans(client_id)
        msg = user_trans('Order №{}:').format(order_id)
        msg += '\n'
        msg = user_trans('Courier has ended a chat.')
        bot.send_message(client_id, msg)
        msg = _('Chat has been ended.')
        query.answer(msg)
        return states.enter_courier_main_menu(_, bot, chat_id, user, order, msg_id, query.id)


@user_passes
def on_courier_chat_send(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    order_id = user_data['chat_order_id']
    user = User.get(telegram_id=user_id)
    order = Order.get(id=order_id)
    if order.courier != user:
        msg = _('You are not responsible for this order anymore')
        bot.send_message(chat_id, msg)
        msg_id = user_data['courier_menu']['msg_id']
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.BOT_INIT
    if query and query.data == 'back':
        msg = _('⌨️ Chat with client')
        reply_markup = keyboards.chat_with_client_keyboard(_, order_id)
        msg_id = query.message.message_id
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.COURIER_STATE_CHAT
    else:
        chat = CourierChat.get(user=order.user, order=order, courier=user)
        if not chat.active:
            msg = _('Chat is not active anymore.')
            bot.send_message(chat_id, msg)
            return states.enter_courier_main_menu(_, bot, chat_id, user, order)
        for msg_type in ('text', 'photo', 'video'):
            msg_data = getattr(update.message, msg_type)
            if msg_data:
                break
        status_msg = _('Message has been sent.')
        if msg_type in ('video', 'photo'):
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
        client = order.user
        client_id = client.telegram_id
        user_trans = get_trans(client_id)
        msg = user_trans('Order №{}:').format(order.id)
        msg += '\n'
        msg += user_trans('You have new message from courier')
        reply_markup = keyboards.chat_client_msg_keyboard(_, chat_msg.id)
        user_menu_id = chat.user_menu_id
        if user_menu_id:
            bot.edit_message_text(msg, client_id, user_menu_id, reply_markup=reply_markup)
        else:
            bot.send_message(client_id, msg, reply_markup=reply_markup)
        chat.user_menu_id = None
        bot.delete_message(chat_id, chat.courier_menu_id)
        msg = _('⌨️ Chat with client')
        reply_markup = keyboards.chat_with_client_keyboard(_, order_id)
        menu_msg = bot.send_message(chat_id, msg, reply_markup=reply_markup)
        chat.courier_menu_id = menu_msg['message_id']
        chat.save()
        answer_to = user_data.get('answer_to_id')
        if answer_to:
            answer_to = CourierChatMessage.get(id=answer_to)
            answer_to.replied = True
            answer_to.save()
        return enums.COURIER_STATE_CHAT


@user_passes
def on_open_chat_msg(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    chat_msg_id = query.data.split('|')[1]
    chat_msg = CourierChatMessage.get(id=chat_msg_id)
    msg_type = chat_msg.msg_type
    chat = chat_msg.chat
    client = chat.user
    client_id = client.telegram_id
    client_msg_id = chat_msg.sent_msg_id
    read_msg = _('Message has been read. ✅')
    client_msg = chat_msg.message
    if msg_type in ('video', 'photo'):
        bot.delete_message(chat_id, msg_id)
        caption = _('From client')
        if msg_type == 'video':
            bot.send_video(chat_id, client_msg, caption=caption)
            bot.edit_message_caption(client_id, client_msg_id, caption=read_msg)
        else:
            bot.send_photo(chat_id, client_msg, caption=caption)
            bot.edit_message_caption(client_id, client_msg_id, caption=read_msg)
    else:
        open_msg = _('From client:')
        open_msg += '\n\n'
        open_msg += client_msg
        bot.edit_message_text(open_msg, chat_id, msg_id)
        query.answer()
        client_msg += '\n\n'
        client_msg += read_msg
        bot.edit_message_text(client_msg, client_id, client_msg_id)
    chat_msg.read = True
    chat_msg.save()
    msg = _('⌨️ Chat with client')
    reply_markup = keyboards.chat_with_client_keyboard(_, chat.order.id)
    # if chat.courier_menu_id:
    #     menu_msg = bot.edit_message_text(msg, chat_id, chat.courier_menu_id, reply_markup=reply_markup)
    # else:
    if not chat.courier_menu_id:
        menu_msg = bot.send_message(chat_id, msg, reply_markup=reply_markup)
        chat.courier_menu_id = menu_msg['message_id']
        chat.save()
    user_data['answer_to_id'] = chat_msg.id
    return enums.COURIER_STATE_CHAT


@user_passes
def on_client_waiting_keyboard(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, courier_chat_id = query.data.split('|')
    courier_chat = CourierChat.get(id=courier_chat_id)
    msg = _('Thank you for response. Your answer will be sent to service channel shortly.')
    if action == 'courier_ping_yes':
        reply_markup = keyboards.chat_with_client_keyboard(_, courier_chat.order.id)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        order = courier_chat.order
        _ = get_channel_trans()
        msg = _('Order №{}:').format(order.id)
        msg += '\n\n'
        msg += _('Courier has answered that everything is ok.')
        shortcuts.send_channel_msg(bot, msg, get_service_channel(), order=order, parse_mode=None)
        client_id = courier_chat.user.telegram_id
        _ = get_trans(client_id)
        msg = _('Order №{}:').format(order.id)
        msg += '\n'
        msg += _('Courier has answered that everything is ok.')
        reply_markup = keyboards.chat_with_courier_keyboard(_, order.id)
        if courier_chat.user_menu_id:
            menu_msg = bot.edit_message_text(msg, client_id, courier_chat.user_menu_id, reply_markup=reply_markup)
        else:
            menu_msg = bot.send_message(client_id, msg, reply_markup=reply_markup)
        courier_chat.user_menu_id = menu_msg['message_id']
        courier_chat.unresponsible_answer = CourierChat.YES
        courier_chat.ping_sent = False
        courier_chat.save()
    elif action == 'courier_ping_no':
        courier_chat.unresponsible_answer = CourierChat.NO
        courier_chat.save()
        bot.edit_message_text(msg, chat_id, msg_id)
    query.answer()
    return enums.COURIER_STATE_CHAT


@user_passes
def on_drop_order(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    order_id = user_data['courier_menu']['order_id']
    main_msg_id = user_data['courier_menu']['msg_id']
    order = Order.get(id=order_id)
    user = User.get(telegram_id=user_id)
    if order.courier != user:
        msg = _('You are not responsible for this order anymore')
        bot.edit_message_text(msg, chat_id, msg_id)
        bot.delete_message(chat_id, main_msg_id)
        query.answer()
        return enums.BOT_INIT
    if action == 'yes':
        is_courier = user.is_courier
        if is_courier:
            shortcuts.change_order_products_credits(order, True, user)
        else:
            shortcuts.change_order_products_credits(order, True)
        order.status = Order.CONFIRMED
        order.courier = None
        order.save()
        msg = _('Order №{} was dropped!').format(order.id)
        bot.delete_message(chat_id, msg_id)
        bot.edit_message_text(msg, chat_id, main_msg_id)
        _ = get_channel_trans()
        msg = _('Order №{} was dropped by @{}.').format(order.id, user.username)
        shortcuts.send_channel_msg(bot, msg, get_service_channel(), order=order, parse_mode=None)
        query.answer()
        return enums.BOT_INIT
    elif action == 'no':
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.COURIER_STATE_INIT
        # return states.enter_courier_main_menu(_, bot, chat_id, user, order, msg_id, query.id)


@user_passes
def on_courier_confirm_order(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    action = query.data
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    order_id = user_data['courier_menu']['order_id']
    main_msg_id = user_data['courier_menu']['msg_id']
    user = User.get(telegram_id=user_id)
    order = Order.get(id=order_id)
    if order.courier != user:
        msg = _('You are not responsible for this order anymore')
        bot.edit_message_text(msg, chat_id, msg_id)
        bot.delete_message(chat_id, main_msg_id)
        query.answer()
        return enums.BOT_INIT
    if order.status == Order.CANCELLED:
        msg = _('Order #{} was cancelled.')
        query.answer(msg, show_alert=True)
        bot.delete_message(chat_id, msg_id)
        return enums.COURIER_STATE_INIT
    if action == 'yes':
        order.status = Order.DELIVERED
        order.save()
        bot.delete_message(chat_id, msg_id)
        msg = _('Order №{} is completed!').format(order_id)
        bot.edit_message_text(msg, chat_id, main_msg_id)
        _ = get_channel_trans()
        status = user.permission.get_permission_display()
        msg = _('Order №{} was delivered by {} @{}\n').format(order.id, status, user.username)
        msg += _('Client: @{}').format(order.user.username)
        service_channel = get_service_channel()
        reply_markup = keyboards.order_finished_keyboard(_, order_id)
        msg_id = shortcuts.send_channel_msg(bot, msg, service_channel, keyboard=reply_markup, order=order, parse_mode=None)
        order.order_text_msg_id = msg_id
        order.save()
        query.answer()
        return enums.BOT_INIT
        # return states.enter_menu(bot, update, user_data)
    elif action == 'no':
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.COURIER_STATE_INIT
        # return states.enter_courier_main_menu(_, bot, chat_id, user, order, msg_id, query.id)


@user_passes
def on_courier_confirm_report(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    action = query.data
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'yes':
        msg = _('Please enter report reason.')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.COURIER_STATE_REPORT_REASON
    elif action == 'no':
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.COURIER_STATE_INIT
        # user = User.get(telegram_id=user_id)
        # return states.enter_courier_main_menu(_, bot, chat_id, user, order, msg_id, query.id)


@user_passes
def on_courier_enter_reason(bot, update, user_data):
    user_id = get_user_id(update)
    chat_id = update.effective_chat.id
    query = update.callback_query
    _ = get_trans(user_id)
    user = User.get(telegram_id=user_id)
    order_id = user_data['courier_menu']['order_id']
    order = Order.get(id=order_id)
    if query and query.data == 'back':
        msg_id = query.message.message_id
        return states.enter_courier_main_menu(_, bot, chat_id, user, order, msg_id, query.id)
    report_reason = update.message.text
    msg = _('User was reported!')
    bot.send_message(chat_id, msg)
    reported_username = order.user.username
    courier_username = user.username
    _ = get_channel_trans()
    report_msg = _('Order №{}:\n'
                   'Courier {} has reported {}\n'
                   'Reason: {}').format(order_id, reported_username, courier_username, report_reason)
    service_channel = get_service_channel()
    shortcuts.send_channel_msg(bot, report_msg, service_channel, order=order, parse_mode=None)
    return states.enter_courier_main_menu(_, bot, chat_id, user, order)


@user_passes
def on_courier_ping_client(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    order_id = user_data['courier_menu']['order_id']
    user = User.get(telegram_id=user_id)
    order = Order.get(id=order_id)
    if order.courier != user:
        msg = _('You are not responsible for this order anymore')
        bot.edit_message_text(msg, chat_id, msg_id)
        msg_id = user_data['courier_menu']['msg_id']
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.BOT_INIT
    if order.status == Order.CANCELLED:
        msg = _('Order #{} was cancelled.').format(order_id)
        query.answer(msg, show_alert=True)
        bot.delete_message(chat_id, msg_id)
        return enums.COURIER_STATE_INIT
        #bot.edit_message_text(msg, chat_id, msg_id)
        # return states.enter_courier_main_menu(_, bot, chat_id, user, order, query.id)
    if action == 'back':
        bot.delete_message(chat_id, msg_id)
        query.answer()
        return enums.COURIER_STATE_INIT
    if order.client_notified:
        msg = _('Client was notified already')
        query.answer(msg, show_alert=True)
        return enums.COURIER_STATE_PING
    if action == 'now':
        user_id = order.user.telegram_id
        user_trans = get_trans(user_id)
        msg = user_trans('Courier has arrived to deliver your order.')
        bot.send_message(chat_id=user_id,
                         text=msg)
        order.client_notified = True
        order.save()
        bot.delete_message(chat_id, msg_id)
        msg = _('Client has been notified.')
        query.answer(msg, show_alert=True)
        return states.enter_courier_main_menu(_, bot, chat_id, user, order)
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
        user = User.get(telegram_id=user_id)
        order_id = user_data['courier_menu']['order_id']
        order = Order.get(id=order_id)
        if order.courier != user:
            msg = _('You are not responsible for this order anymore')
            bot.send_message(chat_id, msg)
            msg_id = user_data['courier_menu']['msg_id']
            bot.delete_message(chat_id, msg_id)
            query.answer()
            return enums.BOT_INIT
        if order.status == Order.CANCELLED:
            msg = _('Order #{} was cancelled.').format(order_id)
            bot.send_message(chat_id, msg)
            return states.enter_courier_main_menu(_, bot, chat_id, user, order)
        user_id = order.user.telegram_id
        order.client_notified = True
        order.save()
        user_trans = get_trans(user_id)
        msg = user_trans('Order #{} notice:').format(order.id)
        msg += '\n\n'
        msg += user_trans('Courier will arrive in {} minutes.').format(time)
        bot.send_message(user_id, msg)
        msg = _('Client has been notified')
        bot.send_message(chat_id, msg)
        return states.enter_courier_main_menu(_, bot, chat_id, user, order)



