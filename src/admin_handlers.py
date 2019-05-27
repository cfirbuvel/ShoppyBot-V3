from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import random

from telegram import ParseMode
from telegram import ReplyKeyboardRemove
from telegram.error import TelegramError
from telegram.utils.helpers import escape_markdown, escape
from peewee import fn, JOIN

from . import enums, keyboards, shortcuts, messages, states
from .btc_wrapper import CurrencyConverter
from .decorators import user_passes, user_allowed
from .btc_processor import process_btc_payment, set_btc_proc
from .helpers import get_user_id, config, get_trans, parse_discount, get_channel_trans, fix_markdown, \
    get_service_channel, get_currency_symbol, get_reviews_channel
from .models import Product, ProductCount, Location, ProductWarehouse, User, \
    ProductMedia, ProductCategory, IdentificationStage, Order, IdentificationQuestion, \
    ChannelMessageData, GroupProductCount, delete_db, create_tables, Currencies, BitcoinCredentials, \
    Channel, UserPermission, ChannelPermissions, CourierLocation, WorkingHours, GroupProductCountPermission, \
    OrderBtcPayment, CurrencyRates, BtcProc, OrderItem, IdentificationPermission, Lottery, LotteryParticipant, \
    LotteryPermission, ProductGroupCount, UserGroupCount, Review, ReviewQuestion, Ad, ChannelAd, AllowedSetting


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
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS
    elif data == 'settings_bot':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    elif data == 'settings_users':
        return states.enter_settings_users(_, bot, chat_id, user_id, msg_id, query.id)
    elif data == 'settings_reviews':
        msg = _('⭐️ Reviews')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_settings_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS
    elif data == 'settings_back':
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'reviews_pending':
        reviews = Review.select().where(Review.is_pending == True).order_by(Review.date_created.desc())
        reviews = [(_('Review №{} - @{}').format(review.id, review.user.username), review.id) for review in reviews]
        user_data['listing_page'] = 1
        msg = _('Please select a review:')
        reply_markup = keyboards.general_select_one_keyboard(_, reviews)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_PENDING
    elif action == 'reviews_show':
        msg = _('🌠 Show reviews')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_show_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS_SHOW
    elif action == 'reviews_questions':
        msg = _('🧾 Reviews questions')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_questions_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS_QUESTIONS
    else:
        user = User.get(telegram_id=user_id)
        msg = _('⚙️ Settings')
        if user.is_logistic_manager:
            reply_markup = keyboards.settings_logistic_manager_keyboard(_, user.allowed_settings_list)
        else:
            reply_markup = keyboards.settings_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_MENU
        # return states.enter_settings(_, bot, chat_id, user_id, query_id=query.id, msg_id=msg_id)


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_pending(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        reviews = Review.select().where(Review.is_pending == True).order_by(Review.date_created.desc())
        reviews = [(_('Review №{} - @{}').format(review.id, review.user.username), review.id) for review in reviews]
        user_data['listing_page'] = page
        msg = _('Please select a review:')
        reply_markup = keyboards.general_select_one_keyboard(_, reviews, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_PENDING
    elif action == 'select':
        val = int(val)
        review = Review.get(id=val)
        user_data['pending_review_id'] = val
        msg = messages.create_review_msg(_, review)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_pending_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS_PENDING_SELECT
    else:
        del user_data['listing_page']
        msg = _('⭐️ Reviews')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_settings_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_pending_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('reviews_approve', 'reviews_back', 'reviews_decline'):
        if action == 'reviews_approve':
            review_id = user_data['pending_review_id']
            review = Review.get(id=review_id)
            review_msg = messages.create_review_msg(get_channel_trans(), review)
            bot.send_message(get_reviews_channel(), review_msg, timeout=20)
            review.is_pending = False
            review.save()
            client = review.user
            client_trans = get_trans(client.telegram_id)
            msg = client_trans('@{}, your review for Order №{} has been approved!').format(client.username,
                                                                                           review.order.id)
            bot.send_message(client.telegram_id, msg, reply_markup=keyboards.reviews_channel_button(client_trans), timeout=20)
            msg = _('Review №{} has been approved').format(review.id)
        elif action == 'reviews_decline':
            review_id = user_data['pending_review_id']
            review = Review.get(review_id)
            client = review.user
            client_trans = get_trans(client.telegram_id)
            msg = client_trans('@{}, your review for Order №{} has been declined!').format(client.username,
                                                                                           review.order.id)
            bot.send_message(client.telegram_id, msg, timeout=20)
            msg = _('Review №{} has been declined').format(review.id)
            review.delete_instance()
        else:
            msg = _('Please select a review:')
        reviews = Review.select().where(Review.is_pending == True).order_by(Review.date_created.desc())
        reviews = [(_('Review №{} - @{}').format(review.id, review.user.username), review.id) for review in reviews]
        page = user_data['listing_page']
        reply_markup = keyboards.general_select_one_keyboard(_, reviews, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_PENDING


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_show(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'reviews_date':
        state = enums.ADMIN_REVIEWS_BY_DATE
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
    elif action == 'reviews_client':
        if config.order_non_registered:
            permissions = UserPermission.get_users_permissions()
        else:
            permissions = UserPermission.get_clients_permissions()
        permissions = [(item.get_permission_display(), item.id) for item in permissions]
        msg = _('Please select clients group')
        reply_markup = keyboards.general_select_one_keyboard(_, permissions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_CLIENT_PERMISSIONS
    else:
        msg = _('⭐️ Reviews')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_settings_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_by_date(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('year', 'month', 'day'):
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.ADMIN_REVIEWS_BY_DATE
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.ADMIN_REVIEWS_BY_DATE
                date_query = shortcuts.get_date_subquery(Review, first_date=first_date, second_date=second_date)
                user_data['reviews_by_date'] = {'first_date': first_date, 'second_date': second_date}
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Review, year=year)
            user_data['reviews_by_date'] = {'year': year}
        else:
            date_query = shortcuts.get_date_subquery(Review, month=month, year=year)
            user_data['reviews_by_date'] = {'year': year, 'month': month}
        reviews = Review.select().where(Review.is_pending == False, *date_query).order_by(Review.date_created.desc())
        reviews = [(_('Review №{}, {}').format(item.id, item.date_created.strftime('%d %b, %Y')), item.id) for item in reviews]
        user_data['listing_page'] = 1
        msg = _('Please select a review')
        reply_markup = keyboards.general_select_one_keyboard(_, reviews)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_DATE_SELECT
    else:
        del user_data['calendar']
        msg = _('🌠 Show reviews')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_show_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS_SHOW


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_by_date_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('page', 'select'):
        if action == 'page':
            page = int(val)
            user_data['listing_page'] = page
            msg = _('Please select a review')
        else:
            page = user_data['listing_page']
            review = Review.get(id=val)
            msg = messages.create_review_msg(_, review)
        date_query = shortcuts.get_date_subquery(Review, **user_data['reviews_by_date'])
        reviews = Review.select().where(Review.is_pending == False, *date_query).order_by(Review.date_created.desc())
        reviews = [(_('Review №{}, {}').format(item.id, item.date_created.strftime('%d %b, %Y')), item.id) for item in
                   reviews]
        reply_markup = keyboards.general_select_one_keyboard(_, reviews, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_DATE_SELECT
    else:
        del user_data['calendar']
        state = enums.ADMIN_REVIEWS_BY_DATE
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_by_client_permissions(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        val = int(val)
        permission = UserPermission.get(id=val)
        users = User.select(User.username, User.id).where(User.permission == permission).tuples()
        user_data['reviews_permission'] = val
        user_data['listing_page'] = 1
        msg = _('Please select a client')
        reply_markup = keyboards.general_select_one_keyboard(_, users)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_CLIENT
    else:
        msg = _('🌠 Show reviews')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_show_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS_SHOW


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_by_client(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        perm_id = user_data['reviews_permission']
        permission = UserPermission.get(id=perm_id)
        users = User.select(User.username, User.id).where(User.permission == permission).tuples()
        msg = _('Please select a client')
        reply_markup = keyboards.general_select_one_keyboard(_, users)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_CLIENT
    elif action == 'select':
        user = User.get(id=val)
        user_data['reviews_user'] = val
        reviews = Review.select().where(Review.is_pending == False, Review.user == user).order_by(Review.date_created.desc())
        reviews = [(_('Review №{}, {}').format(item.id, item.date_created.strftime('%d %b, %Y')), item.id) for item in
                   reviews]
        user_data['listing_page_level_two'] = 1
        msg = _('User\'s @{} reviews:').format(user.username)
        reply_markup = keyboards.general_select_one_keyboard(_, reviews)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_CLIENT_LIST
    else:
        if config.order_non_registered:
            permissions = UserPermission.get_users_permissions()
        else:
            permissions = UserPermission.get_clients_permissions()
        permissions = [(item.get_permission_display(), item.id) for item in permissions]
        msg = _('Please select clients group')
        reply_markup = keyboards.general_select_one_keyboard(_, permissions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_CLIENT_PERMISSIONS


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_by_client_list(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('page', 'select'):
        user = User.get(id=user_data['reviews_user'])
        if action == 'page':
            page = int(val)
            user_data['listing_page_level_two'] = page
            msg = _('User\'s @{} reviews:').format(user.username)
        else:
            page = user_data['listing_page_level_two']
            review = Review.get(id=val)
            msg = messages.create_review_msg(_, review)
        reviews = Review.select().where(Review.is_pending == False, Review.user == user).order_by(
            Review.date_created.desc())
        reviews = [(_('Review №{}, {}').format(item.id, item.date_created.strftime('%d %b, %Y')), item.id) for item in
                   reviews]
        reply_markup = keyboards.general_select_one_keyboard(_, reviews, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_CLIENT_LIST
    else:
        perm_id = user_data['reviews_permission']
        permission = UserPermission.get(id=perm_id)
        users = User.select(User.username, User.id).where(User.permission == permission).tuples()
        msg = _('Please select a client')
        reply_markup = keyboards.general_select_one_keyboard(_, users, user_data['listing_page'])
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_BY_CLIENT


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_questions(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'reviews_add':
        msg = _('Please enter new question text')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.ADMIN_REVIEWS_QUESTIONS_NEW
    elif action == 'reviews_list':
        questions = ReviewQuestion.select(ReviewQuestion.text, ReviewQuestion.id).tuples()
        msg = _('Select a question')
        reply_markup = keyboards.general_select_one_keyboard(_, questions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_QUESTIONS_LIST
    else:
        msg = _('⭐️ Reviews')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.reviews_settings_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_questions_new(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query:
        msg = _('🧾 Reviews questions')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=keyboards.reviews_questions_keyboard(_))
        query.answer()
    else:
        text = update.message.text
        ReviewQuestion.create(text=text)
        msg = _('New question has been created')
        bot.send_message(chat_id, msg, reply_markup=keyboards.reviews_questions_keyboard(_))
    return enums.ADMIN_REVIEWS_QUESTIONS


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_questions_list(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        val = int(val)
        question = ReviewQuestion.get(id=val)
        user_data['review_question_id'] = val
        msg = _('Review question:')
        msg += '\n'
        msg += question.text
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.delete_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS_QUESTIONS_SELECT
    else:
        msg = _('🧾 Reviews questions')
        bot.edit_message_text(msg, chat_id, query.message.message_id,
                              reply_markup=keyboards.reviews_questions_keyboard(_))
        query.answer()
        return enums.ADMIN_REVIEWS_QUESTIONS


@user_allowed(AllowedSetting.REVIEWS)
@user_passes
def on_reviews_questions_select(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('delete', 'back'):
        if action == 'delete':
            q_id = user_data['review_question_id']
            question = ReviewQuestion.get(id=q_id)
            question.delete_instance()
            msg = _('Question has been deleted')
        else:
            msg = _('Select a question')
        questions = ReviewQuestion.select(ReviewQuestion.text, ReviewQuestion.id).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, questions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REVIEWS_QUESTIONS_LIST


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_menu(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        user = User.get(telegram_id=user_id)
        if user.is_logistic_manager:
            reply_markup = keyboards.settings_logistic_manager_keyboard(_, user.allowed_settings_list)
        else:
            reply_markup = keyboards.settings_keyboard(_)
        bot.edit_message_text(_('⚙️ Settings'), chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_MENU
    elif action == 'stats_general':
        state = enums.ADMIN_STATISTICS_GENERAL
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state
    elif action == 'stats_courier':
        couriers = User.select(User.username, User.id).join(UserPermission)\
            .where(User.banned == False, UserPermission.permission == UserPermission.COURIER).tuples()
        msg = _('Select a courier:')
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, couriers)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS_COURIERS
    elif action == 'stats_locations':
        locations = Location.select(Location.title, Location.id)
        if not locations.exists():
            msg = _('You don\'t have locations')
            query.answer(text=msg, show_alert=True)
            return enums.ADMIN_STATISTICS
        else:
            locations = locations.tuples()
            user_data['listing_page'] = 1
            reply_markup = keyboards.general_select_one_keyboard(_, locations)
            msg = _('Select location:')
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text=msg, reply_markup=reply_markup)
            query.answer()
            return enums.ADMIN_STATISTICS_LOCATIONS
    elif action == 'stats_users':
        msg = _('🌝 Statistics by users')
        reply_markup = keyboards.statistics_users(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS_USERS


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_general(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        bot.edit_message_text(chat_id=chat_id,
                              message_id=msg_id,
                              text=_('📈 Statistics'),
                              reply_markup=keyboards.statistics_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS
    elif action in ('day', 'year', 'month'):
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.ADMIN_STATISTICS_GENERAL
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.ADMIN_STATISTICS_GENERAL
                date_query = shortcuts.get_date_subquery(Order, first_date=first_date, second_date=second_date)
                user_data['stats_date'] = {'first_date': first_date, 'second_date': second_date}
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Order, year=year)
            user_data['stats_date'] = {'year': year}
        else:
            date_query = shortcuts.get_date_subquery(Order, month=month, year=year)
            user_data['stats_date'] = {'month': month, 'year': year}
        orders = Order.select().where(Order.status == Order.DELIVERED, *date_query)
        cancelled_orders = Order.select().where(Order.status == Order.CANCELLED, *date_query)
        msg = _('✅ *Total confirmed orders*')
        msg += messages.create_statistics_msg(_, orders)
        msg += '\n\n'
        msg += _('❌ *Total canceled orders*')
        msg += messages.create_statistics_msg(_, cancelled_orders)
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)), *date_query)\
            .order_by(Order.date_created.desc())
        date_format = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in orders]
        user_data['order_listing_page'] = 1
        user_data['stats_msg'] = msg
        reply_markup = keyboards.general_select_one_keyboard(_, orders)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_GENERAL_ORDER_SELECT
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_general_order_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('page', 'select'):
        date_query = shortcuts.get_date_subquery(Order, **user_data['stats_date'])
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)), *date_query) \
            .order_by(Order.date_created.desc())
        date_format = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in
                  orders]
        if action == 'page':
            page = int(val)
            user_data['order_listing_page'] = page
            msg = user_data['stats_msg']
        else:
            page = user_data['order_listing_page']
            order = Order.get(id=val)
            try:
                btc_data = OrderBtcPayment.get(order=order)
            except OrderBtcPayment.DoesNotExist:
                btc_data = None
            msg = messages.create_service_notice(_, order, btc_data)
            user_data['stats_msg'] = msg
        reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_GENERAL_ORDER_SELECT
    else:
        del user_data['order_listing_page']
        del user_data['calendar']
        state = enums.ADMIN_STATISTICS_GENERAL
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_courier_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        del user_data['listing_page']
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=_('📈 Statistics'),
                              reply_markup=keyboards.statistics_keyboard(_))
        query.answer()
        return enums.ADMIN_STATISTICS
    elif action == 'page':
        current_page = int(val)
        user_data['listing_page'] = current_page
        couriers = User.select(User.username, User.id).join(UserPermission)\
            .where(User.banned == False, UserPermission.permission == UserPermission.COURIER).tuples()
        msg = _('Select a courier:')
        reply_markup = keyboards.general_select_one_keyboard(_, couriers, current_page)
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=msg,
                              reply_markup=reply_markup,
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_COURIERS
    else:
        user_data['stats_item_id'] = val
        state = enums.ADMIN_STATISTICS_COURIERS_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_couriers(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        msg = _('Select a courier:')
        page = user_data['listing_page']
        couriers = User.select(User.username, User.id).join(UserPermission) \
            .where(User.banned == False, UserPermission.permission == UserPermission.COURIER).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, couriers, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS_COURIERS
    else:
        courier_id = user_data['stats_item_id']
        courier = User.get(id=courier_id)
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.ADMIN_STATISTICS_COURIERS_DATE
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.ADMIN_STATISTICS_COURIERS_DATE
                date_query = shortcuts.get_date_subquery(Order, first_date=first_date, second_date=second_date)
                user_data['stats_date'] = {'first_date': first_date, 'second_date': second_date}
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Order, year=year)
            user_data['stats_date'] = {'year': year}
        else:
            date_query = shortcuts.get_date_subquery(Order, month=month, year=year)
            user_data['stats_date'] = {'month': month, 'year': year}
        orders = Order.select().where(Order.status == Order.DELIVERED, Order.courier == courier, *date_query)
        courier_username = escape_markdown(courier.username)
        msg = _('*✅ Total confirmed orders for Courier* @{}').format(courier_username)
        msg += messages.create_statistics_msg(_, orders)
        msg += '\n'
        msg += '〰〰〰〰〰〰〰〰〰〰〰〰️'
        msg += '\n'
        msg += _('*Courier warehouse:*')
        msg += '\n'
        for product in Product.select():
            try:
                count = ProductWarehouse.get(product=product, courier=courier).count
            except ProductWarehouse.DoesNotExist:
                count = 0
            msg += '\n'
            msg += '{}: {} credits'.format(product.title, count)
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)), Order.courier == courier,
                                      *date_query).order_by(Order.date_created.desc())
        user_data['stats_item_id'] = courier_id
        user_data['stats_msg'] = msg
        date_format = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in
                  orders]
        user_data['order_listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, orders)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_COURIER_ORDER_SELECT


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_courier_order_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('page', 'select'):
        date_query = shortcuts.get_date_subquery(Order, **user_data['stats_date'])
        courier_id = user_data['stats_item_id']
        courier = User.get(id=courier_id)
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)),
                                      Order.courier == courier, *date_query).order_by(Order.date_created.desc())
        date_format = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in
                  orders]
        if action == 'page':
            page = int(val)
            user_data['order_listing_page'] = page
            msg = user_data['stats_msg']
        else:
            page = user_data['order_listing_page']
            order = Order.get(id=val)
            try:
                btc_data = OrderBtcPayment.get(order=order)
            except OrderBtcPayment.DoesNotExist:
                btc_data = None
            msg = messages.create_service_notice(_, order, btc_data)
            user_data['stats_msg'] = msg
        reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_COURIER_ORDER_SELECT
    else:
        del user_data['calendar']
        state = enums.ADMIN_STATISTICS_COURIERS_DATE
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_locations_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        del user_data['listing_page']
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=_('📈 Statistics'),
                              reply_markup=keyboards.statistics_keyboard(_))
        query.answer()
        return enums.ADMIN_STATISTICS
    elif action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        locations = Location.select(Location.title, Location.id).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, locations, page)
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=_('Select location:'),
                              reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS_LOCATIONS
    else:
        user_data['stats_item_id'] = val
        state = enums.ADMIN_STATISTICS_LOCATIONS_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_locations(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('day', 'month', 'year'):
        location_id = user_data['stats_item_id']
        location = Location.get(id=location_id)
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.ADMIN_STATISTICS_LOCATIONS_DATE
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.ADMIN_STATISTICS_LOCATIONS_DATE
                date_query = shortcuts.get_date_subquery(Order, first_date=first_date, second_date=second_date)
                user_data['stats_date'] = {'first_date': first_date, 'second_date': second_date}
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Order, year=year)
            user_data['stats_date'] = {'year': year}
        else:
            date_query = shortcuts.get_date_subquery(Order, month=month, year=year)
            user_data['stats_date'] = {'month': month, 'year': year}
        orders = Order.select().where(Order.status == Order.DELIVERED,
                                      Order.location == location, *date_query)
        location_title = escape_markdown(location.title)
        msg = _('✅ *Total confirmed orders for Location* `{}`').format(
            location_title)
        msg += messages.create_statistics_msg(_, orders)
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)),
                                      Order.location == location, *date_query).order_by(Order.date_created.desc())
        date_format = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in
                  orders]
        user_data['stats_item_id'] = location_id
        user_data['stats_msg'] = msg
        user_data['order_listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, orders)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_LOCATION_ORDER_SELECT
    else:
        msg = _('Select location:')
        locations = Location.select(Location.title, Location.id).tuples()
        page = user_data['listing_page']
        reply_markup = keyboards.general_select_one_keyboard(_, locations, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_LOCATIONS


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_locations_order_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('select', 'page'):
        date_query = shortcuts.get_date_subquery(Order, **user_data['stats_date'])
        loc_id = user_data['stats_item_id']
        location = Location.get(id=loc_id)
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)),
                                      Order.location == location, *date_query).order_by(Order.date_created.desc())
        date_format = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in
                  orders]
        if action == 'page':
            page = int(val)
            user_data['order_listing_page'] = page
            msg = user_data['stats_msg']
        else:
            page = user_data['order_listing_page']
            order = Order.get(id=val)
            try:
                btc_data = OrderBtcPayment.get(order=order)
            except OrderBtcPayment.DoesNotExist:
                btc_data = None
            msg = messages.create_service_notice(_, order, btc_data)
            user_data['stats_msg'] = msg
        reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_LOCATION_ORDER_SELECT
    else:
        del user_data['calendar']
        state = enums.ADMIN_STATISTICS_LOCATIONS_DATE
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_users(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'back':
        msg = _('📈 Statistics')
        bot.edit_message_text(msg, chat_id, msg_id,
                              reply_markup=keyboards.statistics_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS
    elif action == 'clients_top':
        msg = _('🥇 Top clients')
        reply_markup = keyboards.top_clients_stats_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS_TOP_CLIENTS
    elif action == 'clients_all':
        user_data['listing_page'] = 1
        return states.enter_statistics_user_select(_, bot, chat_id, msg_id, query.id)


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_user_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'back':
        del user_data['listing_page']
        msg = _('🌝 Statistics by users')
        reply_markup = keyboards.statistics_users(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_STATISTICS_USERS
    elif action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_statistics_user_select(_, bot, chat_id, msg_id, query.id, page)
    else:
        user_data['stats_item_id'] = val
        state = enums.ADMIN_STATISTICS_USER_SELECT_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_user_select_date(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('day', 'year', 'month'):
        user_id = user_data['stats_item_id']
        user = User.get(id=user_id)
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.ADMIN_STATISTICS_USER_SELECT_DATE
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.ADMIN_STATISTICS_USER_SELECT_DATE
                date_query = shortcuts.get_date_subquery(Order, first_date=first_date, second_date=second_date)
                user_data['stats_date'] = {'first_date': first_date, 'second_date': second_date}
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Order, year=year)
            user_data['stats_date'] = {'year': year}
        else:
            date_query = shortcuts.get_date_subquery(Order, month=month, year=year)
            user_data['stats_date'] = {'month': month, 'year': year}
        confirmed_orders = Order.select().where(Order.status == Order.DELIVERED,
                                      Order.user == user, *date_query)
        cancelled_orders = Order.select().where(Order.status == Order.CANCELLED,Order.user == user, *date_query)
        username = escape_markdown(user.username)
        msg = _('✅ *Total confirmed orders for client* @{}').format(username)
        msg += messages.create_statistics_msg(_, confirmed_orders)
        msg += '\n\n'
        msg += _('❌ *Total canceled orders for client* @{}').format(username)
        msg += messages.create_statistics_msg(_, cancelled_orders)
        date_format = '%d-%m-%Y'
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)),
                                      Order.user == user, *date_query)
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in
                  orders]
        user_data['stats_item_id'] = user_id
        user_data['stats_msg'] = msg
        user_data['order_listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, orders)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_USER_ORDER_SELECT
    else:
        page = user_data['listing_page']
        return states.enter_statistics_user_select(_, bot, chat_id, msg_id, query.id, page)


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_user_order_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('page', 'select'):
        date_query = shortcuts.get_date_subquery(Order, **user_data['stats_date'])
        user_id = user_data['stats_item_id']
        user = User.get(id=user_id)
        orders = Order.select().where(Order.status.in_((Order.DELIVERED, Order.CANCELLED)),
                                      Order.user == user, *date_query).order_by(Order.date_created.desc())
        date_format = '%d-%m-%Y'
        orders = [('Order №{} {}'.format(order.id, order.date_created.strftime(date_format)), order.id) for order in
                  orders]
        if action == 'page':
            page = int(val)
            user_data['order_listing_page'] = page
            msg = user_data['stats_msg']
        else:
            page = user_data['order_listing_page']
            order = Order.get(id=val)
            try:
                btc_data = OrderBtcPayment.get(order=order)
            except OrderBtcPayment.DoesNotExist:
                btc_data = None
            msg = messages.create_service_notice(_, order, btc_data)
            user_data['stats_msg'] = msg
        reply_markup = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_USER_ORDER_SELECT
    else:
        del user_data['calendar']
        state = enums.ADMIN_STATISTICS_USER_SELECT_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_statistics_top_clients(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'back':
        msg = _('🌝 Statistics by users')
        reply_markup = keyboards.statistics_users(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_STATISTICS_USERS
    user_data['listing_page'] = 1
    if action == 'top_by_product':
        products = Product.select(Product.title, Product.id).tuples()
        msg = _('Select a product')
        reply_markup = keyboards.general_select_one_keyboard(_, products)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_STATISTICS_TOP_CLIENTS_PRODUCT
    elif action == 'top_by_date':
        state = enums.ADMIN_STATISTICS_TOP_CLIENTS_DATE
        return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
    elif action == 'top_by_location':
        locations = Location.select(Location.title, Location.id).tuples()
        msg = _('Select location')
        reply_markup = keyboards.general_select_one_keyboard(_, locations)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_STATISTICS_TOP_CLIENTS_LOCATION
    else:
        top_users = User.select().join(Order, on=Order.user)\
            .where(Order.status == Order.DELIVERED).group_by(User).order_by(fn.COUNT(Order.id).desc())
        currency = get_currency_symbol()
        msg = _('Top clients by orders:')
        msg += '\n'
        msg += '〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰'
        for rank, user in enumerate(top_users, 1):
            username = escape_markdown(user.username)
            orders = Order.select().where(Order.status == Order.DELIVERED, Order.user == user)
            total_orders = orders.count()
            total_price = sum((order.total_cost for order in orders))
            total_delivery = sum((order.delivery_fee for order in orders))
            total_discount = sum((order.discount for order in orders))
            total_price -= total_discount
            msg += '\n\n'
            msg += '{}. @{}'.format(rank, username)
            msg += '\n'
            msg += _('✅ Total delivered orders: *{}*, Total cost: *{}{}*').format(total_orders, total_price, currency)
            msg += '\n'
            msg += _('Total delivery fees: *{0}{2}*, Total discount: *{1}{2}*').format(total_delivery, total_discount, currency)
            if rank == 10:
                break
        reply_markup = keyboards.top_clients_stats_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_TOP_CLIENTS


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_top_users_by_product(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('page', 'select'):
        if action == 'page':
            page = int(val)
            user_data['listing_page'] = page
            msg = _('Select a product')
        else:
            currency = get_currency_symbol()
            product = Product.get(id=val)
            top_users = User.select().join(Order, on=Order.user).join(OrderItem, JOIN.LEFT_OUTER) \
                .where(OrderItem.product == product, Order.status == Order.DELIVERED).group_by(User) \
                .order_by(fn.SUM(OrderItem.total_price).desc())
            product_title = escape_markdown(product.title)
            msg = _('Top clients by product `{}`:').format(product_title)
            msg += '\n'
            msg += '〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰'
            for rank, user in enumerate(top_users, 1):
                username = escape_markdown(user.username)
                items = Order.select(OrderItem.total_price, OrderItem.count).join(OrderItem, JOIN.LEFT_OUTER) \
                    .where(OrderItem.product == product, Order.status == Order.DELIVERED, Order.user == user).tuples()
                total_products = sum((item[1] for item in items))
                total_price = sum((item[0] for item in items))
                msg += '\n\n'
                msg += '{}. @{}'.format(rank, username)
                msg += '\n'
                msg += _('✅ Total delivered products: *{}*, Total product cost: *{}{}*').format(total_products, total_price, currency)
                if rank == 10:
                    break
            page = user_data['listing_page']
        products = Product.select(Product.title, Product.id).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, products, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_TOP_CLIENTS_PRODUCT
    else:
        del user_data['listing_page']
        msg = _('🥇 Top clients')
        reply_markup = keyboards.top_clients_stats_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS_TOP_CLIENTS


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_top_users_by_location(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('page', 'select'):
        if action == 'page':
            page = int(val)
            user_data['listing_page'] = page
            msg = _('Select location')
        else:
            currency = get_currency_symbol()
            loc_id = int(val)
            location = Location.get(id=loc_id)
            top_users = User.select().join(Order, on=Order.user) \
                .where(Order.location == location, Order.status == Order.DELIVERED).group_by(User) \
                .order_by(fn.SUM(Order.total_cost).desc())
            location_title = escape_markdown(location.title)
            msg = _('Top clients by location `{}`:').format(location_title)
            msg += '\n'
            msg += '〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰'
            for rank, user in enumerate(top_users, 1):
                username = escape_markdown(user.username)
                orders = Order.select() \
                    .where(Order.location == location, Order.status == Order.DELIVERED, Order.user == user)
                total_orders = orders.count()
                total_price = sum((order.total_cost for order in orders))
                total_delivery = sum((order.delivery_fee for order in orders))
                total_discount = sum((order.discount for order in orders))
                total_price -= total_discount
                msg += '\n\n'
                msg += '{}. @{}'.format(rank, username)
                msg += '\n'
                msg += _('✅ Total delivered orders: *{}*, Total cost: *{}{}*').format(total_orders, total_price, currency)
                msg += '\n'
                msg += _('Total delivery fees: *{0}{2}*, Total discount: *{1}{2}*').format(total_delivery,
                                                                                           total_discount, currency)
                if rank == 10:
                    break
            page = user_data['listing_page']
        locations = Location.select(Location.title, Location.id).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, locations, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_STATISTICS_TOP_CLIENTS_LOCATION
    else:
        del user_data['listing_page']
        msg = _('🥇 Top clients')
        reply_markup = keyboards.top_clients_stats_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_STATISTICS_TOP_CLIENTS


@user_allowed(AllowedSetting.STATISTICS)
@user_passes
def on_top_by_date(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('year', 'month', 'day'):
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.ADMIN_STATISTICS_TOP_CLIENTS_DATE
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.ADMIN_STATISTICS_TOP_CLIENTS_DATE
                date_query = shortcuts.get_date_subquery(Order, first_date=first_date, second_date=second_date)
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Order, year=year)
        else:
            date_query = shortcuts.get_date_subquery(Order, month=month, year=year)
        currency = get_currency_symbol()
        top_users = User.select().join(Order, on=Order.user) \
            .where(Order.status == Order.DELIVERED, *date_query).group_by(User) \
            .order_by(fn.SUM(Order.total_cost).desc())
        msg = _('Top clients by date:')
        msg += '\n'
        msg += '〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰'
        for rank, user in enumerate(top_users, 1):
            username = escape_markdown(user.username)
            orders = Order.select() \
                .where(Order.status == Order.DELIVERED, Order.user == user, *date_query)
            total_orders = orders.count()
            total_price = sum((order.total_cost for order in orders))
            total_delivery = sum((order.delivery_fee for order in orders))
            total_discount = sum((order.discount for order in orders))
            total_price -= total_discount
            msg += '\n\n'
            msg += '{}. @{}'.format(rank, username)
            msg += '\n'
            msg += _('✅ Total delivered orders: *{}*, Total cost: *{}{}*').format(total_orders, total_price, currency)
            msg += '\n'
            msg += _('Total delivery fees: *{0}{2}*, Total discount: *{1}{2}*').format(total_delivery,
                                                                                       total_discount, currency)
            if rank == 10:
                break
    else:
        msg = _('🥇 Top clients')
    del user_data['calendar']
    reply_markup = keyboards.top_clients_stats_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    query.answer()
    return enums.ADMIN_STATISTICS_TOP_CLIENTS


@user_passes
def on_bot_settings_menu(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if data == 'bot_settings_back':
        msg = _('⚙️ Settings')
        user = User.get(telegram_id=user_id)
        if user.is_logistic_manager:
            reply_markup = keyboards.settings_logistic_manager_keyboard(_, user.allowed_settings_list)
        else:
            reply_markup = keyboards.settings_keyboard(_)
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
    elif data == 'bot_settings_edit_working_hours':
        return states.enter_working_days(_, bot, chat_id, msg_id, query.id)
    elif data == 'bot_settings_edit_messages':
        msg = _('⌨️ Edit bot messages')
        reply_markup = keyboards.edit_messages_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_MESSAGES
    elif data == 'bot_settings_lottery':
        msg = _('🎰 Lottery')
        reply_markup = keyboards.lottery_main_settings_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY
    elif data == 'bot_settings_channels':
        return states.enter_settings_channels(_, bot, chat_id, msg_id, query.id)
    elif data == 'bot_settings_advertisments':
        msg = _(' 🍔 Advertisments')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.advertisments_keyboard(_))
        query.answer()
        return enums.ADMIN_ADVERTISMENTS
    elif data == 'bot_settings_order_options':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    elif data == 'bot_settings_language':
        msg = _('🈚️ Default language:')
        reply_markup = keyboards.bot_language_keyboard(_, config.default_language)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_BOT_LANGUAGE
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
            query.answer(_('This function works only for admin'))
            return enums.ADMIN_BOT_SETTINGS
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_advertisments(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'ads_create':
        msg = _('Please enter Ad title')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.ADMIN_CREATE_AD_TITLE
    elif action == 'ads_edit':
        msg = _('Please select an Ad:')
        ads = Ad.select(Ad.title, Ad.id).tuples()
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, ads)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_ADS_LIST
    else:
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_create_ad_title(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query:
        msg = _(' 🍔 Advertisments')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=keyboards.advertisments_keyboard(_))
        query.answer()
        return enums.ADMIN_ADVERTISMENTS
    else:
        text = update.message.text
        user_data['create_ad'] = {'title': text}
        msg = _('Please enter Ad text:')
        bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
        return enums.ADMIN_CREATE_AD_TEXT


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_create_ad_text(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query:
        msg_id = query.message.message_id
        if query.data == 'back':
            msg = _('Please enter Ad title:')
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
            query.answer()
            return enums.ADMIN_CREATE_AD_TITLE
        else:
            msg = _(' 🍔 Advertisments')
            bot.edit_message_text(msg, chat_id, query.message.message_id,
                                  reply_markup=keyboards.advertisments_keyboard(_))
            query.answer()
            return enums.ADMIN_ADVERTISMENTS
    else:
        text = update.message.text
        user_data['create_ad']['text'] = text
        msg = _('Please send photo/animation')
        bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
        return enums.ADMIN_CREATE_AD_MEDIA


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_create_ad_media(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query:
        msg_id = query.message.message_id
        if query.data == 'back':
            msg = _('Please enter Ad text:')
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
            query.answer()
            return enums.ADMIN_CREATE_AD_TEXT
        else:
            msg = _(' 🍔 Advertisments')
            bot.edit_message_text(msg, chat_id, query.message.message_id,
                                  reply_markup=keyboards.advertisments_keyboard(_))
            query.answer()
            return enums.ADMIN_ADVERTISMENTS
    else:
        media_types = ('photo', 'animation')
        for name in media_types:
            val = getattr(update.message, name)
            if val:
                if type(val) == list:
                    val = val[-1]
                val = val.file_id
                user_data['create_ad']['media'] = val
                user_data['create_ad']['media_type'] = name
                break
        msg = _('Please select channels to send Ad to')
        channels = Channel.select(Channel.name, Channel.id).tuples()
        user_data['create_ad']['channels'] = [channel_id for name, channel_id in channels]
        channels = [(name, channel_id, True) for name, channel_id in channels]
        reply_markup = keyboards.general_select_keyboard(_, channels)
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        return enums.ADMIN_CREATE_AD_CHANNELS


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_create_ad_channels(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    selected_ids = user_data['create_ad']['channels']
    if action == 'select':
        val = int(val)
        if val in selected_ids:
            selected_ids.remove(val)
        else:
            selected_ids.append(val)
        msg = _('Please select channels to send Ad to')
        channels = Channel.select(Channel.name, Channel.id).tuples()
        channels = [(name, channel_id, channel_id in selected_ids) for name, channel_id in channels]
        reply_markup = keyboards.general_select_keyboard(_, channels)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CREATE_AD_CHANNELS
    else:
        msg = _('Please enter interval between messages in hours:')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.back_cancel_keyboard(_))
        query.answer()
        return enums.ADMIN_CREATE_AD_INTERVAL


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_create_ad_interval(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query:
        msg_id = query.message.message_id
        if query.data == 'back':
            selected_ids = user_data['create_ad']['channels']
            msg = _('Please select channels to send Ad to')
            channels = Channel.select(Channel.name, Channel.id).tuples()
            channels = [(name, channel_id, channel_id in selected_ids) for name, channel_id in channels]
            reply_markup = keyboards.general_select_keyboard(_, channels)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.ADMIN_CREATE_AD_CHANNELS
        else:
            msg = _(' 🍔 Advertisments')
            bot.edit_message_text(msg, chat_id, query.message.message_id,
                                  reply_markup=keyboards.advertisments_keyboard(_))
            query.answer()
            return enums.ADMIN_ADVERTISMENTS
    else:
        interval = update.message.text
        try:
            interval = int(interval)
        except ValueError:
            msg = _('Please enter a number')
            bot.send_message(chat_id, msg, reply_markup=keyboards.back_cancel_keyboard(_))
            return enums.ADMIN_CREATE_AD_INTERVAL
        ad_data = user_data['create_ad']
        channels_ids = ad_data.pop('channels')
        ads_exists = Ad.select().exists()
        ad = Ad.create(interval=interval, **ad_data)
        for channel_id in channels_ids:
            channel = Channel.get(id=channel_id)
            ChannelAd.create(ad=ad, channel=channel)
        if not ads_exists:
            shortcuts.send_channel_advertisments(bot)
        msg = _('New advertisment has been created!')
        bot.send_message(chat_id, msg, reply_markup=keyboards.advertisments_keyboard(_))
        return enums.ADMIN_ADVERTISMENTS


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ads_list(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        msg = _('Please select an Ad:')
        ads = Ad.select(Ad.title, Ad.id).tuples()
        reply_markup = keyboards.general_select_keyboard(_, ads, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_ADS_LIST
    elif action == 'select':
        ad = Ad.get(id=val)
        title = escape_markdown(ad.title)
        bot.delete_message(chat_id, msg_id)
        func = getattr(bot, 'send_{}'.format(ad.media_type))
        media_msg = func(chat_id, ad.media, caption=ad.text)
        user_data['ad_detail'] = {'msg_id': media_msg['message_id'], 'ad_id': ad.id}
        channels = Channel.select().join(ChannelAd, JOIN.LEFT_OUTER).where(ChannelAd.ad == ad).group_by(Channel.id)
        msg = _('Ad `{}`').format(title)
        msg += '\n'
        msg += '〰〰〰〰〰〰〰〰〰〰〰〰️'
        msg += '\n'
        msg += _('Channels:')
        msg += '\n'
        msg += ', '.join(item.name for item in channels) if channels.exists() else _('No channels')
        msg += '\n'
        msg += _('Interval: {} hours').format(ad.interval)
        bot.send_message(chat_id, msg, reply_markup=keyboards.edit_delete_keyboard(_), parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_AD_SELECTED
    else:
        del user_data['listing_page']
        msg = _(' 🍔 Advertisments')
        bot.edit_message_text(msg, chat_id, query.message.message_id,
                              reply_markup=keyboards.advertisments_keyboard(_))
        query.answer()
        return enums.ADMIN_ADVERTISMENTS


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ad_selected(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    ad_data = user_data['ad_detail']
    bot.delete_message(chat_id, ad_data['msg_id'])
    if action == 'edit':
        msg = _('Select option to edit')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.edit_ad_keyboard(_))
        query.answer()
        return enums.ADMIN_AD_EDIT
    elif action in ('delete', 'back'):
        if action == 'delete':
            ad = Ad.get(id=ad_data['ad_id'])
            title = escape_markdown(ad.title)
            msg = _('Ad `{}` has been deleted.').format(title)
            ChannelAd.delete().where(ChannelAd.ad == ad).execute()
            ad.delete_instance()
        else:
            msg = _('Please select an Ad:')
        ads = Ad.select(Ad.title, Ad.id).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, ads, user_data['listing_page'])
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ADS_LIST


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ad_edit(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    ad = Ad.get(id=user_data['ad_detail']['ad_id'])
    if action == 'ad_title':
        title = escape_markdown(ad.title)
        msg = _('Title: `{}`').format(title)
        msg += '\n'
        msg += _('Please enter new title')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_AD_EDIT_TITLE
    elif action == 'ad_text':
        msg = _('Text: {}').format(ad.text)
        msg += '\n'
        msg += _('Please enter new text')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_AD_EDIT_TEXT
    elif action == 'ad_media':
        msg = _('Please send photo/animation')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_AD_EDIT_MEDIA
    elif action == 'ad_interval':
        msg = _('Interval: {} hours').format(ad.interval)
        msg += '\n'
        msg += _('Please enter new interval')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_AD_EDIT_INTERVAL
    elif action == 'ad_channels':
        msg = _('Please select channels to send ad to')
        channels = Channel.select(Channel.name, Channel.id).tuples()
        selected_ids = Channel.select().join(ChannelAd, JOIN.LEFT_OUTER).where(ChannelAd.ad == ad)
        selected_ids = [channel.id for channel in selected_ids]
        user_data['ad_detail']['channels'] = selected_ids
        channels = [(name, channel_id, channel_id in selected_ids) for name, channel_id in channels]
        reply_markup = keyboards.general_select_keyboard(_, channels)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_AD_EDIT_CHANNELS
    else:
        title = escape_markdown(ad.title)
        bot.delete_message(chat_id, msg_id)
        func = getattr(bot, 'send_{}'.format(ad.media_type))
        media_msg = func(chat_id, ad.media, caption=ad.text)
        user_data['ad_detail'] = {'msg_id': media_msg['message_id'], 'ad_id': ad.id}
        channels = Channel.select().join(ChannelAd, JOIN.LEFT_OUTER).where(ChannelAd.ad == ad).group_by(Channel.id)
        msg = _('Ad `{}`').format(title)
        msg += '\n'
        msg += '〰〰〰〰〰〰〰〰〰〰〰〰️'
        msg += '\n'
        msg += _('Channels:')
        msg += '\n'
        msg += ', '.join(item.name for item in channels) if channels.exists() else _('No channels')
        msg += '\n'
        msg += _('Interval: {} hours').format(ad.interval)
        bot.send_message(chat_id, msg, reply_markup=keyboards.edit_delete_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_AD_SELECTED


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ad_edit_title(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    reply_markup = keyboards.edit_ad_keyboard(_)
    if query:
        msg = _('Select option to edit')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=reply_markup)
        query.answer()
    else:
        title = update.message.text
        ad = Ad.get(id=user_data['ad_detail']['ad_id'])
        ad.title = title
        ad.save()
        msg = _('Title has been changed to `{}`').format(title)
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_AD_EDIT


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ad_edit_text(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    reply_markup = keyboards.edit_ad_keyboard(_)
    if query:
        msg = _('Select option to edit')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=reply_markup)
        query.answer()
    else:
        text = update.message.text
        ad = Ad.get(id=user_data['ad_detail']['ad_id'])
        ad.text = text
        ad.save()
        msg = _('Ad text has been changed')
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_AD_EDIT


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ad_edit_media(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    reply_markup = keyboards.edit_ad_keyboard(_)
    if query:
        msg = _('Select option to edit')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=reply_markup)
        query.answer()
    else:
        ad = Ad.get(id=user_data['ad_detail']['ad_id'])
        media_types = ('photo','animation')
        for name in media_types:
            val = getattr(update.message, name)
            if val:
                if type(val) == list:
                    val = val[-1]
                val = val.file_id
                ad.media = val
                ad.media_type = name
                ad.save()
                break
        msg = _('Ad media has been changed')
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_AD_EDIT


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ad_edit_interval(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    reply_markup = keyboards.edit_ad_keyboard(_)
    if query:
        msg = _('Select option to edit')
        bot.edit_message_text(msg, chat_id, query.message.message_id, reply_markup=reply_markup)
        query.answer()
    else:
        interval = update.message.text
        try:
            interval = int(interval)
        except ValueError:
            msg = _('Please enter a number (hours)')
            bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
            return enums.ADMIN_AD_EDIT_INTERVAL
        ad = Ad.get(id=user_data['ad_detail']['ad_id'])
        ad.interval = interval
        ad.save()
        msg = _('Ad interval has been changed')
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_AD_EDIT


@user_allowed(AllowedSetting.ADVERTISMENTS)
@user_passes
def on_ad_edit_channels(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    selected_ids = user_data['ad_detail']['channels']
    ad = Ad.get(id=user_data['ad_detail']['ad_id'])
    if action == 'select':
        val = int(val)
        if val in selected_ids:
            selected_ids.remove(val)
        else:
            selected_ids.append(val)
        msg = _('Please select channels to send Ad to')
        channels = Channel.select(Channel.name, Channel.id).tuples()
        channels = [(name, channel_id, channel_id in selected_ids) for name, channel_id in channels]
        reply_markup = keyboards.general_select_keyboard(_, channels)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_AD_EDIT_CHANNELS
    elif action == 'done':
        ChannelAd.delete().where(ChannelAd.ad == ad).execute()
        for channel_id in selected_ids:
            channel = Channel.get(id=channel_id)
            ChannelAd.create(channel=channel, ad=ad)
        msg = _('Ad channels has been updated.')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.edit_ad_keyboard(_))
        return enums.ADMIN_AD_EDIT


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'lottery_settings':
        msg = _('⚙️ Lottery settings')
        reply_markup = keyboards.lottery_settings_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_SETTINGS
    elif action == 'lottery_create':
        try:
            lottery = Lottery.get(completed_date=None, active=True)
        except Lottery.DoesNotExist:
            msg = _('There\'s no active lottery now')
            query.answer(msg, show_alert=True)
            return enums.ADMIN_LOTTERY
        lottery_participants = LotteryParticipant.select()\
            .where(LotteryParticipant.lottery == lottery, LotteryParticipant.is_pending == False)
        lottery_participants = list(lottery_participants)
        prize_title = escape_markdown(lottery.prize_product.title)
        winners = []
        for i in range(lottery.num_codes):
            if not lottery_participants:
                break
            winner = random.choice(lottery_participants)
            lottery_participants.remove(winner)
            winner.is_winner = True
            winner.save()
            winners.append(winner)
            msg = _('You have won lottery №{}!').format(lottery.id)
            msg += '\n'
            msg += _('Prize: *x{} {}*').format(lottery.prize_count, prize_title)
            msg += '\n'
            msg += _('You can take prize on the next order')
            bot.send_message(winner.participant.telegram_id, msg, parse_mode=ParseMode.MARKDOWN)
        lottery.completed_date = datetime.now()
        lottery.active = False
        lottery.save()
        msg = _('Lottery №{} completed!').format(lottery.id)
        msg += '\n'
        msg += _('Winning codes: {}').format(', '.join([winner.code for winner in winners]))
        msg += '\n'
        msg += _('Winners:')
        msg += '\n'
        msg += ', '.join('@{}'.format(winner.participant.username) for winner in winners)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.lottery_main_settings_keyboard(_))
        permissions = [item.permission for item in lottery.permissions]
        channels_skip = ('service_channel', 'couriers_channel', 'reviews_channel')
        channels = Channel.select().join(ChannelPermissions, JOIN.LEFT_OUTER) \
            .where(ChannelPermissions.permission.in_(permissions), Channel.conf_name.not_in(channels_skip))\
            .group_by(Channel.id)
        _ = get_channel_trans()
        for channel in channels:
            msg = messages.create_just_completed_lottery_msg(_, lottery, winners)
            bot.send_message(channel.channel_id, msg, parse_mode=ParseMode.MARKDOWN, timeout=20)
        query.answer()
        return enums.ADMIN_LOTTERY
    elif action == 'lottery_winners':
        lotteries = Lottery.select(Lottery.id, Lottery.completed_date).where(Lottery.completed_date.is_null(False)).tuples()
        lotteries = [(_('Lottery №{} - {}').format(item_id, item_date.strftime('%d %b, %Y, %H:%M')), item_id) for
                     item_id, item_date in lotteries]
        user_data['listing_page'] = 1
        msg = _('Select a lottery:')
        reply_markup = keyboards.general_select_one_keyboard(_, lotteries)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_WINNERS
    elif action == 'lottery_messages':
        return states.enter_lottery_messages(_, bot, chat_id, msg_id, query.id)
    else:
        return states.enter_settings(_, bot, chat_id, user_id, msg_id=msg_id, query_id=query.id)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_winners(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action in ('page', 'select'):
        if action == 'page':
            page = int(val)
            user_data['listing_page'] = page
            msg = _('Select a lottery:')
        else:
            page = user_data['listing_page']
            lottery = Lottery.get(id=val)
            winners = LotteryParticipant.select()\
                .where(LotteryParticipant.is_winner == True, LotteryParticipant.lottery == lottery)
            msg = _('Lottery №{} winners:').format(lottery.id)
            for count, winner in enumerate(winners, 1):
                msg += '\n'
                msg += _('{}. @{} with code {}').format(count, winner.participant.username, winner.code)
        lotteries = Lottery.select(Lottery.id, Lottery.completed_date).where(
            Lottery.completed_date.is_null(False)).tuples()
        lotteries = [(_('Lottery №{} - {}').format(item_id, item_date.strftime('%d %b, %Y, %H:%M')), item_id) for
                     item_id, item_date in lotteries]
        reply_markup = keyboards.general_select_one_keyboard(_, lotteries, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_WINNERS
    else:
        del user_data['listing_page']
        msg = _('🎰 Lottery')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.lottery_main_settings_keyboard(_))
        query.answer()
        return enums.ADMIN_LOTTERY


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_settings(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    try:
        lottery = Lottery.get(completed_date=None)
    except Lottery.DoesNotExist:
        lottery = Lottery.create()
        permissions = UserPermission.get_clients_permissions()
        for permission in permissions:
            LotteryPermission.create(lottery=lottery, permission=permission)
    if action == 'lottery_on':
        if lottery.active:
            msg = _('You have active lottery №{}').format(lottery.id)
            msg += '\n'
            msg += _('Would you like to stop it?')
            reply_markup = keyboards.are_you_sure_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.ADMIN_LOTTERY_OFF_CONFIRM
        if not lottery.could_activate:
            msg = _('Please set all lottery options at first.')
            query.answer(msg, show_alert=True)
            return enums.ADMIN_LOTTERY_SETTINGS
        lottery.active = True
        lottery.save()
        shortcuts.manage_lottery_participants(bot)
        msg = _('⚙️ Lottery settings')
        reply_markup = keyboards.lottery_settings_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        msg = _('Lottery activated!')
        query.answer(msg)
        return enums.ADMIN_LOTTERY_SETTINGS
    if action == 'lottery_winners':
        winners_num = _('Not set') if lottery.num_codes is None else lottery.num_codes
        msg = _('Current number of winners: {}').format(winners_num)
        msg += '\n'
        msg += _('Please enter new number of winners codes')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_WINNERS_NUM
    elif action == 'lottery_participants':
        return states.enter_lottery_settings_participants(_, bot, chat_id, lottery, msg_id, query.id)
    elif action == 'lottery_conditions':
        return states.enter_lottery_conditions(_, bot, chat_id, lottery, msg_id, query.id)
    elif action == 'lottery_prize':
        msg = ''
        if lottery.prize_count and lottery.prize_product:
            msg += _('Current prize:')
            msg += '\n'
            msg += _('x{} - {}').format(lottery.prize_count, lottery.prize_product.title)
            msg += '\n'
        msg += _('Select product:')
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, products)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_PRODUCT_SELECT
    else:
        msg = _('🎰 Lottery')
        reply_markup = keyboards.lottery_main_settings_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_off_confirm(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'yes':
        lottery = Lottery.get(completed_date=None)
        lottery.active = False
        lottery.save()
        q_msg = _('Lottery has been switched off')
    msg = _('⚙️ Lottery settings')
    reply_markup = keyboards.lottery_settings_keyboard(_)
    bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
    if action == 'yes':
        query.answer(q_msg, show_alert=True)
    else:
        query.answer()
    return enums.ADMIN_LOTTERY_SETTINGS


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_winners_num(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query and query.data == 'back':
        return states.enter_lottery_settings(_, bot, chat_id, query.message.message_id, query.id)
    answer = update.message.text
    try:
        answer = int(answer)
    except ValueError:
        msg = _('Please enter a number')
        reply_markup = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_WINNERS_NUM
    lottery = Lottery.get(completed_date=None)
    lottery.num_codes = answer
    lottery.save()
    msg = _('Winners number has been set to *{}*').format(answer)
    return states.enter_lottery_settings(_, bot, chat_id, msg=msg)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_select_product(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        msg = _('Select product:')
        page = int(val)
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, products, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_PRODUCT_SELECT
    elif action == 'select':
        product = Product.get(id=val)
        user_data['lottery_settings'] = {'product_id': val}
        msg = messages.create_admin_product_description(_, product)
        msg += '\n'
        msg += _('Please select amount:')
        all_counts = shortcuts.get_all_product_counts(product)
        all_counts = [(item, item) for item in all_counts]
        reply_markup = keyboards.general_select_one_keyboard(_, all_counts)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_AMOUNT_SELECT
    else:
        del user_data['listing_page']
        return states.enter_lottery_settings(_, bot, chat_id, msg_id, query.id)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_amount_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        count = int(val)
        product_id = user_data['lottery_settings']['product_id']
        product = Product.get(id=product_id)
        lottery = Lottery.get(completed_date=None)
        lottery.prize_product = product
        lottery.prize_count = count
        lottery.save()
        msg = _('Lottery prize has been set to: {} x{}').format(product.title, count)
        return states.enter_lottery_settings(_, bot, chat_id, msg_id, query.id, query_msg=msg)
    else:
        msg = _('Select product:')
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, products)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_PRODUCT_SELECT


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_participants(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    lottery = Lottery.get(completed_date=None)
    if action == 'lottery_tickets':
        tickets_used = LotteryParticipant.select()\
            .where(LotteryParticipant.is_pending == False, LotteryParticipant.lottery == lottery).count()
        msg = _('Number of tickets set: {}').format(lottery.num_tickets)
        msg += '\n'
        msg += _('Number of tickets used: {}').format(tickets_used)
        msg += '\n'
        msg += _('Please enter new number of tickets')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_TICKETS_NUM
    elif action == 'lottery_permissions':
        selected = LotteryPermission.select().where(LotteryPermission.lottery == lottery)
        selected_ids = [perm.permission.id for perm in selected]
        all_permissions = UserPermission.get_clients_permissions()
        permissions = [(perm.get_permission_display(), perm.id, perm.id in selected_ids) for perm in all_permissions]
        user_data['lottery_settings'] = {'selected_ids': selected_ids}
        msg = _('Please select special clients')
        reply_markup = keyboards.general_select_keyboard(_, permissions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_PERMISSIONS
    elif action == 'lottery_participants':
        permissions = LotteryPermission.select().where(LotteryPermission.lottery == lottery)
        if permissions.exists():
            permissions = [item.permission for item in permissions]
        else:
            all_permissions = [
                UserPermission.AUTHORIZED_RESELLER, UserPermission.FRIEND,
                UserPermission.FAMILY, UserPermission.VIP_CLIENT, UserPermission.CLIENT
            ]
            permissions = UserPermission.select().where(UserPermission.permission.in_(all_permissions))
        users = User.select(User.username, User.id).join(UserPermission)\
            .where(UserPermission.permission.in_(permissions), User.banned == False).tuples()
        selected_ids = User.select().join(LotteryParticipant, JOIN.LEFT_OUTER)\
            .where(LotteryParticipant.lottery == lottery, LotteryParticipant.is_pending == False)
        selected_ids = [item.id for item in selected_ids]
        users = [(username, user_id, user_id in selected_ids) for username, user_id in users]
        user_data['lottery_settings'] = {'selected_ids': selected_ids, 'init_users': list(selected_ids)}
        user_data['listing_page'] = 1
        msg = _('Please select lottery participants')
        reply_markup = keyboards.general_select_keyboard(_, users)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_LOTTERY_PARTICIPANTS_USERS
    else:
        return states.enter_lottery_settings(_, bot, chat_id, msg_id, query.id)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_tickets_num(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    lottery = Lottery.get(completed_date=None)
    if query and query.data == 'back':
        return states.enter_lottery_settings_participants(_, bot, chat_id, lottery, query.message.message_id, query.id)
    tickets_num = update.message.text
    error_msg = None
    try:
        tickets_num = int(tickets_num)
    except ValueError:
        error_msg = _('Please enter a number')
    else:
        participants_count = LotteryParticipant.select()\
            .where(LotteryParticipant.lottery == lottery, LotteryParticipant.is_pending == False).count()
        if tickets_num < participants_count:
            error_msg = _('Number of tickets couldn\'t be lower than number of participants')
    if error_msg:
        bot.send_message(chat_id, error_msg, reply_markup=keyboards.cancel_button(_))
        return enums.ADMIN_LOTTERY_TICKETS_NUM
    lottery.num_tickets = tickets_num
    lottery.save()
    return states.enter_lottery_settings_participants(_, bot, chat_id, lottery)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_permissions(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    selected_ids = user_data['lottery_settings']['selected_ids']
    if action == 'select':
        val = int(val)
        if val in selected_ids:
            selected_ids.remove(val)
        else:
            selected_ids.append(val)
        all_permissions = UserPermission.get_clients_permissions()
        permissions = [(perm.get_permission_display(), perm.id, perm.id in selected_ids) for perm in all_permissions]
        msg = _('Please select special clients')
        reply_markup = keyboards.general_select_keyboard(_, permissions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_PERMISSIONS
    elif action == 'done':
        lottery = Lottery.get(completed_date=None)
        LotteryPermission.delete().where(LotteryPermission.lottery == lottery).execute()
        for perm_id in selected_ids:
            permission = UserPermission.get(id=perm_id)
            LotteryPermission.create(lottery=lottery, permission=permission)
        del user_data['lottery_settings']['selected_ids']
        return states.enter_lottery_settings_participants(_, bot, chat_id, lottery, msg_id, query.id)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_participants_users(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    selected_ids = user_data['lottery_settings']['selected_ids']
    lottery = Lottery.get(completed_date=None)
    if action in ('page', 'select'):
        val = int(val)
        if action == 'page':
            user_data['listing_page'] = val
        else:
            if val in selected_ids:
                selected_ids.remove(val)
            else:
                if len(selected_ids) == lottery.num_tickets:
                    msg = _('Cannot add more users than number of tickets')
                    query.answer(msg)
                    return enums.ADMIN_LOTTERY_PARTICIPANTS_USERS
                selected_ids.append(val)
        permissions = LotteryPermission.select().where(LotteryPermission.lottery == lottery)
        if permissions.exists():
            permissions = [item.permission for item in permissions]
        else:
            all_permissions = [
                UserPermission.AUTHORIZED_RESELLER, UserPermission.FRIEND,
                UserPermission.FAMILY, UserPermission.VIP_CLIENT, UserPermission.CLIENT
            ]
            permissions = UserPermission.select().where(UserPermission.permission.in_(all_permissions))
        users = User.select(User.username, User.id).join(UserPermission) \
            .where(UserPermission.permission.in_(permissions), User.banned == False).tuples()
        users = [(username, user_id, user_id in selected_ids) for username, user_id in users]
        msg = _('Please select lottery participants')
        page = user_data['listing_page']
        reply_markup = keyboards.general_select_keyboard(_, users, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_LOTTERY_PARTICIPANTS_USERS
    elif action == 'done':
        init_users = user_data['lottery_settings']['init_users']
        users_to_remove = [item for item in init_users if item not in selected_ids]
        for user_id in users_to_remove:
            user = User.get(id=user_id)
            try:
                participant = LotteryParticipant.get(participant=user)
            except LotteryParticipant.DoesNotExist:
                continue
            participant.delete_instance()
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, you have been removed from lottery №{}').format(user.username, lottery.id)
            bot.send_message(user.telegram_id, msg, timeout=20)
        all_codes = LotteryParticipant.filter(is_pending=False, lottery=lottery)
        all_codes = [item.code for item in all_codes]
        for user_id in selected_ids:
            if user_id in init_users:
                continue
            user = User.get(id=user_id)
            code, user_msg = shortcuts.add_client_to_lottery(lottery, user, all_codes)
            all_codes.append(code)
            bot.send_message(user.telegram_id, user_msg)
        q_msg = _('Lottery participants were changed')
        del user_data['lottery_settings']
        return states.enter_lottery_settings_participants(_, bot, chat_id, lottery, msg_id, query.id, q_msg)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_conditions(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('lottery_price', 'lottery_product'):
        action_map = {'lottery_price': Lottery.PRICE, 'lottery_product': Lottery.PRODUCT}
        user_data['lottery_settings'] = {'by': action_map[action]}
        if action == 'lottery_price':
            currency_sym = get_currency_symbol()
            msg = _('Please enter minimum order price ({}) to enter lottery').format(currency_sym)
            reply_markup = keyboards.cancel_button(_)
            state = enums.ADMIN_LOTTERY_MIN_PRICE
        else:
            msg = _('🧾 Participation conditions')
            reply_markup = keyboards.lottery_products_condition_keyboard(_)
            state = enums.ADMIN_LOTTERY_PRODUCTS_CONDITION
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return state
    else:
        return states.enter_lottery_settings(_, bot, chat_id, msg_id, query.id)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_min_price(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query and query.data == 'back':
        lottery = Lottery.get(completed_date=None)
        return states.enter_lottery_conditions(_, bot, chat_id, lottery, query.message.message_id, query.id)
    min_price = update.message.text
    try:
        min_price = int(min_price)
    except ValueError:
        msg = _('Please enter a number')
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
        return enums.ADMIN_LOTTERY_MIN_PRICE
    user_data['lottery_settings']['min_price'] = min_price
    msg = _('🧾 Participation conditions')
    reply_markup = keyboards.lottery_products_condition_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=reply_markup)
    return enums.ADMIN_LOTTERY_PRODUCTS_CONDITION


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_products_condition(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'lottery_single':
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        msg = _('Please select a product')
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, products)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_SINGLE_PRODUCT_CONDITION
    elif action == 'lottery_category':
        categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
        msg = _('Please select a category')
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, categories)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_CATEGORY_CONDITION
    elif action == 'lottery_all':
        lottery = Lottery.get(completed_date=None)
        by_condition = user_data['lottery_settings']['by']
        lottery.by_condition = by_condition
        if by_condition == Lottery.PRICE:
            min_price = user_data['lottery_settings']['min_price']
            lottery.min_price = min_price
        lottery.products_condition = Lottery.ALL_PRODUCTS
        lottery.save()
        return states.enter_lottery_conditions(_, bot, chat_id, lottery, msg_id, query.id)
    else:
        del user_data['lottery_settings']
        lottery = Lottery.get(completed_date=None)
        return states.enter_lottery_conditions(_, bot, chat_id, lottery, msg_id, query.id)


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_single_product_condition(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        msg = _('Please select a product')
        reply_markup = keyboards.general_select_one_keyboard(_, products, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_SINGLE_PRODUCT_CONDITION
    del user_data['listing_page']
    if action == 'select':
        lottery = Lottery.get(completed_date=None)
        by_condition = user_data['lottery_settings']['by']
        lottery.by_condition = by_condition
        if by_condition == Lottery.PRICE:
            min_price = user_data['lottery_settings']['min_price']
            lottery.min_price = min_price
        product = Product.get(id=val)
        lottery.products_condition = Lottery.SINGLE_PRODUCT
        lottery.single_product_condition = product
        lottery.save()
        return states.enter_lottery_conditions(_, bot, chat_id, lottery, msg_id, query.id)
    else:
        msg = _('🧾 Participation conditions')
        reply_markup = keyboards.lottery_products_condition_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_LOTTERY_PRODUCTS_CONDITION


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_category_condition(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        products = ProductCategory.select(ProductCategory.title, ProductCategory.id).where().tuples()
        msg = _('Please select a category')
        reply_markup = keyboards.general_select_one_keyboard(_, products, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY_CATEGORY_CONDITION
    del user_data['listing_page']
    if action == 'select':
        lottery = Lottery.get(completed_date=None)
        by_condition = user_data['lottery_settings']['by']
        lottery.by_condition = by_condition
        if by_condition == Lottery.PRICE:
            min_price = user_data['lottery_settings']['min_price']
            lottery.min_price = min_price
        category = ProductCategory.get(id=val)
        lottery.products_condition = Lottery.CATEGORY
        lottery.category_condition = category
        lottery.save()
        return states.enter_lottery_conditions(_, bot, chat_id, lottery, msg_id, query.id)
    else:
        msg = _('🧾 Participation conditions')
        reply_markup = keyboards.lottery_products_condition_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_LOTTERY_PRODUCTS_CONDITION


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_messages(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'lottery_messages':
        conf_val = not config.lottery_messages
        if conf_val:
            shortcuts.send_lottery_messages(bot)
        config.set_value('lottery_messages', conf_val)
        return states.enter_lottery_messages(_, bot, chat_id, msg_id, query.id)
    elif action == 'lottery_intervals':
        msg = _('Please enter new interval between messages in hours:')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.ADMIN_LOTTERY_MESSAGES_INTERVAL
    else:
        msg = _('🎰 Lottery')
        reply_markup = keyboards.lottery_main_settings_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOTTERY


@user_allowed(AllowedSetting.LOTTERY)
@user_passes
def on_lottery_messages_interval(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    if query and query.data == 'back':
        return states.enter_lottery_messages(_, bot, chat_id, query.message.message_id, query.id)
    interval = update.message.text
    try:
        interval = int(interval)
    except ValueError:
        msg = _('Please enter a number')
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_))
        return enums.ADMIN_LOTTERY_MESSAGES_INTERVAL
    config.set_value('lottery_messages_interval', interval)
    return states.enter_lottery_messages(_, bot, chat_id)


@user_allowed(AllowedSetting.DEFAULT_LANGUAGE)
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
        reply_markup = keyboards.bot_language_keyboard(_, config.default_language)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_BOT_LANGUAGE
    elif action == 'back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.COURIERS)
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
        page = int(val)
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


@user_allowed(AllowedSetting.COURIERS)
@user_passes
def on_courier_detail(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    courier_id = user_data['courier_select']
    if action == 'courier_details_locations':
        courier = User.get(id=courier_id)
        courier_locs = Location.select().join(CourierLocation)\
            .where(CourierLocation.user == courier)
        courier_locs = [loc.id for loc in courier_locs]
        all_locs = []
        for loc in Location.select():
            is_picked = True if loc.id in courier_locs else False
            all_locs.append((loc.title, loc.id, is_picked))
        user_data['courier_locations_select'] = {'page': 1, 'ids': courier_locs}
        reply_markup = keyboards.general_select_keyboard(_, all_locs)
        msg = _('🎯 Change locations')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_COURIER_LOCATIONS
    elif action == 'courier_details_warehouse':
        user_data['products_listing_page'] = 1
        return states.enter_courier_warehouse_products(_, bot, chat_id, msg_id, query.id)
    elif action == 'courier_details_back':
        del user_data['courier_select']
        msg = _('🛵 Couriers')
        couriers = User.select(User.username, User.id).join(UserPermission) \
            .where(UserPermission.permission == UserPermission.COURIER, User.banned == False).tuples()
        page = user_data['listing_page']
        reply_markup = keyboards.general_select_one_keyboard(_, couriers, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_COURIERS


@user_allowed(AllowedSetting.COURIERS)
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
        msg = _('🎯 Change locations')
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


@user_allowed(AllowedSetting.COURIERS)
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


@user_allowed(AllowedSetting.COURIERS)
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


@user_allowed(AllowedSetting.COURIERS)
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


@user_allowed(AllowedSetting.BOT_MESSAGES)
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


@user_allowed(AllowedSetting.BOT_MESSAGES)
@user_passes
def on_edit_messages(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action.startswith('edit_msg'):
        if action == 'edit_msg_back':
            return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
        else:
            if action == 'edit_msg_contact_info':
                config_msg = config.contact_info
                msg_remainder = _('Type new contact info')
                user_data['edit_message'] = {'name': 'contact_info', 'msg': _('Contact info were changed.')}
            elif action == 'edit_msg_welcome':
                config_msg = config.welcome_text
                msg_remainder = _('Type new welcome message')
                user_data['edit_message'] = {'name': 'welcome_text', 'msg': _('Welcome text was changed.')}
            elif action == 'edit_msg_order_details':
                config_msg = config.order_text
                msg_remainder = _('Type new order details message')
                user_data['edit_message'] = {'name': 'order_details', 'msg': _('Order details message was changed.')}
            else:
                config_msg = config.order_complete_text
                msg_remainder = _('Type new order final message')
                user_data['edit_message'] = {'name': 'order_complete_text',
                                             'msg': _('Order final message was changed.')}
            msg = _('Raw:\n\n`{}`').format(config_msg)
            msg += '\n\n'
            msg += _('Displayed:\n\n{}').format(config_msg)
            msg += '\n\n'
            msg += msg_remainder
            reply_markup = keyboards.cancel_button(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return enums.ADMIN_EDIT_MESSAGES_ENTER
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
@user_passes
def on_users(bot, update, user_data):
    query = update.callback_query
    action = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'users_registered':
        return states.enter_settings_registered_users_perms(_, bot, chat_id, msg_id, query.id)
    elif action == 'users_pending':
        user_data['listing_page'] = 1
        return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id)
    elif action == 'users_black_list':
        user_data['listing_page'] = 1
        return states.enter_black_list(_, bot, chat_id, user_id, msg_id, query.id)
    elif action == 'users_logistic_managers':
        msg = _('Please select logistic manager:')
        lm = UserPermission.get(permission=UserPermission.LOGISTIC_MANAGER)
        objects = User.select(User.username, User.id).where(User.permission == lm).tuples()
        user_data['listing_page'] = 1
        reply_markup = keyboards.general_select_one_keyboard(_, objects)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOGISTIC_MANAGERS
    else:
        msg = _('⚙️ Settings')
        user = User.get(telegram_id=user_id)
        if user.is_logistic_manager:
            reply_markup = keyboards.settings_logistic_manager_keyboard(_, user.allowed_settings_list)
        else:
            reply_markup = keyboards.settings_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        return enums.ADMIN_MENU


@user_allowed(AllowedSetting.USERS)
@user_passes
def on_registered_users_perms(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        perm = UserPermission.get(id=val)
        user_data['registered_users'] = {'perm_id': val}
        user_data['listing_page'] = 1
        return states.enter_settings_registered_users(_, bot, chat_id, perm, msg_id, query.id)
    elif action == 'back':
        return states.enter_settings_users(_, bot, chat_id, user_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
        perm_id = user_data['registered_users']['perm_id']
        perm = UserPermission.get(id=perm_id)
        return states.enter_settings_registered_users(_, bot, chat_id, perm, msg_id, query.id, page=page)
    elif action == 'select':
        user = User.get(id=val)
        username = user.username
        msg = '@{}'.format(username)
        msg += '\n'
        msg += _('Status: {}').format(user.permission.get_permission_display())
        user_data['user_select'] = val
        return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_settings_registered_users_perms(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
    if action == 'registration_show':
        bot.delete_message(chat_id, msg_id)
        answers_ids = shortcuts.send_user_identification_answers(bot, chat_id, user)
        user_data['user_id_messages'] = answers_ids
        msg = _('User @{}').format(user.username)
        return states.enter_registered_users_select(_, bot, chat_id, msg, query.id)
    elif action == 'registration_remove':
        msg = _('Remove registration for @{}?').format(user.username)
        reply_markup = keyboards.are_you_sure_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_REGISTERED_USERS_REMOVE
    elif action == 'registration_status':
        msg = _('⭐️ Change user status')
        registered_perms = (UserPermission.OWNER, UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION)
        perms = UserPermission.select().where(UserPermission.permission.not_in(registered_perms))\
            .order_by(UserPermission.permission.desc())
        perms = [(perm.get_permission_display(), perm.id) for perm in perms]
        reply_markup = keyboards.general_select_one_keyboard(_, perms, page_len=len(perms))
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REGISTERED_USERS_STATUS
    elif action == 'registration_black_list':
        msg = _('Black list user @{}?').format(user.username)
        reply_markup = keyboards.are_you_sure_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_REGISTERED_USERS_BLACK_LIST
    if action == 'registration_back':
        del user_data['user_select']
        page = user_data['listing_page']
        perm_id = user_data['registered_users']['perm_id']
        perm = UserPermission.get(id=perm_id)
        return states.enter_settings_registered_users(_, bot, chat_id, perm, msg_id, query.id, page=page)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
        username = user.username
        if action == 'yes':
            shortcuts.remove_user_registration(user)
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, your registration has been removed').format(username)
            reply_markup = keyboards.start_btn(_)
            bot.send_message(user.telegram_id, msg, reply_markup=reply_markup)
            msg = _('Registration for @{} has been removed!').format(username)
            page = user_data['listing_page']
            del user_data['user_select']
            perm_id = user_data['registered_users']['perm_id']
            perm = UserPermission.get(id=perm_id)
            return states.enter_settings_registered_users(_, bot, chat_id, perm, msg_id, query.id, page=page, msg=msg)
        else:
            msg = '@{}'.format(username)
            msg += '\n'
            msg += _('Status: {}').format(user.permission.get_permission_display())
            return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
        username = user.username
        if action == 'select':
            perm = UserPermission.get(id=val)
            user.permission = perm
            user.save()
            AllowedSetting.delete().where(AllowedSetting.user == user).execute()
            perm_display = perm.get_permission_display()
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, your status has been changed to: {}').format(username, perm_display)
            reply_markup = keyboards.start_btn(_)
            bot.send_message(user.telegram_id, msg, reply_markup=reply_markup)
            msg = _('User\'s @{} status was changed to: {}').format(username, perm_display)
        else:
            msg = '@{}'.format(username)
            msg += '\n'
            msg += _('Status: {}').format(user.permission.get_permission_display())
        return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
            msg = _('@{} has been added to black-list!').format(username)
            perm_id = user_data['registered_users']['perm_id']
            perm = UserPermission.get(id=perm_id)
            return states.enter_settings_registered_users(_, bot, chat_id, perm, msg_id, query.id, msg=msg)
        else:
            msg = '@{}'.format(username)
            msg += '\n'
            msg += _('Status: {}').format(user.permission.get_permission_display())
            return states.enter_registered_users_select(_, bot, chat_id, msg, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
        return states.enter_settings_users(_, bot, chat_id, user_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
        username = user.username
        if action == 'approve_user':
            msg = _('Select new status for user @{}').format(username)
            registered_perms = (UserPermission.OWNER, UserPermission.NOT_REGISTERED, UserPermission.PENDING_REGISTRATION)
            perms = UserPermission.select().where(UserPermission.permission.not_in(registered_perms)) \
                .order_by(UserPermission.permission.desc())
            perms = [(perm.get_permission_display(), perm.id) for perm in perms]
            reply_markup = keyboards.general_select_one_keyboard(_, perms, page_len=len(perms))
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.ADMIN_PENDING_REGISTRATIONS_APPROVE
        elif action == 'black_list':
            msg = _('Black-list user @{}?').format(username)
            reply_markup = keyboards.are_you_sure_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
            query.answer()
            return enums.ADMIN_PENDING_REGISTRATIONS_BLACK_LIST
        else:
            del user_data['user_select']
            page = user_data['listing_page']
            return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id, page=page)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
        username = user.username
        if action == 'select':
            perm = UserPermission.get(id=val)
            user.permission = perm
            user.save()
            perm_display = perm.get_permission_display()
            user_trans = get_trans(user.telegram_id)
            msg = user_trans('{}, your registration has been approved. Your status is {}').format(username, perm_display)
            reply_markup = keyboards.start_btn(_)
            bot.send_message(user.telegram_id, msg, reply_markup=reply_markup)
            msg = _('User\'s @{} registration approved!').format(username)
            page = user_data['listing_page']
            del user_data['user_select']
            return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id, page=page, msg=msg)
        else:
            return states.enter_pending_registrations_user(_, bot, chat_id, msg_id, query.id, user_data, user_id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
            LotteryParticipant.delete().join(Lottery)\
                .where(Lottery.completed_date == None | LotteryParticipant.is_pending == True,
                       LotteryParticipant.participant == user).execute()
            username = escape_markdown(user.username)
            banned_trans = get_trans(user.telegram_id)
            msg = banned_trans('{}, you have been black-listed.').format(username)
            bot.send_message(user.telegram_id, msg)
            msg = _('User @{} has been banned.').format(username)
            page = user_data['listing_page']
            del user_data['user_select']
            return states.enter_pending_registrations(_, bot, chat_id, msg_id, query.id, page=page, msg=msg)
        elif action == 'no':
            return states.enter_pending_registrations_user(_, bot, chat_id, msg_id, query.id, user_data, user_id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
        return states.enter_black_list(_, bot, chat_id, user_id, msg_id, query.id, page=page)
    elif action == 'select':
        user_data['user_select'] = val
        user = User.get(id=val)
        msg = _('User @{}').format(user.username)
        reply_markup = keyboards.banned_user_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_BLACK_LIST_USER
    elif action == 'back':
        del user_data['listing_page']
        return states.enter_settings_users(_, bot, chat_id, user_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.USERS)
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
    if action in 'black_list_show':
        user_id = user_data['user_select']
        user = User.get(id=user_id)
        bot.delete_message(chat_id, msg_id)
        answers_ids = shortcuts.send_user_identification_answers(bot, chat_id, user)
        user_data['user_id_messages'] = answers_ids
        msg = _('User @{}').format(user.username)
        reply_markup = keyboards.banned_user_keyboard(_)
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
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
        msg = _('@{} has been removed from black list!').format(username)
        return states.enter_black_list(_, bot, chat_id, user_id, msg_id, query.id, page=page, msg=msg)
    elif action == 'black_list_back':
        del user_data['user_select']
        page = user_data['listing_page']
        return states.enter_black_list(_, bot, chat_id, user_id, msg_id, query.id, page=page)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_logistic_managers(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        msg = _('Please select logistic manager:')
        lm = UserPermission.get(permission=UserPermission.LOGISTIC_MANAGER)
        objects = User.select(User.username, User.id).where(User.permission == lm).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, objects, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOGISTIC_MANAGERS
    elif action == 'select':
        user_data['logistic_manager_id'] = val
        user = User.get(id=val)
        msg = _('Select allowed settings for @{}').format(user.username)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.logistic_manager_settings_keyboard(_, user))
        query.answer()
        return enums.ADMIN_LOGISTIC_MANAGER_SETTINGS
    else:
        return states.enter_settings_users(_, bot, chat_id, user_id, msg_id, query.id)


@user_passes
def on_logistic_manager_settings(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'logistic_back':
        msg = _('Please select logistic manager:')
        lm = UserPermission.get(permission=UserPermission.LOGISTIC_MANAGER)
        objects = User.select(User.username, User.id).where(User.permission == lm).tuples()
        reply_markup = keyboards.general_select_one_keyboard(_, objects, user_data['listing_page'])
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_LOGISTIC_MANAGERS
    else:
        val = action.split('_')[-1]
        val = int(val)
        user = User.get(id=user_data['logistic_manager_id'])
        try:
            setting = AllowedSetting.get(user=user, setting=val)
        except AllowedSetting.DoesNotExist:
            AllowedSetting.create(user=user, setting=val)
        else:
            setting.delete_instance()
        msg = _('Select allowed settings for @{}').format(user.username)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.logistic_manager_settings_keyboard(_, user))
        query.answer()
        return enums.ADMIN_LOGISTIC_MANAGER_SETTINGS


@user_allowed(AllowedSetting.CHANNELS)
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
        reply_markup = keyboards.bot_language_keyboard(_, config.channels_language)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_CHANNELS_LANGUAGE
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.CHANNELS)
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


@user_allowed(AllowedSetting.CHANNELS)
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


@user_allowed(AllowedSetting.CHANNELS)
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


@user_allowed(AllowedSetting.CHANNELS)
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


@user_allowed(AllowedSetting.CHANNELS)
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


@user_allowed(AllowedSetting.CHANNELS)
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


@user_allowed(AllowedSetting.CHANNELS)
@user_passes
def on_channels_language(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('iw', 'en'):
        config.set_value('channels_language', action)
        msg = _('🈚︎ Select language:')
        reply_markup = keyboards.bot_language_keyboard(_, config.channels_language)
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
        reply_markup = keyboards.bot_orders_keyboard(_)
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
        currency_str, currency_sym = Currencies.CURRENCIES[config.currency]
        msg = _('Enter discount like:\n'
                '50 > 500: all deals above 500{0} will be -50{0}\n'
                '10% > 500: all deals above 500{0} will be -10%\n'
                '*Current discount: {1} > {2}*').format(currency_sym, config.discount, config.discount_min)
        msg += '\n\n'
        msg += _('Currency: {} {}').format(currency_str, currency_sym)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ADD_DISCOUNT
    elif data == 'bot_order_options_delivery':
        return states.enter_delivery_options(_, bot, chat_id, msg_id, query.id)
    elif data == 'bot_order_options_price_groups':
        msg = _('💸 Product price groups')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.create_product_price_groups_keyboard(_))
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP
    elif data == 'bot_order_options_add_locations':
        return states.enter_locations(_, bot, chat_id, msg_id, query.id)
    elif data == 'bot_order_options_currency':
        currency = config.currency
        currency_name, currency_symbol = Currencies.CURRENCIES[currency]
        msg = _('Current currency: *{} {}*'.format(currency_name, currency_symbol))
        msg += '\n'
        msg += _('Select new currency:')
        reply_markup = keyboards.create_currencies_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_SET_CURRENCIES
    elif data == 'bot_order_options_bitcoin_payments':
        btc_creds = BitcoinCredentials.select().first()
        wallet_id = btc_creds.wallet_id
        msg = _('💰 Bitcoin payments')
        msg += '\n'
        msg += _('Enabled: *{}*').format(_('Enabled') if btc_creds.enabled else _('Disabled'))
        msg += '\n'
        msg += _('Wallet ID: *{}*').format(wallet_id if wallet_id else '')
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_creds.password else 'No')
        reply_markup = keyboards.create_btc_settings_keyboard(_, btc_creds.enabled)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BTC_PAYMENTS
    elif data == 'bot_order_options_identify':
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.for_order, first_question))
        msg = _('👨 Edit identification process')
        reply_markup = keyboards.edit_identification_keyboard(_, questions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ORDERS)
@user_passes
def on_admin_orders(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    action = query.data
    if action == 'back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    if action == 'pending':
        orders = Order.select().where(Order.status.in_((Order.CONFIRMED, Order.PROCESSING)))
        orders_data = [(order.id, order.date_created.strftime('%d/%m/%Y')) for order in orders]
        orders = [(_('Order №{} {}').format(order_id, order_date), order_id) for order_id, order_date in orders_data]
        user_data['listing_page'] = 1
        keyboard = keyboards.general_select_one_keyboard(_, orders)
        msg = _('Please select an order\nBot will send it to service channel')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_ORDERS_PENDING_SELECT
    elif action == 'finished':
        state = enums.ADMIN_ORDERS_FINISHED_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ORDERS)
@user_passes
def on_admin_orders_pending_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'back':
        del user_data['listing_page']
        bot.edit_message_text(_('📖 Orders'), chat_id, msg_id, reply_markup=keyboards.bot_orders_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS
    if action == 'page':
        orders = user_data['admin_orders']['list']
        page = int(val)
        user_data['admin_orders']['page'] = page
        keyboard = keyboards.general_select_one_keyboard(_, orders, page)
        msg = _('Please select an order\nBot will send it to service channel')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS_PENDING_SELECT
    elif action == 'select':
        service_trans = get_channel_trans()
        order = Order.get(id=val)
        user_name = order.user.username
        location = order.location.title if order.location else '-'
        msg = service_trans('Order №{}, Location {}\nUser @{}').format(val, location, user_name)
        reply_markup = keyboards.show_order_keyboard(_, order.id)
        shortcuts.send_channel_msg(bot, msg, get_service_channel(), reply_markup, order, parse_mode=None)
        query.answer(text=_('Order has been sent to service channel'), show_alert=True)
        return enums.ADMIN_ORDERS_PENDING_SELECT
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ORDERS)
@user_passes
def on_admin_orders_finished_date(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        bot.edit_message_text(_('📖 Orders'), chat_id, msg_id,
                              reply_markup=keyboards.bot_orders_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS
    elif action in ('day', 'month', 'year'):
        year, month = user_data['calendar']['year'], user_data['calendar']['month']
        if action == 'day':
            day = int(val)
            first_date = user_data['calendar'].get('first_date')
            if not first_date:
                first_date = date(year=year, month=month, day=day)
                user_data['calendar']['first_date'] = first_date
                state = enums.ADMIN_ORDERS_FINISHED_DATE
                return shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
            else:
                second_date = date(year=year, month=month, day=day)
                if first_date > second_date:
                    query.answer(_('Second date could not be before first date'), show_alert=True)
                    return enums.ADMIN_ORDERS_FINISHED_DATE
                del user_data['calendar']
                date_query = shortcuts.get_date_subquery(first_date=first_date, second_date=second_date)
                user_data['stats'] = {'first_date': first_date, 'second_date': second_date}
        elif action == 'year':
            date_query = shortcuts.get_date_subquery(Order, year=year)
        else:
            date_query = shortcuts.get_date_subquery(Order, month=month, year=year)
        orders = Order.select().where(Order.status == Order.DELIVERED, *date_query)
        orders_data = [(order.id, order.user.username, order.date_created.strftime('%d/%m/%Y')) for order in orders]
        orders = [(_('Order №{} @{} {}').format(order_id, user_name, order_date), order_id) for order_id, user_name, order_date in orders_data]
        user_data['admin_finished_orders'] = orders
        user_data['listing_page'] = 1
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=_('Select order'),
                              reply_markup=keyboards.general_select_one_keyboard(_, orders),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS_FINISHED_LIST
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ORDERS)
@user_passes
def on_admin_orders_finished_list(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        del user_data['listing_page']
        state = enums.ADMIN_ORDERS_FINISHED_DATE
        shortcuts.initialize_calendar(_, bot, user_data, chat_id, state, msg_id, query.id)
        return state
    orders = user_data['admin_finished_orders']
    if action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        msg = _('Select order')
        keyboard = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id,
                              reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_ORDERS_FINISHED_LIST
    elif action == 'select':
        order = Order.get(id=val)
        try:
            btc_data = OrderBtcPayment.get(id=order)
        except OrderBtcPayment.DoesNotExist:
            btc_data = None
        msg = messages.create_service_notice(_, order, btc_data)
        courier_username = escape_markdown(order.courier.username)
        courier_delivered = _('Courier: {}').format(courier_username)
        msg += '\n\n' + courier_delivered
        user_data['admin_finished_id'] = val
        reply_markup = keyboards.send_to_service_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ORDERS_FINISHED_SELECT


@user_allowed(AllowedSetting.ORDERS)
@user_passes
def on_admin_orders_finished_select(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action == 'back':
        page = user_data['listing_page']
        msg = _('Select order')
        orders = user_data['admin_finished_orders']
        keyboard = keyboards.general_select_one_keyboard(_, orders, page)
        bot.edit_message_text(msg, chat_id, msg_id,
                              reply_markup=keyboard)
        query.answer()
        return enums.ADMIN_ORDERS_FINISHED_LIST
    elif action == 'send':
        order_id = user_data['admin_finished_id']
        order = Order.get(id=order_id)
        courier = order.courier
        status = courier.permission.get_permission_display()
        service_trans = get_channel_trans()
        msg = service_trans('Order №{} was delivered by {} @{}\n').format(order.id, status, courier.username)
        msg += service_trans('Client: @{}').format(order.user.username)
        keyboard = keyboards.order_finished_keyboard(_, order_id)
        msg_id = shortcuts.send_channel_msg(bot, msg, get_service_channel(), keyboard, order, parse_mode=None)
        order.order_text_msg_id = msg_id
        order.save()
        query.answer(_('Order was sent to service channel.'))
        return enums.ADMIN_ORDERS_FINISHED_SELECT


@user_allowed(AllowedSetting.DELIVERY)
@user_passes
def on_delivery(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'edit_methods':
        msg = _('🏃‍♂️ Edit delivery methods')
        reply_markup = keyboards.delivery_methods_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_DELIVERY_METHODS
    elif action == 'edit_fee':
        return states.enter_delivery_fee(_, bot, chat_id, msg_id, query.id)
    elif action == 'back':
        return states.enter_menu(bot, update, user_data, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.DELIVERY)
@user_passes
def on_delivery_methods(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('pickup', 'delivery', 'both'):
        current_method = config.delivery_method
        if not current_method == action:
            config.set_value('delivery_method', action)
            msg = _('🏃‍♂️ Edit delivery methods')
            reply_markup = keyboards.delivery_methods_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_DELIVERY_METHODS
    elif action == 'back':
        return states.enter_delivery_options(_, bot, chat_id, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.DELIVERY)
@user_passes
def on_delivery_fee(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'add':
        return states.enter_delivery_fee_add(_, bot, chat_id, msg_id, query.id)
    elif action == 'back':
        return states.enter_delivery_fee(_, bot, chat_id, msg_id, query.id)
    elif action == 'vip':
        conf_value = not config.delivery_fee_for_vip
        config.set_value('delivery_fee_for_vip', conf_value)
        return states.enter_delivery_fee(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.DELIVERY)
@user_passes
def on_delivery_fee_add(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'all':
        user_data['delivery_fee_location'] = 'all'
        return states.enter_delivery_fee_enter(_, bot, chat_id, msg_id=msg_id, query_id=query.id)
    elif action == 'select':
        page = 1
        user_data['listing_page'] = page
        return states.enter_delivery_fee_location(_, bot, chat_id, msg_id, query.id, page)
    elif action == 'back':
        return states.enter_delivery_fee(_, bot, chat_id, msg_id, query.id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.DELIVERY)
@user_passes
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
        return states.enter_delivery_fee_enter(_, bot, chat_id, val, msg_id, query.id)
    elif action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_delivery_fee_location(_, bot, chat_id, msg_id, query.id, page)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.DELIVERY)
@user_passes
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
                return states.enter_delivery_fee_location(_, bot, chat_id, query.message.message_id, query.id, page)
        return states.enter_unknown_command(_, bot, query)
    delivery_text = update.message.text
    delivery_data = delivery_text.split('>')
    delivery_fee = delivery_data[0].strip()
    try:
        delivery_fee = int(delivery_fee)
    except ValueError:
        msg = _('Incorrect format')
        bot.send_message(msg, chat_id)
        return states.enter_delivery_fee_enter(_, bot, chat_id, for_location)
    try:
        delivery_min = delivery_data[1]
    except IndexError:
        delivery_min = 0
    else:
        delivery_min = int(delivery_min.strip())
    msg = _('Delivery fee was changed:')
    msg += '\n'
    currency_sym = get_currency_symbol()
    msg += _('Delivery fee: `{}{}`').format(delivery_fee, currency_sym)
    msg += '\n'
    msg += _('Delivery treshold: `{}{}`').format(delivery_min, currency_sym)
    if for_location == 'all':
        config.set_value('delivery_fee', delivery_fee)
        config.set_value('delivery_min', delivery_min)
        for loc in Location.select():
            loc.delivery_fee = delivery_fee
            loc.delivery_min = delivery_min
            loc.save()
        bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        return states.enter_delivery_fee_add(_, bot, chat_id)
    else:
        loc = Location.get(id=for_location)
        loc.delivery_fee = delivery_fee
        loc.delivery_min = delivery_min
        loc.save()
        bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        page = user_data['listing_page']
        return states.enter_delivery_fee_location(_, bot, chat_id, page=page)


@user_allowed(AllowedSetting.CATEGORIES)
@user_passes
def on_admin_categories(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    action = query.data
    if action == 'add':
        msg = _('Please enter the name of category')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.cancel_button(_))
        query.answer()
        return enums.ADMIN_CATEGORY_ADD
    elif action == 'back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    categories = ProductCategory.select(ProductCategory.title, ProductCategory.id).tuples()
    keyboard = keyboards.general_select_one_keyboard(_, categories)
    msg = _('Please select a category:')
    bot.edit_message_text(msg, chat_id, msg_id,
                          parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    query.answer()
    if action == 'products':
        return enums.ADMIN_CATEGORY_PRODUCTS_SELECT
    elif action == 'remove':
        return enums.ADMIN_CATEGORY_REMOVE_SELECT


@user_allowed(AllowedSetting.CATEGORIES)
@user_passes
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


@user_allowed(AllowedSetting.CATEGORIES)
@user_passes
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


@user_allowed(AllowedSetting.CATEGORIES)
@user_passes
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


@user_allowed(AllowedSetting.CATEGORIES)
@user_passes
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


@user_allowed(AllowedSetting.WAREHOUSE)
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
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    elif action == 'select':
        user_data['product_warehouse'] = {'product_id': val}
        product = Product.get(id=val)
        return states.enter_warehouse(_, bot, chat_id, product, msg_id, query.id)


@user_allowed(AllowedSetting.WAREHOUSE)
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


@user_allowed(AllowedSetting.WAREHOUSE)
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


@user_allowed(AllowedSetting.WAREHOUSE)
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


@user_allowed(AllowedSetting.WAREHOUSE)
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


@user_allowed(AllowedSetting.WAREHOUSE)
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


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_products(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    if data == 'bot_products_back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    elif data == 'bot_products_view':
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        if not products:
            query.answer(_('You don\'t have products'))
            return enums.ADMIN_PRODUCTS
        msg = _('Select a product to view')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.general_select_one_keyboard(_, products))
        query.answer()
        return enums.ADMIN_PRODUCTS_SHOW
    elif data == 'bot_products_add':
        bot.edit_message_text(chat_id=chat_id,
                              message_id=msg_id,
                              text=_('➕ Add product'),
                              reply_markup=keyboards.create_bot_product_add_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_ADD
    elif data == 'bot_products_edit':
        products = Product.select(Product.title, Product.id).where(Product.is_active==True).tuples()
        products_keyboard = keyboards.general_select_one_keyboard(_, products)
        msg = _('Select a product to edit')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN, reply_markup=products_keyboard)
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
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=_('Select a product which you want to remove'),
                              reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_DELETE_PRODUCT
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
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
        shortcuts.send_product_media(bot, product, chat_id)
        msg = messages.create_admin_product_description(_, product)
        msg += _('Select a product to view')
        bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN,
                         reply_markup=keyboards.general_select_one_keyboard(_, products))
        query.answer()
    return enums.ADMIN_PRODUCTS_SHOW


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
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
        product.is_active = False
        product.save()
        user_data['admin_product_edit'] = {'id': product.id}
        product_title = escape_markdown(product.title)
        msg = _('Edit product {}').format(product_title)
        msg += '\n'
        msg += _('_Note: product is disabled while editing_')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_edit(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    product_id = user_data['admin_product_edit']['id']
    product = Product.get(id=product_id)
    if action == 'back':
        product.is_active = True
        product.save()
        del user_data['admin_product_edit']
        products = Product.select(Product.title, Product.id).where(Product.is_active == True).tuples()
        msg = _('Select a product to edit')
        bot.edit_message_text(msg, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=keyboards.general_select_one_keyboard(_, products))
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_SELECT
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
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_edit_title(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    product_id = user_data['admin_product_edit']['id']
    product = Product.get(id=product_id)
    query = update.callback_query
    if query:
        if query.data == 'back':
            product_title = escape_markdown(product.title)
            msg = _('Edit product {}').format(product_title)
            bot.edit_message_text(msg, chat_id, query.message.message_id,
                                  reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                                  parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_PRODUCT_EDIT
        else:
            return states.enter_unknown_command(_, bot, query)
    else:
        product.title = update.message.text
        product.save()
        msg = _('Product\'s title has been updated')
        bot.send_message(chat_id, msg, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_edit_price_type(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    product_id = user_data['admin_product_edit']['id']
    product = Product.get(id=product_id)
    if action == 'text':
        prices_str = shortcuts.get_product_prices_str(_, product)
        bot.edit_message_text(prices_str, chat_id, msg_id, parse_mode=ParseMode.MARKDOWN)
        msg = _('Enter new product prices\none per line in the format\n*COUNT PRICE*, e.g. *1 10*')
        msg += '\n\n'
        currency_str = '{} {}'.format(*Currencies.CURRENCIES[config.currency])
        msg += _('Currency: {}').format(currency_str)
        reply_markup = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT_PRICES_TEXT
    elif action == 'select':
        msg = _('Select product price groups to use with this product:')
        product_groups = GroupProductCount.select().join(ProductGroupCount).where(ProductGroupCount.product == product)\
            .group_by(GroupProductCount.id)
        product_groups = [item.id for item in product_groups]
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        objects = []
        selected_ids = []
        for group_name, group_id in groups:
            is_picked = group_id in product_groups
            objects.append((group_name, group_id, is_picked))
            if is_picked:
                selected_ids.append(group_id)
        user_data['admin_product_edit']['groups_selected_ids'] = selected_ids
        user_data['admin_product_edit']['listing_page'] = 1
        keyboard = keyboards.general_select_keyboard(_, objects)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_PRICES_GROUP
    elif action == 'back':
        product_title = escape_markdown(product.title)
        msg = _('Edit product {}').format(product_title)
        keyboard = keyboards.create_bot_product_edit_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_edit_prices_group(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    selected_ids = user_data['admin_product_edit']['groups_selected_ids']
    if action == 'page':
        page = int(val)
        msg = _('Select product price groups to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        groups = [(group_name, group_id, group_id in selected_ids) for group_name, group_id in groups]
        user_data['admin_product_edit']['listing_page'] = page
        keyboard = keyboards.general_select_keyboard(_, groups, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_PRICES_GROUP
    elif action == 'select':
        group_id = int(val)
        if group_id in selected_ids:
            selected_ids.remove(group_id)
        else:
            selected_ids.append(group_id)
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        groups = [(group_name, group_id, group_id in selected_ids) for group_name, group_id in groups]
        msg = _('Select product price groups to use with this product:')
        page = user_data['admin_product_edit']['listing_page']
        keyboard = keyboards.general_select_keyboard(_, groups, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_EDIT_PRICES_GROUP
    else:
        if selected_ids:
            product_id = user_data['admin_product_edit']['id']
            product = Product.get(id=product_id)
            ProductCount.delete().where(ProductCount.product == product).execute()
            price_groups = GroupProductCount.select().where(GroupProductCount.id.in_(selected_ids))
            ProductGroupCount.delete().where(ProductGroupCount.product == product).execute()
            for price_group in price_groups:
                ProductGroupCount.create(product=product, price_group=price_group)
        msg = _('Product\'s price groups was updated!')
        keyboard = keyboards.create_bot_product_edit_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_edit_prices_text(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    product_id = user_data['admin_product_edit']['id']
    product = Product.get(id=product_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    if query:
        if query.data == 'back':
            product_title = escape_markdown(product.title)
            msg = _('Edit product {}').format(product_title)
            bot.edit_message_text(msg, chat_id, query.message.message_id,
                                  reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                                  parse_mode=ParseMode.MARKDOWN)
            return enums.ADMIN_PRODUCT_EDIT
        else:
            return states.enter_unknown_command(_, bot, query)
    else:
        prices_text = update.message.text
        prices_list = []
        try:
            for line in prices_text.split('\n'):
                count_str, price_str = line.split()
                count = int(count_str)
                price = float(price_str)
                prices_list.append((count, price))
        except ValueError:
            msg = _('Could not read prices, please try again')
        else:
            product.group_price = None
            product.save()
            ProductCount.delete().where(ProductCount.product == product).execute()
            ProductGroupCount.delete().where(ProductCount.product == product).execute()
            for count, price in prices_list:
                ProductCount.create(product=product, count=count, price=price)
            msg = _('Product\'s prices have been updated')
        bot.send_message(chat_id, msg, reply_markup=keyboards.create_bot_product_edit_keyboard(_),
                         parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_EDIT


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_edit_media(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    upd_msg = update.message
    msg_text = upd_msg.text
    chat_id = update.effective_chat.id
    product_id = user_data['admin_product_edit']['id']
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


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_delete_product(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, param = data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
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
                              message_id=msg_id,
                              text=_('🏪 My Products'),
                              reply_markup=keyboards.create_bot_products_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCTS
    elif action in ('page', 'select'):
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
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=_('Select a product which you want to remove'),
                              reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_DELETE_PRODUCT
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_add(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    if data == 'bot_product_back':
        msg = _('🏪 My Products')
        reply_markup = keyboards.create_bot_products_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_PRODUCTS
    elif data == 'bot_product_new':
        msg = _('Enter new product title')
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
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
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=_('Select a product which you want to activate again'),
                              reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_LAST_ADD
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_last_select(bot, update, user_data):
    query = update.callback_query
    data = query.data
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action, param = data.split('|')
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
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
        bot.edit_message_text(_('➕ Add product'), chat_id, msg_id,
                              reply_markup=keyboards.create_bot_product_add_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_ADD
    elif action in ('page', 'select'):
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
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                              text=_('Select a product which you want to activate again'),
                              reply_markup=products_keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_LAST_ADD
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_title(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    if query:
        if query.data == 'back':
            query = update.callback_query
            bot.edit_message_text(chat_id=chat_id,
                                  message_id=query.message.message_id,
                                  text=_('➕ Add product'),
                                  reply_markup=keyboards.create_bot_product_add_keyboard(_),
                                  parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_PRODUCT_ADD
        else:
            return states.enter_unknown_command(_, bot, query)
    title = update.message.text
    # initialize new product data
    user_data['add_product'] = {}
    user_data['add_product']['title'] = title
    msg = _('Add product prices:')
    keyboard = keyboards.create_product_price_type_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_ADD_PRODUCT_PRICES


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_add_product_prices(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'text':
        msg = _('Enter new product prices\none per line in the format\n*COUNT PRICE*, e.g. *1 10*')
        msg += '\n\n'
        currency_str = '{} {}'.format(*Currencies.CURRENCIES[config.currency])
        msg += _('Currency: {}').format(currency_str)
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICES_TEXT
    elif action == 'select':
        msg = _('Select product price groups to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        groups = [(group_name, group_id, False) for group_name, group_id in groups]
        user_data['add_product']['prices'] = {'groups': []}
        user_data['add_product']['listing_page'] = 1
        keyboard = keyboards.general_select_keyboard(_, groups)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICES_GROUP
    elif action == 'back':
        msg = _('➕ Add product')
        keyboard = keyboards.create_bot_product_add_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_ADD
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_price_group(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    action, val = query.data.split('|')
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    selected_ids = user_data['add_product']['prices']['groups']
    if action == 'page':
        page = int(val)
        msg = _('Select product price group to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        groups = [(group_name, group_id, group_id in selected_ids) for group_name, group_id in groups]
        user_data['add_product']['listing_page'] = page
        keyboard = keyboards.general_select_keyboard(_, groups, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICES_GROUP
    elif action == 'select':
        group_id = int(val)
        if group_id in selected_ids:
            selected_ids.remove(group_id)
        else:
            selected_ids.append(group_id)
        msg = _('Select product price group to use with this product:')
        groups = GroupProductCount.select(GroupProductCount.name, GroupProductCount.id).tuples()
        groups = [(group_name, group_id, group_id in selected_ids) for group_name, group_id in groups]
        page = user_data['add_product']['listing_page']
        user_data['add_product']['prices']['groups'] = selected_ids
        keyboard = keyboards.general_select_keyboard(_, groups, page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICES_GROUP
    else:
        print(selected_ids)
        if not selected_ids:
            msg = _('Add product prices:')
            keyboard = keyboards.create_product_price_type_keyboard(_)
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard)
            return enums.ADMIN_ADD_PRODUCT_PRICES
        msg = _('Send photos/videos for new product')
        keyboard = keyboards.create_product_media_keyboard(_)
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_PRODUCT_MEDIA


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
def on_product_price_text(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    if query:
        if query.data == 'back':
            msg = _('Add product prices:')
            keyboard = keyboards.create_product_price_type_keyboard(_)
            bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            query.answer()
            return enums.ADMIN_ADD_PRODUCT_PRICES
        else:
            return states.enter_unknown_command(_, bot, query)
    prices = update.message.text
    prices_list = []
    for line in prices.split('\n'):
        try:
            count_str, price_str = line.split()
            count = int(count_str)
            price = Decimal(price_str)
            prices_list.append((count, price))
        except ValueError:
            update.message.reply_text(
                text=_('Could not read prices, please try again'))
            return enums.ADMIN_PRODUCT_PRICES_TEXT

    user_data['add_product']['prices'] = {'list': prices_list}
    msg = _('Send photos/videos for new product')
    keyboard = keyboards.create_product_media_keyboard(_)
    bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_PRODUCT_MEDIA


@user_allowed(AllowedSetting.MY_PRODUCTS)
@user_passes
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
        price_groups = prices.get('groups')
        if price_groups is None:
            prices = prices['list']
            for count, price in prices:
                ProductCount.create(product=product, price=price, count=count)
        else:
            for group_id in price_groups:
                price_group = GroupProductCount.get(id=group_id)
                ProductGroupCount.create(product=product, price_group=price_group)
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


@user_allowed(AllowedSetting.LOCATIONS)
@user_passes
def on_locations(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action == 'bot_locations_back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
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


@user_allowed(AllowedSetting.LOCATIONS)
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
        currency_sym = get_currency_symbol()
        delivery_fee = location.delivery_fee if location.delivery_fee else config.delivery_fee
        delivery_min = location.delivery_min if location.delivery_fee else config.delivery_min
        msg += _('Delivery fee: `{}{}`').format(delivery_fee, currency_sym)
        msg += '\n'
        msg += _('Delivery threshold: `{}{}`').format(delivery_min, currency_sym)
        reply_markup = keyboards.location_detail_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_LOCATION_DETAIL
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.LOCATIONS)
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


@user_allowed(AllowedSetting.LOCATIONS)
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
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    update.message.reply_text(
        text=_('Admin command cancelled.'),
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN,
    )
    return enums.BOT_INIT


def on_admin_fallback(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    update.message.reply_text(
        text=_('Unknown input, type /cancel to exit admin mode'),
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN,
    )
    return enums.ADMIN_INIT


@user_allowed(AllowedSetting.WORKING_HOURS)
@user_passes
def on_admin_edit_working_hours(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        user_data['day_selected'] = val
        day_name = dict(WorkingHours.DAYS)[int(val)]
        msg = _('Please enter working time in format `12:00-18:00` for {}'.format(day_name))
        reply_markup = keyboards.cancel_button(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_ENTER_WORKING_HOURS
    elif action == 'back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.WORKING_HOURS)
@user_passes
def on_admin_enter_working_hours(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query:
        if query.data == 'back':
            del user_data['day_selected']
            return states.enter_working_days(_, bot, chat_id, query.message.message_id, query.id)
        else:
            return states.enter_unknown_command(_, bot, query)
    hours_str = update.message.text
    hours = hours_str.split('-')
    working_hours = []
    time_format = '%H:%M'
    if len(hours) == 2:
        for val in hours:
            val = val.strip().replace(' ', '')
            try:
                val = datetime.strptime(val, time_format)
            except ValueError:
                break
            else:
                working_hours.append(val)
    if not working_hours:
        msg = _('Incorrect time format. Please enter time in format  `12:00-18:00`')
        reply_markup = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_ENTER_WORKING_HOURS
    else:
        day = user_data['day_selected']
        day = int(day)
        open_time, close_time = working_hours
        try:
            working_hours = WorkingHours.get(day=day)
        except WorkingHours.DoesNotExist:
            WorkingHours.create(day=day, open_time=open_time, close_time=close_time)
        else:
            working_hours.open_time = open_time
            working_hours.close_time = close_time
            working_hours.save()
        day_repr = dict(WorkingHours.DAYS)[day]
        open_time, close_time = open_time.strftime(time_format), close_time.strftime(time_format)
        msg = _('{} working hours was set to `{}-{}`').format(day_repr, open_time, close_time)
        del user_data['day_selected']
    return states.enter_working_days(_, bot, chat_id, msg=msg)


@user_allowed(AllowedSetting.DISCOUNT)
@user_passes
def on_admin_add_discount(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query:
        if query.data == 'back':
            return states.enter_order_options(_, bot, chat_id, user_id, query.message.message_id, query.id)
        else:
            return states.enter_unknown_command(_, bot, query)
    discount = update.message.text
    discount = parse_discount(discount)
    if discount:
        discount, discount_min = discount
        config.set_value('discount', discount)
        config.set_value('discount_min', discount_min)
        msg = _('Discount was changed')
        return states.enter_order_options(_, bot, chat_id, user_id, msg=msg)
    else:
        msg = _('Invalid format')
        msg += '\n'
        currency_str, currency_sym = Currencies.CURRENCIES[config.currency]
        msg += _('Enter discount like:\n'
                 '50 > 500: all deals above 500{0} will be -50{0}\n'
                 '10% > 500: all deals above 500{0} will be -10%\n'
                 '*Current discount: {1} > {2}*').format(currency_sym, config.discount, config.discount_min)
        msg += '\n\n'
        msg += _('Currency: {} {}').format(currency_str, currency_sym)
        bot.send_message(chat_id, msg, reply_markup=keyboards.cancel_button(_), parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_ADD_DISCOUNT


@user_allowed(AllowedSetting.BOT_STATUS)
@user_passes
def on_admin_bot_status(bot, update, user_data):
    query = update.callback_query
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    action = query.data
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    if action in ('bot_status_on_off', 'bot_status_only_reg', 'bot_status_watch', 'bot_status_order'):
        if action == 'bot_status_on_off':
            value = not config.bot_on_off
            config.set_value(action, value)
        else:
            actions_map = {
                'bot_status_only_reg': 'only_for_registered', 'bot_status_watch': 'watch_non_registered',
                'bot_status_order': 'order_non_registered'
            }
            conf_name = actions_map[action]
            old_value = getattr(config, conf_name)
            if old_value:
                query.answer()
                return enums.ADMIN_BOT_STATUS
            for v in actions_map.values():
                config.set_value(v, False)
            config.set_value(conf_name, True)
        msg = _('⚡️ Bot Status')
        reply_markup = keyboards.create_bot_status_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_BOT_STATUS
    if action == 'bot_status_back':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ID_PROCESS)
@user_passes
def on_admin_edit_identification_stages(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, data = query.data.split('|')
    if action == 'id_back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    if action in ('id_toggle', 'id_delete', 'id_order_toggle'):
        stage = IdentificationStage.get(id=data)
        question = IdentificationQuestion.get(stage=stage)
        if action == 'id_toggle':
            stage.active = not stage.active
            stage.save()
        elif action == 'id_order_toggle':
            stage.for_order = not stage.for_order
            stage.save()
        elif action == 'id_delete':
            question.delete_instance(recursive=True)
            stage.delete_instance(recursive=True)
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.for_order, first_question))
        msg = _('👨 Edit identification process')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.edit_identification_keyboard(_, questions),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES
    if action == 'id_permissions':
        all_permissions = UserPermission.get_clients_permissions()
        stage = IdentificationStage.get(id=data)
        permissions = IdentificationPermission.select().where(IdentificationPermission.stage == stage)
        permissions = [perm.permission for perm in permissions]
        objects = []
        selected_ids = []
        for perm in all_permissions:
            is_picked = True if perm in permissions else False
            objects.append((perm.get_permission_display(), perm.id, is_picked))
            if is_picked:
                selected_ids.append(perm.id)
        user_data['admin_edit_identification'] = {'id': data, 'selected_ids': selected_ids}
        msg = _('Select special clients types for this question')
        reply_markup = keyboards.general_select_keyboard(_, objects)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_EDIT_IDENTIFICATION_PERMISSIONS
    if action in ('id_add', 'id_edit'):
        if action == 'id_add':
            user_data['admin_edit_identification'] = {'new': True}
            msg = ''
        else:
            stage = IdentificationStage.get(id=data)
            stage.active = False
            stage.save()
            user_data['admin_edit_identification'] = {'new': False, 'id': data}
            msg = _('_Note: identification stage is disabled while editing_')
            msg += '\n'
        msg += _('Select type of identification question')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_edit_identification_type_keyboard(_),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_IDENTIFICATION_QUESTION_TYPE
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ID_PROCESS)
@user_passes
def on_admin_edit_identification_permissions(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    selected_ids = user_data['admin_edit_identification']['selected_ids']
    if action == 'select':
        all_permissions = UserPermission.get_clients_permissions()
        val = int(val)
        if val in selected_ids:
            selected_ids.remove(val)
        else:
            selected_ids.append(val)
        objects = []
        for perm in all_permissions:
            is_picked = True if perm.id in selected_ids else False
            objects.append((perm.get_permission_display(), perm.id, is_picked))
        user_data['admin_edit_identification']['selected_ids'] = selected_ids
        msg = _('Select special clients types for this question')
        reply_markup = keyboards.general_select_keyboard(_, objects)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_EDIT_IDENTIFICATION_PERMISSIONS
    else:
        stage_id = user_data['admin_edit_identification']['id']
        stage = IdentificationStage.get(id=stage_id)
        permissions = UserPermission.select().where(UserPermission.id.in_(selected_ids))
        IdentificationPermission.delete().where(IdentificationPermission.stage == stage).execute()
        for perm in permissions:
            IdentificationPermission.create(stage=stage, permission=perm)
        query_msg = _('Special clients were set!')
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.for_order, first_question))
        msg = _('👨 Edit identification process')
        reply_markup = keyboards.edit_identification_keyboard(_, questions)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer(query_msg)
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES


@user_allowed(AllowedSetting.ID_PROCESS)
@user_passes
def on_admin_edit_identification_question_type(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    edit_options = user_data['admin_edit_identification']
    if action == 'back':
        if not edit_options['new']:
            stage_id = edit_options['id']
            stage = IdentificationStage.get(id=stage_id)
            stage.active = True
            stage.save()
        del user_data['admin_edit_identification']
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.for_order, first_question))
        msg = _('👨 Edit identification process')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.edit_identification_keyboard(_, questions),
                              parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES
    if action in ('photo', 'video'):
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
            msg += '\n'
            msg += _('Current questions:\n'
                    '{}\n{}').format(q_msg, msg)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_),
                              parse_mode=ParseMode.HTML)
        query.answer()
        return enums.ADMIN_EDIT_IDENTIFICATION_QUESTION
    elif action == 'text':
        msg = _('Select text question type')
        reply_markup = keyboards.identification_type_text_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES_TEXT
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.ID_PROCESS)
@user_passes
def on_admin_edit_identification_text_type(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    edit_options = user_data['admin_edit_identification']
    if action == 'text':
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
                    '{}\n\n{}').format(q_msg, msg)
        edit_options['type'] = action
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.cancel_button(_),
                              parse_mode=ParseMode.HTML)
        query.answer()
        return enums.ADMIN_EDIT_IDENTIFICATION_QUESTION
    elif action == 'back':
        msg = _('Select type of identification question')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_edit_identification_type_keyboard(_))
        return enums.ADMIN_EDIT_IDENTIFICATION_QUESTION_TYPE
    else:
        if action == 'phone':
            question = _('Please send your phone number')
        else:
            question = _('Please send your ID number')
        edit_options = user_data['admin_edit_identification']
        if edit_options['new']:
            stage = IdentificationStage.create(type=action)
            IdentificationQuestion.create(content=question, stage=stage)
            msg = _('Identification question has been created')
        else:
            stage = IdentificationStage.get(id=edit_options['id'])
            stage.type = action
            for q in stage.identification_questions:
                q.delete_instance()
            IdentificationQuestion.create(content=question, stage=stage)
            stage.active = True
            stage.save()
            msg = _('Identification question has been changed')
        questions = []
        for stage in IdentificationStage:
            first_question = stage.identification_questions[0]
            first_question = first_question.content
            questions.append((stage.id, stage.active, stage.for_order, first_question))
        bot.send_message(chat_id, msg, reply_markup=keyboards.edit_identification_keyboard(_, questions),
                         parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_EDIT_IDENTIFICATION_STAGES


@user_allowed(AllowedSetting.ID_PROCESS)
@user_passes
def on_admin_edit_identification_question(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query and query.data == 'back':
        msg_id = query.message.message_id
        msg = _('Select type of identification question')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_edit_identification_type_keyboard(_))
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
        for q in stage.identification_questions:
            q.delete_instance()
        for q_text in msg_text.split('\n'):
            if q_text:
                IdentificationQuestion.create(content=q_text, stage=stage)
        stage.active = True
        stage.save()
        print(edit_options['type'])
        msg = _('Identification question has been changed')
    questions = []
    for stage in IdentificationStage:
        first_question = stage.identification_questions[0]
        first_question = first_question.content
        questions.append((stage.id, stage.active, stage.for_order, first_question))
    bot.send_message(chat_id, msg, reply_markup=keyboards.edit_identification_keyboard(_, questions),
                     parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_EDIT_IDENTIFICATION_STAGES


@user_passes
def on_admin_reset_all_data(bot, update, user_data):
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
    elif action in ('no', 'back'):
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_reset_confirm(bot, update, user_data):
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
        shortcuts.init_bot_tables()
        msg = _('Database, session and all channel messages were deleted.')
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id, msg)
    elif action == 'no':
        return states.enter_settings(_, bot, chat_id, user_id, query.id, msg_id)
    elif action == 'back':
        msg = _('You are about to delete your database, session and all messages in channels. Is that correct?')
        reply_markup = keyboards.create_reset_all_data_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_RESET_DATA
    return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
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
        user_data['listing_page'] = 1
        return states.enter_price_groups_list(_, bot, chat_id, msg_id, query.id)
    elif action == 'back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    else:
        states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
def on_admin_product_price_groups_list(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        return states.enter_price_group_selected(_, bot, chat_id, val, msg_id, query.id)
    elif action == 'page':
        page = int(val)
        user_data['listing_page'] = page
        return states.enter_price_groups_list(_, bot, chat_id, msg_id, query.id, page=page)
    elif action == 'back':
        del user_data['listing_page']
        msg = _('💸 Product price groups')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_product_price_groups_keyboard(_))
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
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
    elif action == 'special_clients':
        group = GroupProductCount.get(id=val)
        msg = _('Please select special clients for group {}').format(group.name)
        permissions = [
            UserPermission.FAMILY, UserPermission.FRIEND, UserPermission.AUTHORIZED_RESELLER,
            UserPermission.VIP_CLIENT, UserPermission.CLIENT
        ]
        permissions = UserPermission.select().where(UserPermission.permission.in_(permissions))
        group_perms = GroupProductCountPermission.select().where(GroupProductCountPermission.price_group == group)
        group_perms = [group_perm.permission for group_perm in group_perms]
        special_clients = []
        selected_ids = []
        for perm in permissions:
            is_picked = perm in group_perms
            special_clients.append((perm.get_permission_display(), perm.id, is_picked))
            if is_picked:
                selected_ids.append(perm.id)
        user_data['admin_special_clients'] = {'group_id': val, 'selected_perms': selected_ids}
        reply_markup = keyboards.general_select_keyboard(_, special_clients)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_CLIENTS
    elif action == 'users':
        group = GroupProductCount.get(id=val)
        group_perms = GroupProductCountPermission.select().where(GroupProductCountPermission.price_group == group)
        if group_perms:
            permissions = [item.permission for item in group_perms]
        else:
            permissions = UserPermission.get_clients_permissions()
        users = User.select().where(User.banned == False, User.permission.in_(permissions)).order_by(User.permission)
        user_choices = []
        selected_ids = []
        for user in users:
            name = '{} - {}'.format(user.username, user.permission.get_permission_display())
            user_groups = [user_group.price_group for user_group in  user.price_groups]
            is_picked = group in user_groups
            user_choices.append((name, user.id, is_picked))
            if is_picked:
                selected_ids.append(user.id)
        user_data['admin_special_clients'] = {'selected_users': selected_ids, 'group_id': val}
        msg = _('Please select users for price group {}').format(group.name)
        reply_markup = keyboards.general_select_keyboard(_, user_choices)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_CLIENTS_USERS
    elif action in ('back', 'delete'):
        if action == 'delete':
            group = GroupProductCount.get(id=val)
            has_products = Product.select().join(ProductGroupCount).where(ProductGroupCount.price_group == group)\
                .group_by(Product.id).exists()
            if has_products:
                msg = _('Cannot delete group which has products, please remove price group from product')
                query.answer(msg, show_alert=True)
                return enums.ADMIN_PRODUCT_PRICE_GROUP_SELECTED
            else:
                ProductCount.delete().where(ProductCount.price_group == group).execute()
                ProductGroupCount.delete().where(ProductGroupCount.price_group == group).execute()
                UserGroupCount.delete().where(UserGroupCount.price_group == group).execute()
                GroupProductCountPermission.delete().where(GroupProductCountPermission.price_group == group).execute()
                group.delete_instance()
                msg = _('Group was successfully deleted!')
        else:
            msg = None
        page = user_data['listing_page']
        return states.enter_price_groups_list(_, bot, chat_id, msg_id, query.id, msg, page)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
def on_admin_product_price_group_clients(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        group_id = user_data['admin_special_clients']['group_id']
        group = GroupProductCount.get(id=group_id)
        msg = _('Please select special clients for group {}').format(group.name)
        permissions = UserPermission.get_clients_permissions()
        selected_ids = user_data['admin_special_clients']['selected_perms']
        val = int(val)
        if val in selected_ids:
            selected_ids.remove(val)
        else:
            selected_ids.append(val)
        special_clients = []
        for perm in permissions:
            is_picked = perm.id in selected_ids
            special_clients.append((perm.get_permission_display(), perm.id, is_picked))
        reply_markup = keyboards.general_select_keyboard(_, special_clients)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_CLIENTS
    elif action  in ('done', 'back'):
        group_id = user_data['admin_special_clients']['group_id']
        if action == 'done':
            group = GroupProductCount.get(id=group_id)
            GroupProductCountPermission.delete().where(GroupProductCountPermission.price_group == group).execute()
            for perm_id in user_data['admin_special_clients']['selected_perms']:
                perm = UserPermission.get(id=perm_id)
                GroupProductCountPermission.create(permission=perm, price_group=group)
        return states.enter_price_group_selected(_, bot, chat_id, group_id, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
def on_admin_product_price_group_clients_users(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    selected_ids = user_data['admin_special_clients']['selected_users']
    group_id = user_data['admin_special_clients']['group_id']
    group = GroupProductCount.get(id=group_id)
    if action in ('page', 'select'):
        group_perms = GroupProductCountPermission.select().where(GroupProductCountPermission.price_group == group)
        if group_perms:
            permissions = [item.permission for item in group_perms]
        else:
            permissions = UserPermission.get_clients_permissions()
        users = User.select().where(User.banned == False, User.permission.in_(permissions)).order_by(User.permission)
        if action == 'select':
            page = 1
            val = int(val)
            if val in selected_ids:
                selected_ids.remove(val)
            else:
                selected_ids.append(val)
        else:
            page = int(val)
        user_choices = []
        for user in users:
            name = '{} - {}'.format(user.username, user.permission.get_permission_display())
            is_picked = user.id in selected_ids
            user_choices.append((name, user.id, is_picked))
        user_data['admin_special_clients']['selected_users'] = selected_ids
        msg = _('Please select users for price group {}').format(group.name)
        reply_markup = keyboards.general_select_keyboard(_, user_choices, page_num=page)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_CLIENTS_USERS
    elif action == 'done':
        users = User.select().where(User.id.in_(selected_ids))
        UserGroupCount.delete().where(UserGroupCount.price_group == group).execute()
        for user in users:
            try:
                UserGroupCount.get(price_group=group, user=user)
            except UserGroupCount.DoesNotExist:
                UserGroupCount.create(price_group=group, user=user)
        del user_data['admin_special_clients']
        return states.enter_price_group_selected(_, bot, chat_id, group_id, msg_id, query.id)


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
def on_admin_product_price_group_change(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    if update.callback_query and update.callback_query.data == 'back':
        query = update.callback_query
        chat_id, msg_id = query.message.chat_id, query.message.message_id
        msg = _('💸 Product price groups')
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_product_price_groups_keyboard(_))
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP
    group_name = update.effective_message.text
    user_data['price_group']['name'] = group_name
    msg = _('Enter new product prices\none per line in the format\n*COUNT PRICE*, e.g. *1 10*')
    msg += '\n\n'
    currency_str = '{} {}'.format(*Currencies.CURRENCIES[config.currency])
    msg += _('Currency: {}').format(currency_str)
    keyboard = keyboards.cancel_button(_)
    bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_PRODUCT_PRICE_GROUP_PRICES


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
def on_admin_product_price_group_prices(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    chat_id = update.effective_chat.id
    query = update.callback_query
    if query:
        if query.data == 'back':
            del user_data['price_group']
            query = update.callback_query
            msg_id = query.message.message_id
            msg = _('💸 Product price groups')
            bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboards.create_product_price_groups_keyboard(_))
            query.answer()
            return enums.ADMIN_PRODUCT_PRICE_GROUP
        else:
            return states.enter_unknown_command(_, bot, query)
    group_prices = update.effective_message.text
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
        msg += '\n\n'
        currency_str = '{} {}'.format(*Currencies.CURRENCIES[config.currency])
        msg += _('Currency: {}').format(currency_str)
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return enums.ADMIN_PRODUCT_PRICE_GROUP_PRICES
    group_id = user_data['price_group']['edit']
    if group_id:
        group_name = user_data['price_group']['name']
        group = GroupProductCount.get(id=group_id)
        group.name = group_name
        group.save()
        ProductCount.delete().where(ProductCount.price_group == group).execute()
        for count, price in prices:
            ProductCount.create(count=count, price=price, price_group=group)
        group_name = escape(group_name)
        msg = _('Group <i>{}</i>  was successfully changed!').format(group_name)
        keyboard = keyboards.create_product_price_groups_keyboard(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return enums.ADMIN_PRODUCT_PRICE_GROUP
    else:
        user_data['price_group']['group_prices'] = prices
        msg = _('Please select special clients for group')
        permissions = [
            UserPermission.FAMILY, UserPermission.FRIEND, UserPermission.AUTHORIZED_RESELLER,
            UserPermission.VIP_CLIENT, UserPermission.CLIENT
        ]
        permissions = UserPermission.select().where(UserPermission.permission.in_(permissions))
        special_clients = [(perm.get_permission_display(), perm.id, False) for perm in permissions]
        user_data['price_group']['selected_perms_ids'] = []
        reply_markup = keyboards.general_select_keyboard(_, special_clients)
        bot.send_message(chat_id, msg, reply_markup=reply_markup)
        return enums.ADMIN_PRODUCT_PRICE_GROUP_PERMISSIONS_NEW


@user_allowed(AllowedSetting.PRICE_GROUPS)
@user_passes
def on_admin_product_price_group_permissions_new(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action, val = query.data.split('|')
    if action == 'select':
        msg = _('Please select special clients for group')
        permissions = UserPermission.get_clients_permissions()
        selected_ids = user_data['price_group']['selected_perms_ids']
        val = int(val)
        if val in selected_ids:
            selected_ids.remove(val)
        else:
            selected_ids.append(val)
        special_clients = [(perm.get_permission_display(), perm.id, perm.id in selected_ids) for perm in permissions]
        reply_markup = keyboards.general_select_keyboard(_, special_clients)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup)
        query.answer()
        return enums.ADMIN_PRODUCT_PRICE_GROUP_PERMISSIONS_NEW
    elif action == 'done':
        group_data = user_data['price_group']
        group_name = group_data['name']
        group_prices = group_data['group_prices']
        group_perms = group_data['selected_perms_ids']
        group = GroupProductCount.create(name=group_name)
        for count, price in group_prices:
            ProductCount.create(count=count, price=price, price_group=group)
        for perm_id in group_perms:
            perm = UserPermission.get(id=perm_id)
            GroupProductCountPermission.create(price_group=group, permission=perm)
        group_name = escape(group_name)
        msg = _('Group <i>{}</i>  was successfully added!').format(group_name)
        keyboard = keyboards.create_product_price_groups_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return enums.ADMIN_PRODUCT_PRICE_GROUP
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_btc_settings(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    btc_creds = BitcoinCredentials.select().first()
    wallet_id = btc_creds.wallet_id
    password = btc_creds.password
    if action == 'btc_wallet_id':
        msg = _('Current wallet ID: *{}*').format(wallet_id if wallet_id else '')
        msg += '\n'
        msg += _('Enter new BTC wallet ID:')
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BTC_NEW_WALLET_ID
    if action == 'btc_password':
        msg = _('Enter new password:')
        keyboard = keyboards.cancel_button(_)
        bot.send_message(chat_id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_BTC_NEW_PASSWORD
    if action == 'btc_back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    if action == 'btc_disable':
        btc_creds.enabled = False
        btc_creds.save()
    elif action == 'btc_enable':
        btc_status_msg = shortcuts.check_btc_status(_, wallet_id, password)
        if btc_status_msg:
            msg = _('Couldn\'t enable btc payments. Reason:')
            msg += '\n'
            msg += btc_status_msg
            query.answer(btc_status_msg, show_alert=True)
            return enums.ADMIN_BTC_PAYMENTS
        btc_creds.enabled = True
        btc_creds.save()
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


@user_passes
def on_admin_btc_new_wallet_id(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    btc_creds = BitcoinCredentials.select().first()
    btc_enabled = btc_creds.enabled
    msg = _('💰 Bitcoin payments')
    msg += '\n'
    keyboard = keyboards.create_btc_settings_keyboard(_, btc_enabled)
    query = update.callback_query
    btc_password = btc_creds.password
    if query:
        if query.data == 'back':
            btc_wallet = btc_creds.wallet_id
            msg += _('Status: *{}*').format(_('Enabled') if btc_enabled else _('Disabled'))
            msg += '\n'
            msg += _('Wallet ID: *{}*').format(btc_wallet if btc_wallet else '')
            msg += '\n'
            msg += _('Password set: {}').format('Yes' if btc_password else 'No')
            bot.edit_message_text(msg, query.message.chat_id, query.message.message_id,
                                  reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            query.answer()
        else:
            return states.enter_unknown_command(_, bot, query)
    else:
        wallet_id = update.message.text
        btc_creds.wallet_id = wallet_id
        btc_creds.enabled = False
        btc_creds.save()
        msg += _('Status: *{}*').format(_('Enabled') if btc_enabled else _('Disabled'))
        msg += '\n'
        msg += _('Wallet ID: *{}*').format(wallet_id)
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_password else 'No')
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_BTC_PAYMENTS


@user_passes
def on_admin_btc_new_password(bot, update, user_data):
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
    if query:
        if query.data == 'back':
            btc_password = btc_creds.password
            msg += _('Status: *{}*').format(_('Enabled') if btc_enabled else _('Disabled'))
            msg += '\n'
            msg += _('Wallet ID: *{}*').format(btc_wallet if btc_wallet else '')
            msg += '\n'
            msg += _('Password set: {}').format('Yes' if btc_password else 'No')
            bot.edit_message_text(msg, query.message.chat_id, query.message.message_id,
                                  reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            query.answer()
        else:
            return states.enter_unknown_command(_, bot, query)
    else:
        btc_password = update.message.text
        btc_creds.password = btc_password
        btc_creds.enabled = False
        btc_creds.save()
        msg += _('Status: *{}*').format(_('Enabled') if btc_enabled else _('Disabled'))
        msg += '\n'
        msg += _('Wallet ID: *{}*').format(btc_wallet if btc_wallet else '')
        msg += '\n'
        msg += _('Password set: {}').format('Yes' if btc_password else 'No')
        bot.send_message(update.effective_chat.id, msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return enums.ADMIN_BTC_PAYMENTS


@user_passes
def on_admin_change_currency(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    data = query.data
    if data in Currencies.CURRENCIES:
        CurrencyConverter().fetch_update_currencies()
        rate = CurrencyRates.get(currency=data)
        msg = _('When currency changed, all product prices, price groups, delivery fees and discount would be converted.')
        msg += '\n'
        msg += _('{} rate to {}: *{}*').format(Currencies.CURRENCIES[Currencies.DOLLAR][0], Currencies.CURRENCIES[data][0], rate.dollar_rate)
        msg += '\n'
        updated_str = config.currencies_last_updated.strftime('%H:%M %b %d')
        msg += _('Rate was updated at: {}').format(updated_str)
        msg += '\n'
        msg += _('Are you sure?')
        user_data['admin_currency_change'] = data
        keyboard = keyboards.are_you_sure_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_SET_CURRENCIES_CONFIRM
    elif data == 'back':
        return states.enter_order_options(_, bot, chat_id, user_id, msg_id, query.id)
    else:
        return states.enter_unknown_command(_, bot, query)


@user_passes
def on_admin_change_currency_confirm(bot, update, user_data):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    action = query.data
    if action in ('yes', 'no'):
        if action == 'yes':
            currency = user_data['admin_currency_change']
            old_currency = config.currency
            converter = CurrencyConverter()
            converter.fetch_update_currencies()
            for product_count in ProductCount.select():
                price = product_count.price
                new_price = converter.convert_currencies(price, old_currency, currency)
                product_count.price = new_price
                product_count.save()
            for location in Location.select().where(Location.delivery_fee.is_null(False)):
                delivery_fee = converter.convert_currencies(location.delivery_fee, old_currency, currency)
                delivery_min = converter.convert_currencies(location.delivery_min, old_currency, currency)
                location.delivery_min = delivery_min
                location.delivery_fee = delivery_fee
                location.save()
            delivery_fee = converter.convert_currencies(config.delivery_fee, old_currency, currency)
            delivery_min = converter.convert_currencies(config.delivery_min, old_currency, currency)
            config.set_value('delivery_fee', delivery_fee)
            config.set_value('delivery_min', delivery_min)
            config.set_value('currency', currency)
            msg = _('Currency was set to *{} {}*').format(*Currencies.CURRENCIES[currency])
        else:
            del user_data['admin_currency_change']
            currency = config.currency
            currency_name, currency_symbol = Currencies.CURRENCIES[currency]
            msg = _('Current currency: *{} {}*'.format(currency_name, currency_symbol))
            msg += '\n'
            msg += _('Select new currency:')
        reply_markup = keyboards.create_currencies_keyboard(_)
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        query.answer()
        return enums.ADMIN_SET_CURRENCIES
    return states.enter_unknown_command(_, bot, query)


@user_passes
def on_start_btc_processing(bot, update):
    user_id = get_user_id(update)
    _ = get_trans(user_id)
    query = update.callback_query
    order_id = query.data.split('|')[1]
    try:
        BtcProc.get(order_id=order_id)
    except BtcProc.DoesNotExist:
        order = Order.get(id=order_id)
        set_btc_proc(order.id)
        process_btc_payment(bot, order)
        chat_id, msg_id = query.message.chat_id, query.message.message_id
        shortcuts.delete_channel_msg(bot, chat_id, msg_id)
        query.answer()
    else:
        msg = _('Process is running already.')
        query.answer(msg, show_alert=True)



