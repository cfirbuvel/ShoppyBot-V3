import gettext
import os
from functools import wraps

from telegram.ext import ConversationHandler
from .keyboards import start_btn
from .helpers import get_user_id, get_locale, config, cat, get_username, get_trans
from .models import User, UserPermission, AllowedSetting
from .states import enter_menu


def user_passes(func):

    @wraps(func)
    def wrapper(bot, update, user_data, *args, **kwargs):
        user_id = get_user_id(update)
        passes_test = True
        username = get_username(update)
        locale = get_locale(update)
        chat_id = update.effective_chat.id
        try:
            user = User.get(telegram_id=user_id)
        except User.DoesNotExist:
            default_permission = UserPermission.get(permission=UserPermission.NOT_REGISTERED)
            user = User(telegram_id=user_id, username=username, locale=locale, permission=default_permission,
                        currency=config.currency)
            user.save()
        else:
            if username != user.username:
                user.username = username
                user.save()
        # _ = gettext.gettext if locale == 'en' else cat.gettext
        _ = get_trans(user_id)
        query = update.callback_query
        if query:
            bot.answer_callback_query(query.id)
        if not username:
            caption = _('Please create username to continue using bot')
            reply_markup = start_btn(_)
            if os.path.isfile(config.username_gif):
                with open(config.username_gif, 'rb') as animation:
                    bot.send_animation(chat_id, animation, caption=caption, reply_markup=reply_markup)
            else:
                bot.send_animation(chat_id, config.username_gif, caption=caption, reply_markup=reply_markup)
            return ConversationHandler.END
        if user.banned:
            passes_test = False
            msg = _('You have been banned.')
        if passes_test:
            if not config.bot_on_off:
                if not user.is_admin:
                    passes_test = False
                    first_name = update.effective_user.first_name
                    msg = _('Sorry {}, the bot is currently switched off.').format(first_name)
        if passes_test:
            return func(bot, update, user_data)
        chat_id = update.effective_chat.id
        if query:
            bot.edit_message_text(msg, chat_id, query.message.message_id)
        else:
            bot.send_message(chat_id, msg)
        return ConversationHandler.END
    return wrapper


def user_allowed(setting):

    def decorator(func):
        @wraps(func)
        def wrapper(bot, update, user_data):
            user_id = get_user_id(update)
            user = User.get(telegram_id=user_id)
            if user.is_logistic_manager:
                try:
                    AllowedSetting.get(user=user, setting=setting)
                except AllowedSetting.DoesNotExist:
                    _ = get_trans(user_id)
                    msg = _('You don\'t have permission to use this menu')
                    query = update.query
                    chat_id = update.effective_chat.id
                    if query:
                        bot.edit_message_text(msg, chat_id, query.message.message_id)
                        query_id = query.id
                    else:
                        bot.send_message(chat_id, msg)
                        query_id = None
                    return enter_menu(bot, update, user_data, query_id=query_id)
            return func(bot, update, user_data)
        return wrapper

    return decorator