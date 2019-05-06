import datetime
import operator

from telegram import ParseMode, TelegramError, InputMediaPhoto, InputMediaVideo
from telegram.utils.helpers import escape_markdown, escape

from .models import Order, OrderItem, ProductWarehouse, ChannelMessageData, ProductCount, UserPermission,\
    UserIdentificationAnswer, Product, ProductCategory, WorkingHours

from .helpers import config, get_trans, logger, get_user_id, get_channel_trans, Cart, get_full_product_info
from . import keyboards, messages, states


# def make_confirm(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     label, order_id, courier_name = data.split('|')
#     delete_channel_msg(bot, config.get_service_channel(), query.message.message_id)
#     try:
#         order = Order.get(id=order_id)
#     except Order.DoesNotExist:
#         logger.info('Order № {} not found!'.format(order_id))
#     else:
#         order.confirmed = True
#         order.save()
#
#         user_id = order.user.telegram_id
#         _ = get_trans(user_id)
#         courier_name = escape_markdown(courier_name)
#         bot.send_message(
#             user_id,
#             text=_('Courier @{} assigned to your order').format(courier_name),
#             parse_mode=ParseMode.MARKDOWN,
#         )
#         courier_id = order.courier.telegram_id
#         user_data = get_user_session(courier_id)
#         user_data['courier']['order_id'] = order_id
#         session_client.json_set(courier_id, user_data)
#         order_data = OrderPhotos.get(order==order)
#         _ = get_trans(courier_id)
#         bot.send_message(courier_id,
#                          text=order_data.order_text,
#                          reply_markup=keyboards.courier_order_status_keyboard(_, order_id),
#                          parse_mode=ParseMode.MARKDOWN)


# def make_unconfirm(bot, update, user_data):
#     query = update.callback_query
#     data = query.data
#     label, order_id, courier_name, answers_ids, assigned_msg_id = data.split('|')
#     delete_channel_msg(bot, config.service_channel, query.message.message_id)
#     couriers_channel = config.couriers_channel
#     for answer_id in answers_ids.split(','):
#         delete_channel_msg(bot, couriers_channel, answer_id)
#     delete_channel_msg(bot, couriers_channel, assigned_msg_id)
#     try:
#         order = Order.get(id=order_id)
#     except Order.DoesNotExist:
#         logger.info('Order № {} not found!'.format(order_id))
#     else:
#         change_order_products_credits(order, True, order.courier)
#         order.courier = None
#         order.save()
#         _ = get_channel_trans()
#         order_data = OrderPhotos.get(order=order)
#         msg = _('The admin did not confirm. Please retake '
#                 'responsibility for order №{}').format(order_id)
#         send_channel_msg(bot, msg, couriers_channel, order=order)
#         answers_ids = send_order_identification_answers(bot, couriers_channel, order, send_one=True, channel=True)
#         answers_ids = ','.join(answers_ids)
#         order_info = Order.get(id=order_id)
#         order_pickup_state = order_info.shipping_method
#         order_location = order_info.location
#         if order_location:
#             order_location = order_location.title
#         keyboard = keyboards.service_notice_keyboard(order_id, _, answers_ids, order_location, order_pickup_state)
#         send_channel_msg(bot, order_data.order_text, couriers_channel, keyboard, order)


# def resend_responsibility_keyboard(bot, update):
#     query = update.callback_query
#     data = query.data
#     order_id = data.split('|')[1]
#     try:
#         order = Order.get(id=order_id)
#     except Order.DoesNotExist:
#         logger.info('Order № {} not found!'.format(order_id))
#         return
#     else:
#         change_order_products_credits(order, True, order.courier)
#         order.confirmed = False
#         order.courier = None
#         order.save()
#     couriers_channel = config.couriers_channel
#     _ = get_channel_trans()
#     bot.delete_message(query.message.chat_id,
#                        message_id=query.message.message_id)
#     order_data = OrderPhotos.get(order=order)
#     msg = _('Order №{} was dropped by courier').format(order_id)
#     send_channel_msg(bot, msg, couriers_channel, order=order)
#     answers_ids = send_order_identification_answers(bot, couriers_channel, order, send_one=True, channel=True)
#     answers_ids = ','.join(answers_ids)
#
#     order_info = Order.get(id=order_id)
#     order_pickup_state = order_info.shipping_method
#     order_location = order_info.location
#     if order_location:
#         order_location = order_location.title
#     keyboard = keyboards.service_notice_keyboard(order_id, _, answers_ids, order_location, order_pickup_state)
#     send_channel_msg(bot, order_data.order_text, couriers_channel, keyboard, order)
#     query.answer(text=_('Order sent to couriers channel'), show_alert=True)


# def bot_send_order_msg(_, bot, chat_id, message, order_id, order_data=None, channel=False, parse_mode=ParseMode.MARKDOWN):
#     order = Order.get(id=order_id)
#     keyboard = keyboards.show_order_keyboard(_, order_id)
#     if channel:
#         msg_id = send_channel_msg(bot, message, chat_id, keyboard, order, parse_mode)
#     else:
#         order_msg = bot.send_message(chat_id, message, reply_markup=keyboard, parse_mode=parse_mode)
#         msg_id = order_msg['message_id']
#     order_data.order_hidden_text = message
#     order_data.order_text_msg_id = str(msg_id)
#     order_data.save()


def send_order_identification_answers(bot, chat_id, order, send_one=False, channel=False):
    answers = []
    photos_answers = []
    photos = []
    class_map = {'photo': InputMediaPhoto, 'video': InputMediaVideo}
    for answer in order.identification_answers:
        type = answer.stage.type
        content = answer.content
        question = answer.question.content
        if type in ('photo', 'video'):
            media_class = class_map[type]
            content = media_class(content, question)
            photos.append(content)
            photos_answers.append(answer)
        else:
            question = escape(question)
            content = escape(content)
            content = '<i>{}</i>:\n' \
                      '{}'.format(question, content)
            answers.append((content, answer))
        if send_one:
            break
    if photos:
        if channel:
            msgs_ids = send_channel_media_group(bot, chat_id, photos, order=order)
        else:
            photo_msgs = bot.send_media_group(chat_id, photos)
            msgs_ids = [msg['message_id'] for msg in photo_msgs]
    else:
        msgs_ids = []
    for ph_id, answer in zip(msgs_ids, photos_answers):
        answer.msg_id = ph_id
        answer.save()
    for content, answer in answers:
        if channel:
            sent_msg_id = send_channel_msg(bot, content, chat_id, parse_mode=ParseMode.HTML, order=order)
            answer.msg_id = sent_msg_id
        else:
            msg = bot.send_message(chat_id, content, parse_mode=ParseMode.HTML)
            sent_msg_id = msg['message_id']
        answer.save()
        msgs_ids.append(str(sent_msg_id))
    return msgs_ids


def send_identification_answers(answers, bot, chat_id, send_one=False, channel=False):
    text_answers = []
    photos_answers = []
    photos = []
    class_map = {'photo': InputMediaPhoto, 'video': InputMediaVideo}
    for answer in answers:
        type = answer.stage.type
        content = answer.content
        question = answer.question.content
        if type in ('photo', 'video'):
            media_class = class_map[type]
            content = media_class(content, question)
            photos.append(content)
            photos_answers.append(answer)
        else:
            question = escape(question)
            content = escape(content)
            content = '<i>{}</i>:\n' \
                      '{}'.format(question, content)
            text_answers.append((content, answer))
        if send_one:
            break
    msgs_ids = []
    if photos:
        if channel:
            msgs_ids += send_channel_media_group(bot, chat_id, photos)
        else:
            msgs = bot.send_media_group(chat_id, photos)
            msgs_ids += [msg['message_id'] for msg in msgs]
    for content, answer in text_answers:
        if channel:
            msg_id = send_channel_msg(bot, content, chat_id, parse_mode=ParseMode.HTML)
        else:
            msg = bot.send_message(chat_id, content, parse_mode=ParseMode.HTML)
            msg_id = msg['message_id']
        msgs_ids.append(msg_id)
    return msgs_ids


def send_user_identification_answers(bot, chat_id, user):
    answers = user.identification_answers
    return send_identification_answers(answers, bot, chat_id)


def send_product_info(bot, product, chat_id, trans):
    if product.group_price:
        product_prices = product.group_price.product_counts
    else:
        product_prices = product.product_counts
    product_prices = ((obj.count, obj.price) for obj in product_prices)
    send_product_media(bot, product, chat_id)
    msg = messages.create_admin_product_description(trans, product.title, product_prices)
    bot.send_message(chat_id,
                     text=msg)


def initialize_calendar(_, bot, user_data, chat_id, state, message_id=None, query_id=None, msg=None, cancel=False):
    current_date = datetime.date.today()
    year, month = current_date.year, current_date.month
    if not msg:
        msg = _('Pick year, month or day')
    user_data['calendar'] = {'year': year, 'month': month, 'msg': msg, 'cancel': cancel, 'state': state}
    reply_markup = keyboards.calendar_keyboard(year, month, _, cancel)
    if message_id:
        bot.edit_message_text(msg, chat_id, message_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    return state


def initialize_time_picker(_, bot, user_data, chat_id, state, msg_id, query_id, msg, cancel=False):
    current_time = datetime.datetime.now()
    hour, minute = current_time.hour, current_time.minute
    user_data['time_picker'] = {'hour': hour, 'minute': minute, 'msg': msg, 'cancel': cancel, 'state': state}
    reply_markup = keyboards.time_picker_keyboard(_, hour, minute, cancel)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    return state


def check_order_now_allowed():
    now = datetime.datetime.now()
    res = True
    try:
        working_day = WorkingHours.get(day=now.weekday())
    except WorkingHours.DoesNotExist:
        res = False
    else:
        open_time = now.replace(hour=working_day.open_time.hour, minute=working_day.open_time.minute, second=0)
        close_time = now.replace(hour=working_day.close_time.hour, minute=working_day.close_time.minute, second=0)
        if not open_time <= now < close_time:
            res = False
    return res


def get_order_subquery(action, val, month, year):
    val = int(val)
    query = []
    subquery = Order.date_created.year == year
    query.append(subquery)
    if action == 'year':
        return query
    query.append(Order.date_created.month == month)
    if action == 'day':
        query.append(Order.date_created.day == val)
    return query


def get_order_count_and_price(*subqueries):
    _ = get_channel_trans()
    orders_count = Order.select().where(*subqueries).count()
    total_price = 0
    products_count = {}
    product_text = ''
    count_text = _('count')
    price_text = _('price')
    orders_items = OrderItem.select().join(Order).where(*subqueries)
    for order_item in orders_items:
        total_price += order_item.total_price
        title, count, price = order_item.product.title, order_item.count, order_item.total_price
        try:
            if products_count[title]:
                products_count[title][count_text] += count
                products_count[title][price_text] += price
        except KeyError:
            products_count[title] = {count_text: count, price_text: price}
    for x in products_count:
        product_name = escape(x)
        product_name = '<b>{}</b>'.format(product_name)
        product_text += _('\n Product: ')
        product_text += product_name
        product_text += '\n'
        for y in products_count[x]:
            product_text += y
            product_text += ' = '
            product_text += str(products_count[x][y])
            product_text += '\n'
    return orders_count, total_price, product_text


def check_order_products_credits(order, courier=None):

    for order_item in order.order_items:
        product = order_item.product
        if product.warehouse_active:
            if courier:
                try:
                    warehouse = ProductWarehouse.get(product=product, courier=courier)
                    warehouse_count = warehouse.count
                except ProductWarehouse.DoesNotExist:
                    warehouse_count = 0
                    # warehouse = ProductWarehouse(product=product, courier=courier)
                    # warehouse.save()
            else:
                warehouse_count = product.credits

        product_warehouse = ProductWarehouse.get(product=product)
        product_warehouse_count = product_warehouse.count
        if product_warehouse_count <= 0:
            not_defined = True
            return not_defined


def check_order_products_credits(order, trans, courier=None):
    msg = ''
    first_msg = True
    not_defined = False
    for order_item in order.order_items:
        product = order_item.product
        if courier:
            try:
                warehouse = ProductWarehouse.get(product=product, courier=courier)
                warehouse_count = warehouse.count
            except ProductWarehouse.DoesNotExist:
                warehouse = ProductWarehouse(product=product, courier=courier)
                warehouse.save()
        else:
            warehouse_count = product.credits
        product_warehouse = ProductWarehouse.get(product=product)
        product_warehouse_count = product_warehouse.count
        # if product_warehouse_count <= 0:
        #     not_defined = True
        #     return not_defined
        if order_item.count > warehouse_count:
            _ = trans
            product_title = escape_markdown(product.title.replace('`', ''))
            if courier:
                if first_msg:
                    msg += _('You don\'t have enough credits to deliver products:\n')
                    first_msg = False
                msg += _('Product: `{}`\nCount: {}\nCourier credits: {}\n').format(product_title,
                                                                                   order_item.count,
                                                                                   warehouse_count)
            else:
                if first_msg:
                    msg += _('There are not enough credits in warehouse to deliver products:\n')
                    first_msg = False
                msg += _('Product: `{}`\nCount: {}\nWarehouse credits: {}\n').format(product_title,
                                                                                     order_item.count,
                                                                                     warehouse_count)
    return msg


def change_order_products_credits(order, add=False, courier=None):
    if add:
        op = operator.add
    else:
        op = operator.sub
    for order_item in order.order_items:
        product = order_item.product
        if courier:
            warehouse = ProductWarehouse.get(product=product, courier=courier)
            warehouse.count = op(warehouse.count, order_item.count)
            warehouse.save()
        else:
            product.credits = op(product.credits, order_item.count)
            product.save()


def send_product_media(bot, product, chat_id):
    class_map = {'photo': InputMediaPhoto, 'video': InputMediaVideo}
    media_list = []
    for media in product.product_media:
        media_class = class_map[media.file_type]
        file = media_class(media=media.file_id)
        media_list.append(file)
    messages = bot.send_media_group(chat_id, media_list)
    messages_ids = [msg['message_id'] for msg in messages]
    return messages_ids


def send_products(_, bot, user_data, chat_id, products):
    msgs_ids = []
    for product in products:
        product_id = product.id
        product_count = Cart.get_product_count(user_data, product_id)
        subtotal = Cart.get_product_subtotal(user_data, product_id)
        product_title, prices = get_full_product_info(product_id)
        media_ids = send_product_media(bot, product, chat_id)
        msgs_ids += media_ids
        msg = messages.create_product_description(_, product_title, prices, product_count, subtotal)
        reply_markup = keyboards.create_product_keyboard(_, product_id, user_data)
        msg = bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN, timeout=20)
        msgs_ids.append(msg['message_id'])
    return msgs_ids


def product_inactive(_, bot, user_data, update, product):
    query = update.callback_query
    chat_id = update.effective_chat.id
    msg = _('Sorry, product "{}" is not active now.').format(product.title)
    query.answer(msg)
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
        products = Product.select().where(Product.is_active == True, Product.category == cat)
        if products.exists():
            products_msgs += send_products(_, bot, user_data, chat_id, products)
            user_data['products_msgs'] = products_msgs
        return states.enter_menu(bot, update, user_data)
    else:
        products = Product.select().where(Product.is_active == True)
        if products.exists():
            products_msgs = send_products(_, bot, user_data, chat_id, products)
            user_data['products_msgs'] = products_msgs
        menu_msg_id = user_data['menu_id']
        return states.enter_menu(bot, update, user_data, menu_msg_id)


def send_channel_msg(bot, msg, chat_id, keyboard=None, order=None, parse_mode=ParseMode.MARKDOWN,):
    params = {
        'chat_id': chat_id, 'text': msg, 'parse_mode': parse_mode
    }
    if keyboard:
        params['reply_markup'] = keyboard
    sent_msg = bot.send_message(**params)
    sent_msg_id = str(sent_msg['message_id'])
    ChannelMessageData.create(channel=str(chat_id), msg_id=sent_msg_id, order=order)
    return sent_msg_id


def send_channel_location(bot, chat_id, lat, lng, order=None):
    sent_msg = bot.send_location(chat_id, lat, lng)
    sent_msg_id = str(sent_msg['message_id'])
    ChannelMessageData.create(channel=str(chat_id), msg_id=sent_msg_id, order=order)
    return sent_msg_id


def edit_channel_msg(bot, msg, chat_id, msg_id, keyboard=None, order=None, parse_mode=ParseMode.MARKDOWN):
    params = {
        'chat_id': chat_id, 'message_id': msg_id, 'text': msg, 'parse_mode': parse_mode
    }
    if keyboard:
        params['reply_markup'] = keyboard
    edited_msg = bot.edit_message_text(**params)
    edited_msg_id = str(edited_msg['message_id'])
    chat_id = str(chat_id)
    try:
        msg_data = ChannelMessageData.get(channel=chat_id, msg_id=msg_id)
    except ChannelMessageData.DoesNotExist:
        ChannelMessageData.create(channel=chat_id, msg_id=edited_msg_id, order=order)
    else:
        msg_data.channel = chat_id
        msg_data.msg_id = edited_msg_id
        msg_data.order = order
        msg_data.save()
    return edited_msg_id


def delete_channel_msg(bot, chat_id, msg_id):
    try:
        bot.delete_message(chat_id, msg_id)
    except TelegramError:
        pass
    try:
        msg_row = ChannelMessageData.get(channel=str(chat_id), msg_id=str(msg_id))
    except ChannelMessageData.DoesNotExist:
        pass
    else:
        msg_row.delete_instance()


def send_channel_media_group(bot, chat_id, media, order=None):
    msgs = bot.send_media_group(chat_id, media)
    msgs_ids = [str(msg['message_id']) for msg in msgs]
    chat_id = str(chat_id)
    for msg_id in msgs_ids:
        ChannelMessageData.create(channel=chat_id, msg_id=msg_id, order=order)
    return msgs_ids


def delete_order_channels_msgs(bot, order):
    msgs = ChannelMessageData.select().where(ChannelMessageData.order == order)
    for msg in msgs:
        try:
            bot.delete_message(msg.channel, msg.msg_id)
        except TelegramError:
            pass
        msg.delete_instance()


def get_product_prices_str(trans, product):
    _ = trans
    group_price = product.group_price
    prices_str = _('Current prices:\n')
    if group_price:
        group_name = escape_markdown(group_price.name)
        prices_str += _('Product price group:\n_{}_').format(group_name)
        prices_str += '\n\n'
        product_counts = ProductCount.select().where(ProductCount.product_group == group_price)
    else:
        product_counts = product.product_counts
    for price in product_counts:
        prices_str += _('x {} = ${}\n').format(price.count, price.price)
    return prices_str


def remove_user_registration(user):
    UserIdentificationAnswer.delete().where(UserIdentificationAnswer.user == user).execute()
    user.permission = UserPermission.NOT_REGISTERED
    user.phone_number = None
    user.save()


# def black_list_user(_, bot, user):
#     user.banned = True
#     user.save()
#     user_trans = get_trans(user.telegram_id)
#     msg = user_trans('{}, you have been black-listed').format(user.username)
#     bot.send_message(user.telegram_id, msg)
#     msg = _('*{}* has been added to black-list!').format(username)