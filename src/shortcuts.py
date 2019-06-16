import datetime
from string import ascii_uppercase
import random
import operator
import time
from peewee import JOIN
from pytz import timezone

from telegram import ParseMode, TelegramError, InputMediaPhoto, InputMediaVideo
from telegram.utils.helpers import escape_markdown, escape
from telegram.ext.dispatcher import run_async

from .helpers import config, get_trans, get_channel_trans, get_currency_symbol,\
    get_service_channel
from .btc_wrapper import CurrencyConverter, wallet_enable_hd
from .cart_helper import Cart

from .models import Order, ProductWarehouse, ChannelMessageData, ProductCount, UserPermission, UserIdentificationAnswer, \
    Product, WorkingHours, User, CurrencyRates, BitcoinCredentials, Channel, ChannelPermissions, CourierChatMessage, \
    CourierChat, GroupProductCount, GroupProductCountPermission, ProductGroupCount, UserGroupCount, Lottery, \
    LotteryParticipant, LotteryPermission, Ad, ChannelAd, UserAd
from . import keyboards, messages


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
            content = media_class(media=content, caption=question)
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


def initialize_calendar(_, bot, user_data, chat_id, state, message_id=None, query_id=None, msg=None, cancel=False):
    current_date = datetime.datetime.now()
    il_tz = timezone('Asia/Jerusalem')
    current_date = il_tz.localize(current_date)
    year, month = current_date.year, current_date.month
    try:
        first_date = user_data['calendar']['first_date']
    except KeyError:
        first_date = None
    if not msg:
        msg = _('Pick year, month or day')
    user_data['calendar'] = {'year': year, 'month': month, 'msg': msg, 'cancel': cancel, 'state': state, 'first_date': first_date}
    reply_markup = keyboards.calendar_keyboard(year, month, _, cancel, first_date=first_date)
    if message_id:
        bot.edit_message_text(msg, chat_id, message_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    return state


def initialize_time_picker(_, bot, user_data, chat_id, state, msg_id, query_id, msg, time_range, cancel=False):
    start_time = time_range[0]
    hour, minute = start_time.hour, start_time.minute
    user_data['time_picker'] = {
        'hour': hour, 'minute': minute, 'msg': msg, 'cancel': cancel, 'state': state, 'range': time_range
    }
    reply_markup = keyboards.time_picker_keyboard(_, hour, minute, cancel)
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if query_id:
        bot.answer_callback_query(query_id)
    return state


def check_order_datetime_allowed(dtime):
    res = True
    try:
        working_day = WorkingHours.get(day=dtime.weekday())
    except WorkingHours.DoesNotExist:
        res = False
    else:
        close_time = working_day.close_time
        close_time = datetime.datetime(year=dtime.year, month=dtime.month, day=dtime.day, hour=close_time.hour, minute=close_time.minute)
        close_time = timezone('Asia/Jerusalem').localize(close_time)
        close_time = close_time - datetime.timedelta(minutes=30)
        if not dtime < close_time:
            res = False
    return res


def calculate_delivery_fee(delivery_method, location, total, special_client):
    if delivery_method == Order.DELIVERY:
        if location and location.delivery_fee is not None:
            delivery_fee, delivery_min = location.delivery_fee, location.delivery_min
        else:
            delivery_fee, delivery_min = config.delivery_fee, config.delivery_min
        if total < delivery_min or delivery_min == 0:
            if not special_client:
                return delivery_fee
    return 0


def get_date_subquery(model, first_date=None, second_date=None, year=None, month=None):
    if first_date and second_date:
        query = [model.date_created >= first_date, model.date_created <= second_date]
    elif year and month:
        query = [model.date_created.year == year, model.date_created.month == month]
    elif year:
        query = [model.date_created.year == year]
    else:
        raise ValueError('Incorrect arguments')
    return query


def change_order_products_credits(order, add=False, courier=None):
    if add:
        op = operator.add
    else:
        op = operator.sub
    for order_item in order.order_items:
        product = order_item.product
        if product.warehouse_active:
            if courier:
                warehouse = ProductWarehouse.get(product=product, courier=courier)
                warehouse.count = op(warehouse.count, order_item.count)
                warehouse.save()
            else:
                product.credits = op(product.credits, order_item.count)
                product.save()


@run_async
def check_courier_available(courier_chat_id, bot):
    wait_period = 30 * 60
    refresh_delay = 30
    time_passed = 0
    chat_id = get_service_channel()
    chat = CourierChat.get(id=courier_chat_id)
    order = chat.order
    courier = chat.courier
    _ = get_channel_trans()
    while time_passed != wait_period:
        chat = CourierChat.get(id=courier_chat_id)
        if chat.unresponsible_answer == CourierChat.YES:
            return
        elif chat.unresponsible_answer == CourierChat.NO:
            break
        time.sleep(refresh_delay)
        time_passed += refresh_delay
    msg = _('Order №{}:').format(order.id)
    msg += '\n'
    if chat.unresponsible_answer is None:
        msg += _('Courier don\'t respond for notification for 30 minutes.')
    else:
        msg += _('Something is wrong with courier.')
    msg += '\n'
    msg += _('Courier responsibility dropped.')
    send_channel_msg(bot, msg, chat_id, order=order, parse_mode=None)
    change_order_products_credits(order, True, courier)
    order.courier = None
    order.status = Order.CONFIRMED
    order.save()
    courier_id = courier.telegram_id
    _ = get_trans(courier_id)
    msg = _('Your responsibility for Order №{} has been dropped.').format(order.id)
    bot.send_message(courier_id, msg)


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


def send_products(_, bot, user_data, chat_id, products, user):
    currency = user.currency
    msgs_ids = []
    for product in products:
        product_id = product.id
        product_count = Cart.get_product_count(user_data, product_id)
        price_group = Cart.get_product_price_group(product, user)
        subtotal = Cart.get_product_subtotal(user_data, product, price_group)
        product_title, prices = get_full_product_info(product, price_group)
        media_ids = send_product_media(bot, product, chat_id)
        msgs_ids += media_ids
        msg = messages.create_product_description(_, currency, product_title, prices, product_count, subtotal)
        reply_markup = keyboards.create_product_keyboard(_, product_id, user_data)
        msg = bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN, timeout=20)
        msgs_ids.append(msg['message_id'])
    return msgs_ids


def get_all_product_counts(product):
    if product.price_groups:
        price_groups = [group.price_group for group in product.price_groups]
        counts = ProductCount.select().where(ProductCount.price_group.in_(price_groups))
    else:
        counts = ProductCount.select().where(ProductCount.product == product)
    counts = set([item.count for item in counts])
    counts = list(counts)
    counts.sort()
    return counts


def get_users_products(user, category=None):
    # if user.
    db_query = (
        (UserGroupCount.user == user)
        | ((GroupProductCountPermission.permission == user.permission) & (UserGroupCount.price_group.is_null(True)))
        | ((GroupProductCountPermission.price_group.is_null(True)) & (UserGroupCount.price_group.is_null(True)))
    )
    user_group_prices = GroupProductCount.select().join(GroupProductCountPermission, JOIN.LEFT_OUTER) \
        .switch(GroupProductCount).join(UserGroupCount, JOIN.LEFT_OUTER).where(db_query).group_by(GroupProductCount.id)
    user_group_prices = list(user_group_prices)
    db_query = ((ProductGroupCount.product.is_null(True)) | (ProductGroupCount.price_group.in_(user_group_prices)))
    db_query = [Product.is_active == True, db_query]
    if category:
        db_query.append(Product.category == category)
    products = Product.select().join(ProductGroupCount, JOIN.LEFT_OUTER).where(*db_query).group_by(Product.id)
    print(list(products))
    return products


def get_full_product_info(product, price_group):
    product_title = product.title
    if price_group:
        query = (ProductCount.price_group == price_group)
    else:
        query = (ProductCount.product == product)
    rows = ProductCount.select(ProductCount.count, ProductCount.price).where(query).tuples()
    return product_title, rows


def send_channel_msg(bot, msg, chat_id, keyboard=None, order=None, parse_mode=ParseMode.MARKDOWN,):
    params = {
        'chat_id': chat_id, 'text': msg, 'parse_mode': parse_mode, 'timeout': 20
    }
    if keyboard:
        params['reply_markup'] = keyboard
    sent_msg = bot.send_message(**params)
    sent_msg_id = str(sent_msg['message_id'])
    ChannelMessageData.create(channel=str(chat_id), msg_id=sent_msg_id, order=order)
    return sent_msg_id


def send_channel_photo(bot, photo, chat_id, caption=None, order=None):
    sent_msg = bot.send_photo(chat_id, photo, caption, timeout=20)
    sent_msg_id = str(sent_msg['message_id'])
    ChannelMessageData.create(channel=str(chat_id), msg_id=sent_msg_id, order=order)
    return sent_msg_id


def send_channel_video(bot, video, chat_id, caption=None, order=None):
    sent_msg = bot.send_video(chat_id, video, caption, timeout=20)
    sent_msg_id = str(sent_msg['message_id'])
    ChannelMessageData.create(channel=str(chat_id), msg_id=sent_msg_id, order=order)
    return sent_msg_id


def send_channel_location(bot, chat_id, lat, lng, order=None):
    sent_msg = bot.send_location(chat_id, lat, lng, timeout=20)
    sent_msg_id = str(sent_msg['message_id'])
    ChannelMessageData.create(channel=str(chat_id), msg_id=sent_msg_id, order=order)
    return sent_msg_id


def edit_channel_msg(bot, msg, chat_id, msg_id, keyboard=None, order=None, parse_mode=ParseMode.MARKDOWN):
    params = {
        'chat_id': chat_id, 'message_id': msg_id, 'text': msg, 'parse_mode': parse_mode, 'timeout': 20
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
        bot.delete_message(chat_id, msg_id, timeout=20)
    except TelegramError:
        pass
    try:
        msg_row = ChannelMessageData.get(channel=str(chat_id), msg_id=str(msg_id))
    except ChannelMessageData.DoesNotExist:
        pass
    else:
        msg_row.delete_instance()


def send_channel_media_group(bot, chat_id, media, order=None):
    msgs = bot.send_media_group(chat_id, media, timeout=20)
    msgs_ids = [str(msg['message_id']) for msg in msgs]
    chat_id = str(chat_id)
    for msg_id in msgs_ids:
        ChannelMessageData.create(channel=chat_id, msg_id=msg_id, order=order)
    return msgs_ids


def delete_order_channels_msgs(bot, order):
    msgs = ChannelMessageData.select().where(ChannelMessageData.order == order)
    for msg in msgs:
        try:
            bot.delete_message(msg.channel, msg.msg_id, timeout=20)
        except TelegramError:
            pass
        msg.delete_instance()


def get_product_prices_str(_, product):
    currency = get_currency_symbol()
    price_groups = product.price_groups
    prices_str = _('Current prices:\n')
    if price_groups:
        for group in price_groups:
            group = group.price_group
            group_name = escape_markdown(group.name)
            prices_str += _('Product price group:\n_{}_').format(group_name)
            prices_str += '\n'
            product_counts = ProductCount.select(ProductCount.count, ProductCount.price)\
                .where(ProductCount.price_group == group).tuples()
            for count, price in product_counts:
                prices_str += _('x {} = {}{}\n').format(count, price, currency)
            prices_str += '\n\n'
    else:
        for product_count in product.product_counts:
            prices_str += _('x {} = {}{}\n').format(product_count.count, product_count.price, currency)
    return prices_str


def remove_user_registration(user):
    UserIdentificationAnswer.delete().where(UserIdentificationAnswer.user == user).execute()
    user.permission = UserPermission.NOT_REGISTERED
    user.phone_number = None
    user.save()


def init_bot_tables():
    for perm, _ in UserPermission.PERMISSIONS:
        try:
            UserPermission.get(permission=perm)
        except UserPermission.DoesNotExist:
            UserPermission.create(permission=perm)

    owner_id = config.owner_id
    if owner_id is None:
        raise AssertionError('Please set Owner ID in config file before starting the bot.')
    try:
        User.get(telegram_id=owner_id)
    except User.DoesNotExist:
        owner_perm = UserPermission.get(permission=UserPermission.OWNER)
        User.create(telegram_id=owner_id, permission=owner_perm)

    btc_creds = BitcoinCredentials.select().first()
    if not btc_creds:
        BitcoinCredentials.create()

    channels_map = {
        'reviews_channel': {'name': 'Reviews channel', 'perms': (1, 2, 3, 4, 5, 6, 7, 8)},
        'service_channel': {'name': 'Service channel', 'perms': (1, 2)},
        'customers_channel': {'name': 'Customers channel', 'perms': (1, 2, 4, 5, 6, 7, 8)},
        'vip_customers_channel': {'name': 'Vip customers channel', 'perms': (1, 2, 7)},
        'couriers_channel': {'name': 'Couriers channel', 'perms': (1, 2, 3)}
    }
    currencies_query = CurrencyRates.select()
    if not currencies_query.exists():
        CurrencyConverter.fetch_update_currencies()
        if not currencies_query.exists():
            raise AssertionError('Couldn\'t fetch currencies from "apilayer" API')
    for conf_name, data in channels_map.items():
        try:
            Channel.get(conf_name=conf_name)
        except Channel.DoesNotExist:
            name = data['name']
            perms = data['perms']
            conf_id = conf_name + '_id'
            conf_link = conf_name + '_link'
            channel_id = config.get_config_value(conf_id)
            channel_link = config.get_config_value(conf_link)
            if not channel_link or not channel_id:
                raise AssertionError('Please specify both "{}" and "{}" config values'.format(conf_id, conf_link))
            channel = Channel.create(name=name, channel_id=channel_id, link=channel_link, conf_name=conf_name)
            for val in perms:
                perm = UserPermission.get(permission=val)
                ChannelPermissions.create(channel=channel, permission=perm)


def check_btc_status(_, wallet_id, password):
    if not wallet_id or not password:
        msg = _('Please set BTC wallet ID and password.')
    else:
        msg, success = wallet_enable_hd(_, wallet_id, password)
        if success or msg.lower().startswith('current wallet is already an hd wallet'):
            msg = None
    return msg


def send_chat_msg(_, bot, db_msg, chat_id, msg_id=None, read=False):
    msg = db_msg.message
    msg_type = db_msg.msg_type
    if msg_type in (CourierChatMessage.VIDEO, CourierChatMessage.PHOTO):
        if read:
            caption = '✅'
            sent_id = bot.edit_message_caption(chat_id, msg_id, caption=caption)
        else:
            if msg_type == CourierChatMessage.VIDEO:
                sent_id = bot.send_video(chat_id, msg)
            else:
                sent_id = bot.send_photo(chat_id, msg)
    else:
        if read:
            msg += '\n'
            msg += '✅'
        if msg_id:
            sent_id = bot.edit_message_text(msg, chat_id, msg_id)
        else:
            sent_id = bot.send_message(chat_id, msg, msg_id)
    db_msg.sent_msg_id = sent_id
    db_msg.read = True
    db_msg.save()


def generate_lottery_code(all_codes):
    while True:
        new_code = random.choices(ascii_uppercase, k=5)
        new_code = ''.join(new_code)
        if new_code not in all_codes:
            return new_code


@run_async
def manage_lottery_participants(bot):
    try:
        lottery = Lottery.get(completed_date=None)
    except Lottery.DoesNotExist:
        return
    while not lottery.completed_date:
        tickets = LotteryParticipant.select() \
            .where(LotteryParticipant.is_pending == False, LotteryParticipant.lottery == lottery)
        tickets_used = tickets.count()
        tickets_diff = lottery.num_tickets - tickets_used
        if tickets_diff:
            try:
                pending_participant = LotteryParticipant.select().where(LotteryParticipant.is_pending == True) \
                    .order_by(LotteryParticipant.created_date.asc()).get()
            except LotteryParticipant.DoesNotExist:
                pass
            else:
                LotteryParticipant.update({LotteryParticipant.lottery: lottery, LotteryParticipant.is_pending: False}) \
                    .where(LotteryParticipant.id == pending_participant.id).execute()
                all_codes = [ticket.code for ticket in tickets if ticket.code]
                code = generate_lottery_code(all_codes)
                pending_participant.code = code
                pending_participant.save()
                user = pending_participant.user
                _ = get_trans(user.telegram_id)
                msg = _('{}, you have been added to lottery №{}').format(user.username, lottery.id)
                msg += '\n'
                msg += _('Lottery code: {}').format(code)
                bot.send_message(user.user_id, msg)
                continue

        time.sleep(15)
        lottery = Lottery.get(id=lottery.id)


@run_async
def send_lottery_messages(bot):
    while config.lottery_messages:
        last_sent_date = config.lottery_messages_sent
        if last_sent_date:
            now = datetime.datetime.now()
            il_tz = timezone('Asia/Jerusalem')
            now = il_tz.localize(now)
            interval = datetime.timedelta(hours=config.lottery_messages_interval)
            time_remains = (last_sent_date + interval) - now
            if time_remains.days >= 0:
                time.sleep(time_remains.total_seconds())
            if not config.lottery_messages:
                break
        permissions = UserPermission.get_clients_permissions()
        channels_skip = ('service_channel', 'couriers_channel', 'reviews_channel')
        channels = Channel.select().join(ChannelPermissions, JOIN.LEFT_OUTER)\
            .where(ChannelPermissions.permission.in_(permissions), Channel.conf_name.not_in(channels_skip))\
            .group_by(Channel.id)
        _ = get_channel_trans()
        for channel in channels:
            channel_permissions = [item.permission for item in channel.permissions]
            completed_lottery = Lottery.select().join(LotteryPermission)\
                .where(Lottery.completed_date.is_null(False), LotteryPermission.permission.in_(channel_permissions))
            if completed_lottery.exists():
                completed_lottery = completed_lottery.get()
                msg = messages.create_completed_lottery_channel_msg(_, completed_lottery)
                bot.send_message(channel.channel_id, msg, parse_mode=ParseMode.MARKDOWN, timeout=20)
        active_lottery = Lottery.select().where(Lottery.completed_date == None, Lottery.active == True)
        if active_lottery.exists():
            active_lottery = active_lottery.get()
            lottery_permissions = [item.permission for item in active_lottery.permissions]
            channels = Channel.select().join(ChannelPermissions, JOIN.LEFT_OUTER)\
                .where(Channel.conf_name.not_in(channels_skip), ChannelPermissions.permission.in_(lottery_permissions))\
                .group_by(Channel.id)
            for channel in channels:
                msg = messages.create_lottery_channel_msg(_, active_lottery)
                bot.send_message(channel.channel_id, msg, parse_mode=ParseMode.MARKDOWN, timeout=20)
        now = datetime.datetime.now()
        il_tz = timezone('Asia/Jerusalem')
        now = il_tz.localize(now)
        config.set_datetime_value('lottery_messages_sent', now)


@run_async
def send_channel_advertisments(bot):

    def send_ad(ad):
        channels = Channel.select().join(ChannelAd, JOIN.LEFT_OUTER).where(ChannelAd.ad == ad)
        users = User.select().join(UserAd, JOIN.LEFT_OUTER).where(UserAd.ad == ad)
        chats_ids = [channel.channel_id for channel in channels] + [user.telegram_id for user in users]
        for chat_id in chats_ids:
            func = getattr(bot, 'send_{}'.format(ad.media_type))
            func(chat_id, ad.media, caption=ad.text)
        now = datetime.datetime.now()
        il_tz = timezone('Asia/Jerusalem')
        now = il_tz.localize(now)
        ad.last_sent_date = now
        ad.save()

    while True:
        ads = Ad.select()
        if ads.exists():
            ads_to_send = []
            for ad in ads:
                if ad.last_sent_date:
                    now = datetime.datetime.now()
                    il_tz = timezone('Asia/Jerusalem')
                    now = il_tz.localize(now)
                    interval = datetime.timedelta(hours=ad.interval)
                    last_sent, offset = ad.last_sent_date.split('+')
                    offset = '+' + offset.replace(':', '')
                    last_sent += offset
                    last_sent = datetime.datetime.strptime(last_sent, '%Y-%m-%d %H:%M:%S.%f%z')
                    time_remains = (last_sent + interval) - now
                    if time_remains.days >= 0:
                        ads_to_send.append((ad, time_remains))
                        continue
                send_ad(ad)
            if ads_to_send:
                ad, time_remains = min(ads_to_send, key=lambda x: x[1])
                time.sleep(time_remains.total_seconds())
                send_ad(ad)
        else:
            break


def check_lottery_available(order):
    try:
        lottery = Lottery.get(completed_date=None, active=True)
    except Lottery.DoesNotExist:
        return
    lottery_permissions = [item.permission for item in lottery.permissions]
    if not order.user.permission in lottery_permissions:
        return
    is_participant = LotteryParticipant.select() \
        .where(LotteryParticipant.lottery == lottery, LotteryParticipant.participant == order.user).exists()
    if is_participant:
        return
    if lottery.products_condition in (Lottery.SINGLE_PRODUCT, Lottery.CATEGORY):
        order_products = [order_item.product for order_item in order.order_items]
        if lottery.products_condition == Lottery.SINGLE_PRODUCT:
            if lottery.single_product_condition not in order_products:
                return
        else:
            order_categories = [product.category for product in order_products]
            if lottery.category_condition not in order_categories:
                return
        if lottery.by_condition == Lottery.PRICE:
            if order.total_cost < lottery.min_price:
                return
    return True


def add_client_to_lottery(lottery, user, all_codes, is_pending=False):
    code = generate_lottery_code(all_codes)
    LotteryParticipant.create(lottery=lottery, participant=user, code=code, is_pending=is_pending)
    user_trans = get_trans(user.telegram_id)
    msg = user_trans('{}, you have been added to lottery №{}').format(user.username, lottery.id)
    msg += '\n'
    msg += user_trans('Lottery code: {}').format(code)
    return code, msg


