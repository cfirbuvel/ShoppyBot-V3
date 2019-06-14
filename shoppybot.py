#! /usr/bin/env python3
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, Filters, MessageHandler, Updater, \
    Handler

from src import admin_handlers, courier_handlers, handlers, enums, shortcuts
from src.helpers import config, get_user_id, get_channel_trans
from src.shortcuts import send_lottery_messages, manage_lottery_participants, send_channel_advertisments

# from src.shortcuts import on_drop_order, make_confirm, make_unconfirm

from src.models import create_tables, close_db
from src.btc_wrapper import wallet_enable_hd
from src.btc_settings import BtcSettings
from src.btc_processor import start_orders_processing

# will be called when conversation context is lost (e.g. bot is restarted)
# and the user clicks menu buttons


def close_db_on_signal(signum, frame):
    close_db()


def error_callback(bot, update, error):
    raise error


def main():
    user_conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', handlers.on_start, pass_user_data=True),
            CallbackQueryHandler(handlers.on_start, pattern='^start_bot', pass_user_data=True),
            CallbackQueryHandler(handlers.on_menu, pattern='^(menu|product)', pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_courier_menu, pattern='^courier_menu', pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_courier_chat, pattern='^courier_chat', pass_user_data=True),
            CallbackQueryHandler(handlers.on_chat_with_courier, pattern='^client_chat', pass_user_data=True),
            CallbackQueryHandler(handlers.on_open_chat_msg, pattern='^client_read_msg', pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_open_chat_msg, pattern='^courier_read_msg', pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_client_waiting_keyboard, pattern='^courier_ping', pass_user_data=True),
            CallbackQueryHandler(handlers.on_client_order_delivered, pattern='^delivered_order', pass_user_data=True)
        ],
        states={
            enums.BOT_INIT: [
                CommandHandler('start', handlers.on_start, pass_user_data=True),
                CallbackQueryHandler(handlers.on_menu, pattern='^(menu|product)',
                                     pass_user_data=True)
            ],
            enums.COURIER_STATE_INIT: [
                CallbackQueryHandler(courier_handlers.on_courier_menu, pattern='^courier_menu', pass_user_data=True),
            ],
            enums.COURIER_STATE_PING: [
                CallbackQueryHandler(courier_handlers.on_courier_ping_client, pattern='^(back|now|soon)', pass_user_data=True)
            ],
            enums.COURIER_STATE_PING_SOON: [
                CallbackQueryHandler(courier_handlers.on_courier_ping_client_soon, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, courier_handlers.on_courier_ping_client_soon, pass_user_data=True)
            ],
            enums.COURIER_STATE_CONFIRM_ORDER: [
                CallbackQueryHandler(courier_handlers.on_courier_confirm_order, pattern='^(yes|no)', pass_user_data=True)
            ],
            enums.COURIER_STATE_CONFIRM_REPORT: [
                CallbackQueryHandler(courier_handlers.on_courier_confirm_report, pattern='^(yes|no)', pass_user_data=True)
            ],
            enums.COURIER_STATE_CONFIRM_DROPPED: [
                CallbackQueryHandler(courier_handlers.on_drop_order, pattern='^(yes|no)', pass_user_data=True)
            ],
            enums.COURIER_STATE_REPORT_REASON: [
                MessageHandler(Filters.text, courier_handlers.on_courier_enter_reason, pass_user_data=True),
                CallbackQueryHandler(courier_handlers.on_courier_enter_reason, pattern='^back', pass_user_data=True)
            ],
            enums.COURIER_STATE_CHAT: [
                CallbackQueryHandler(courier_handlers.on_courier_chat, pattern='^courier_chat', pass_user_data=True)
            ],
            enums.COURIER_STATE_CHAT_SEND: [
                MessageHandler(Filters.text | Filters.photo | Filters.video, courier_handlers.on_courier_chat_send, pass_user_data=True),
                CallbackQueryHandler(courier_handlers.on_courier_chat_send, pattern='^back', pass_user_data=True)
            ],
            enums.BOT_REGISTRATION: [
                CallbackQueryHandler(handlers.on_registration, pattern='^(register|cancel)',
                                     pass_user_data=True)
            ],
            enums.BOT_REGISTRATION_REPEAT: [
                CallbackQueryHandler(handlers.on_registration_repeat, pattern='^(yes|no)',
                                     pass_user_data=True)
            ],
            enums.BOT_IDENTIFICATION: [
                CallbackQueryHandler(handlers.on_registration_identification, pattern='^(back|cancel)',
                                     pass_user_data=True),
                MessageHandler(Filters.text | Filters.photo | Filters.video, handlers.on_registration_identification,
                               pass_user_data=True)
            ],
            enums.BOT_IDENTIFICATION_PHONE: [
                MessageHandler(Filters.text | Filters.contact, handlers.on_registration_identification_phone,
                               pass_user_data=True)
            ],
            enums.BOT_CHANNELS: [
                CallbackQueryHandler(handlers.on_channels, pattern='^back',
                                     pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_SHIPPING: [
                CallbackQueryHandler(handlers.on_order_delivery, pattern='^(back|pickup|delivery)',
                                     pass_user_data=True),
            ],
            enums.BOT_CHECKOUT_LOCATION: [
                CallbackQueryHandler(handlers.on_order_locations, pattern='^(select|page|back|cancel)',
                                     pass_user_data=True),
            ],
            enums.BOT_CHECKOUT_ADDRESS: [
                MessageHandler(Filters.text | Filters.location, handlers.on_order_delivery_address,
                               pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_DATETIME_SELECT: [
                CallbackQueryHandler(handlers.on_order_datetime_select, pattern='^(now|datetime|back|cancel)',
                                     pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_DATE_SELECT: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar',
                                     pass_user_data=True),
                CallbackQueryHandler(handlers.on_order_date_select, pattern='^(day|year|month|back|cancel)',
                                     pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_TIME_SELECT: [
                CallbackQueryHandler(handlers.on_time_picker_change, pattern='^time_picker',
                                     pass_user_data=True),
                CallbackQueryHandler(handlers.on_order_time_select, pattern='^(done|back|cancel)',
                                     pass_user_data=True)
            ],
            # enums.BOT_CHECKOUT_PHONE_NUMBER: [
            #     MessageHandler(Filters.contact | Filters.text,
            #                    handlers.on_order_phone_number, pass_user_data=True),
            # ],
            enums.BOT_CHECKOUT_IDENTIFY: [
                CallbackQueryHandler(handlers.on_order_identification, pattern='^(back|cancel)',
                                     pass_user_data=True),
                MessageHandler(Filters.text | Filters.photo | Filters.video, handlers.on_order_identification,
                               pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_IDENTIFY_PHONE: [
                 MessageHandler(Filters.contact | Filters.text,
                                handlers.on_order_identification_phone_number, pass_user_data=True),
            ],
            enums.BOT_CHECKOUT_PAYMENT_TYPE: [
                CallbackQueryHandler(handlers.on_order_payment_type, pattern='^(btc|delivery|back|cancel)',
                                     pass_user_data=True),
            ],
            enums.BOT_BTC_CONVERSION_FAILED: [
                CallbackQueryHandler(handlers.on_order_btc_conversion_failed, pattern='^(back|cancel|try_again)',
                                     pass_user_data=True),
            ],
            enums.BOT_GENERATING_ADDRESS_FAILED: [
                CallbackQueryHandler(handlers.on_order_generating_address_failed, pattern='^(back|cancel|try_again)',
                                     pass_user_data=True),
            ],
            enums.BOT_BTC_TOO_LOW: [
                CallbackQueryHandler(handlers.on_order_btc_too_low, pattern='^(back|cancel|try_again)', pass_user_data=True),
            ],
            enums.BOT_ORDER_CONFIRMATION: [
                CallbackQueryHandler(handlers.on_order_confirm, pattern='^(back|cancel|confirm)', pass_user_data=True),
            ],
            enums.BOT_LANGUAGE_CHANGE: [
                CallbackQueryHandler(handlers.on_bot_language_change, pattern='^(back|iw|en)',
                                     pass_user_data=True),
            ],
            enums.BOT_CURRENCY_CHANGE: [
                CallbackQueryHandler(handlers.on_bot_currency_change, pattern='^(USD|ILS|EUR|GPB|back)', pass_user_data=True)
            ],
            enums.BOT_MY_ORDERS: [
                CallbackQueryHandler(handlers.on_menu, pattern='product', pass_user_data=True),
                CallbackQueryHandler(handlers.on_my_orders, pattern='^(back|by_date|last_order)', pass_user_data=True)
            ],
            enums.BOT_MY_ORDERS_DATE: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(handlers.on_my_order_date, pattern='^(back|day|month|year)', pass_user_data=True)
            ],
            enums.BOT_MY_LAST_ORDER: [
                CallbackQueryHandler(handlers.on_my_last_order, pattern='^(back|cancel|show)', pass_user_data=True)
            ],
            enums.BOT_MY_LAST_ORDER_CANCEL: [
                CallbackQueryHandler(handlers.on_my_last_order_cancel, pattern='^(yes|no)', pass_user_data=True)
            ],
            enums.BOT_MY_ORDERS_SELECT:[
                CallbackQueryHandler(handlers.on_my_order_select, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.BOT_CHAT_ORDERS: [
                CallbackQueryHandler(handlers.on_bot_chat_orders, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.BOT_CHAT_ORDER_SELECTED: [
                CallbackQueryHandler(handlers.on_bot_chat_order_selected, pattern='^(start|back)', pass_user_data=True)
            ],
            enums.BOT_CHAT_WITH_COURIER: [
                CallbackQueryHandler(handlers.on_chat_with_courier, pattern='^client_chat', pass_user_data=True)
            ],
            enums.BOT_CHAT_SEND: [
                MessageHandler(Filters.text | Filters.video | Filters.photo, handlers.on_chat_send, pass_user_data=True),
                CallbackQueryHandler(handlers.on_chat_send, pattern='^back', pass_user_data=True)
            ],
            enums.BOT_PRODUCT_CATEGORIES: [
                CallbackQueryHandler(handlers.on_product_categories, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.BOT_ORDER_DELIVERED: [
                CallbackQueryHandler(handlers.on_client_order_delivered, pattern='^delivered_order', pass_user_data=True)
            ],
            enums.BOT_ORDER_REVIEW: [
                CallbackQueryHandler(handlers.on_order_review, pattern='^review', pass_user_data=True)
            ],
            enums.BOT_ORDER_REVIEW_FEW_WORDS: [
                CallbackQueryHandler(handlers.on_order_review_few_words, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, handlers.on_order_review_few_words, pass_user_data=True)
            ],
            #
            # admin states
            #
            enums.ADMIN_MENU: [
                CallbackQueryHandler(admin_handlers.on_settings_menu, pattern='^settings', pass_user_data=True)],
            enums.ADMIN_STATISTICS: [
                CallbackQueryHandler(admin_handlers.on_statistics_menu, pattern='^(stats|back)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_GENERAL: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_statistics_general, pattern='^(back|day|month|year)', pass_user_data=True),
            ],
            enums.ADMIN_STATISTICS_GENERAL_ORDER_SELECT: [
                CallbackQueryHandler(admin_handlers.on_statistics_general_order_select, pattern='^(page|back|select)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_COURIERS: [
                CallbackQueryHandler(admin_handlers.on_statistics_courier_select, pattern='^(back|page|select)',  pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_COURIERS_DATE: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_statistics_couriers, pattern='^(back|day|month|year)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_COURIER_ORDER_SELECT: [
                CallbackQueryHandler(admin_handlers.on_statistics_courier_order_select, pattern='^(back|page|select)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_LOCATIONS: [
                CallbackQueryHandler(admin_handlers.on_statistics_locations_select, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_LOCATIONS_DATE: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_statistics_locations, pattern='^(back|year|month|day)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_LOCATION_ORDER_SELECT: [
                CallbackQueryHandler(admin_handlers.on_statistics_locations_order_select, pattern='^(back|select|page)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_USERS: [
                CallbackQueryHandler(admin_handlers.on_statistics_users, pattern='^(clients|back)', pass_user_data=True),
            ],
            enums.ADMIN_STATISTICS_ALL_CLIENTS: [
                CallbackQueryHandler(admin_handlers.on_statistics_all_clients, pattern='^(back|select|search)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_USER_SEARCH: [
                CallbackQueryHandler(admin_handlers.on_statistics_user_search, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_statistics_user_search, pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_USER_SELECT: [
                CallbackQueryHandler(admin_handlers.on_statistics_user_select, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_USER_SELECT_DATE: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_statistics_user_select_date, pattern='^(back|year|month|day)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_USER_ORDER_SELECT: [
                CallbackQueryHandler(admin_handlers.on_statistics_user_order_select, pattern='^(back|select|page)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_TOP_CLIENTS: [
                CallbackQueryHandler(admin_handlers.on_statistics_top_clients, pattern='^(back|top)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_TOP_CLIENTS_PRODUCT: [
                CallbackQueryHandler(admin_handlers.on_top_users_by_product, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_TOP_CLIENTS_LOCATION: [
                CallbackQueryHandler(admin_handlers.on_top_users_by_location, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_STATISTICS_TOP_CLIENTS_DATE: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_top_by_date, pattern='^(back|year|month|day)', pass_user_data=True)
            ],
            enums.ADMIN_BOT_SETTINGS: [
                CallbackQueryHandler(admin_handlers.on_bot_settings_menu, pattern='^bot_settings', pass_user_data=True)
            ],
            enums.ADMIN_COURIERS: [
                CallbackQueryHandler(admin_handlers.on_couriers, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_COURIER_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_courier_detail, pattern='^courier_details', pass_user_data=True)
            ],
            enums.ADMIN_COURIER_LOCATIONS: [
                CallbackQueryHandler(admin_handlers.on_courier_locations, pattern='^(done|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_COURIER_WAREHOUSE_PRODUCTS: [
                CallbackQueryHandler(admin_handlers.on_courier_warehouse_products, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_COURIER_WAREHOUSE_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_courier_warehouse_detail, pattern='^(back|edit)', pass_user_data=True)
            ],
            enums.ADMIN_COURIER_WAREHOUSE_EDIT: [
                CallbackQueryHandler(admin_handlers.on_courier_warehouse_edit, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_courier_warehouse_edit, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_WORKING_HOURS: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_working_hours, pattern='^(back|select)', pass_user_data=True)
            ],
            enums.ADMIN_ENTER_WORKING_HOURS: [
                CallbackQueryHandler(admin_handlers.on_admin_enter_working_hours, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_enter_working_hours, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_MESSAGES: [
                CallbackQueryHandler(admin_handlers.on_edit_messages, pattern='^edit_msg', pass_user_data=True)
            ],
            enums.ADMIN_EDIT_MESSAGES_ENTER: [
                CallbackQueryHandler(admin_handlers.on_edit_messages_enter, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_edit_messages_enter, pass_user_data=True)
            ],
            enums.ADMIN_LOCATIONS: [
                CallbackQueryHandler(admin_handlers.on_locations, pattern='^bot_locations', pass_user_data=True)
            ],
            enums.ADMIN_LOCATION_ADD: [
                CallbackQueryHandler(admin_handlers.on_location_add, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_location_add, pass_user_data=True)
            ],
            enums.ADMIN_LOCATIONS_VIEW: [
                CallbackQueryHandler(admin_handlers.on_locations_view, pattern='^back|page|select', pass_user_data=True)
            ],
            enums.ADMIN_LOCATION_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_location_detail, pattern='^back|remove', pass_user_data=True)
            ],
            enums.ADMIN_ORDERS: [
                CallbackQueryHandler(admin_handlers.on_admin_orders, pattern='(^finished|^pending|^back)', pass_user_data=True)
            ],
            enums.ADMIN_ORDERS_PENDING_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_orders_pending_select, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_ORDERS_FINISHED_DATE: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_admin_orders_finished_date, pattern='^(back|day|month|year)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_ORDERS_FINISHED_LIST: [
                CallbackQueryHandler(admin_handlers.on_admin_orders_finished_list, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_ORDERS_FINISHED_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_orders_finished_select, pattern='^(send|back)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCTS: [
                CallbackQueryHandler(admin_handlers.on_products, pattern='^bot_products', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCTS_SHOW: [
                CallbackQueryHandler(admin_handlers.on_show_product, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_ADD: [
                CallbackQueryHandler(admin_handlers.on_product_add, pattern='^bot_product', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_LAST_ADD: [
                CallbackQueryHandler(admin_handlers.on_product_last_select, pattern='^(done|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_SELECT: [
                CallbackQueryHandler(admin_handlers.on_product_edit_select, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT: [
                CallbackQueryHandler(admin_handlers.on_product_edit, pattern='^(back|title|price|media)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_TITLE: [
                CallbackQueryHandler(admin_handlers.on_product_edit_title, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_edit_title, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_PRICES: [
                CallbackQueryHandler(admin_handlers.on_product_edit_price_type, pattern='^(back|text|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_PRICES_TEXT: [
                CallbackQueryHandler(admin_handlers.on_product_edit_prices_text, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_edit_prices_text, pass_user_data=True),
            ],
            enums.ADMIN_PRODUCT_EDIT_PRICES_GROUP: [
                CallbackQueryHandler(admin_handlers.on_product_edit_prices_group, pattern='^(done|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_MEDIA: [
                MessageHandler(Filters.text | Filters.photo | Filters.video, admin_handlers.on_product_edit_media,
                               pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel),
            ],
            enums.ADMIN_PRODUCT_TITLE: [
                CallbackQueryHandler(
                    admin_handlers.on_product_title, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_title,
                               pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel),
            ],
            enums.ADMIN_ADD_PRODUCT_PRICES: [
                CallbackQueryHandler(admin_handlers.on_add_product_prices, pattern='^(back|text|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICES_TEXT: [
                CallbackQueryHandler(admin_handlers.on_product_price_text, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_price_text, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PRODUCT_PRICES_GROUP: [
                CallbackQueryHandler(admin_handlers.on_product_price_group, pattern='^(done|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_MEDIA: [
                MessageHandler(Filters.text | Filters.photo | Filters.video, admin_handlers.on_product_media,
                               pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel),
            ],
            enums.ADMIN_DELETE_PRODUCT: [
                CallbackQueryHandler(admin_handlers.on_delete_product, pattern='^(done|page|select)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_WAREHOUSE: [
                CallbackQueryHandler(admin_handlers.on_warehouse, pattern='^warehouse', pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_PRODUCTS: [
                CallbackQueryHandler(admin_handlers.on_warehouse_products, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_COURIERS: [
                CallbackQueryHandler(admin_handlers.on_warehouse_couriers, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_PRODUCT_EDIT: [
                CallbackQueryHandler(admin_handlers.on_warehouse_product_credits, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_warehouse_product_credits, pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_COURIER_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_warehouse_courier_detail, pattern='^(back|edit)', pass_user_data=True),
            ],
            enums.ADMIN_WAREHOUSE_COURIER_EDIT: [
                CallbackQueryHandler(admin_handlers.on_warehouse_courier_edit, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_warehouse_courier_edit, pass_user_data=True)
            ],
            enums.ADMIN_CATEGORIES: [
                CallbackQueryHandler(admin_handlers.on_admin_categories, pattern='^(back|add|edit|products|remove)', pass_user_data=True),
            ],
            enums.ADMIN_CATEGORY_ADD: [
                CallbackQueryHandler(admin_handlers.on_admin_category_add, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_category_add, pass_user_data=True)
            ],
            enums.ADMIN_CATEGORY_EDIT: [
                CallbackQueryHandler(admin_handlers.on_admin_category_edit, pattern='^(back|select|page)', pass_user_data=True),
            ],
            enums.ADMIN_CATEGORY_EDIT_NAME: [
                CallbackQueryHandler(admin_handlers.on_admin_category_edit_name, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_category_edit_name, pass_user_data=True)
            ],
            enums.ADMIN_CATEGORY_PRODUCTS_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_category_products_select, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_CATEGORY_PRODUCTS_ADD: [
                CallbackQueryHandler(admin_handlers.on_admin_category_products_add, pattern='^(done|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_CATEGORY_REMOVE_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_category_remove, pattern='^(back|select)', pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS: [
                CallbackQueryHandler(admin_handlers.on_channels, pattern='^bot_channels', pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS_LANGUAGE: [
                CallbackQueryHandler(admin_handlers.on_channels_language, pattern='^(back|iw|en)', pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS_VIEW: [
                CallbackQueryHandler(admin_handlers.on_channels_view, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS_DETAILS: [
                CallbackQueryHandler(admin_handlers.on_channel_details, pattern='^(back|edit|remove)', pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS_SET_NAME: [
                CallbackQueryHandler(admin_handlers.on_channel_set_name, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_channel_set_name, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_CHANNELS_SET_ID: [
                CallbackQueryHandler(admin_handlers.on_channel_set_id, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_channel_set_id, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_CHANNELS_SET_LINK: [
                CallbackQueryHandler(admin_handlers.on_channel_set_link, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_channel_set_link, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_CHANNELS_ADD: [
                CallbackQueryHandler(admin_handlers.on_channel_add, pattern='^(done|select)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_ADVERTISMENTS: [
                CallbackQueryHandler(admin_handlers.on_advertisments, pattern='^ads', pass_user_data=True)
            ],
            enums.ADMIN_CREATE_AD_TITLE: [
                CallbackQueryHandler(admin_handlers.on_create_ad_title, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_create_ad_title, pass_user_data=True)
            ],
            enums.ADMIN_CREATE_AD_TEXT: [
                CallbackQueryHandler(admin_handlers.on_create_ad_text, pattern='^(back|cancel)', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_create_ad_text, pass_user_data=True)
            ],
            enums.ADMIN_CREATE_AD_MEDIA: [
                CallbackQueryHandler(admin_handlers.on_create_ad_media, pattern='^(back|cancel)', pass_user_data=True),
                MessageHandler(Filters.photo | Filters.animation, admin_handlers.on_create_ad_media, pass_user_data=True)
            ],
            enums.ADMIN_CREATE_AD_CHANNELS: [
                CallbackQueryHandler(admin_handlers.on_create_ad_channels, pattern='^(done|select)', pass_user_data=True)
            ],
            enums.ADMIN_CREATE_AD_USERS: [
                CallbackQueryHandler(admin_handlers.on_create_ad_users, pattern='^(done|select|page)', pass_user_data=True)
            ],
            enums.ADMIN_CREATE_AD_INTERVAL: [
                CallbackQueryHandler(admin_handlers.on_create_ad_interval, pattern='^(back|cancel)', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_create_ad_interval, pass_user_data=True)
            ],
            enums.ADMIN_ADS_LIST: [
                CallbackQueryHandler(admin_handlers.on_ads_list, pattern='^(page|select|back)', pass_user_data=True)
            ],
            enums.ADMIN_AD_SELECTED: [
                CallbackQueryHandler(admin_handlers.on_ad_selected, pattern='^(back|edit|delete)', pass_user_data=True)
            ],
            enums.ADMIN_AD_EDIT: [
                CallbackQueryHandler(admin_handlers.on_ad_edit, pattern='^ad', pass_user_data=True)
            ],
            enums.ADMIN_AD_EDIT_TITLE: [
                CallbackQueryHandler(admin_handlers.on_ad_edit_title, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_ad_edit_title, pass_user_data=True)
            ],
            enums.ADMIN_AD_EDIT_TEXT: [
                CallbackQueryHandler(admin_handlers.on_ad_edit_text, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_ad_edit_text, pass_user_data=True)
            ],
            enums.ADMIN_AD_EDIT_MEDIA: [
                CallbackQueryHandler(admin_handlers.on_ad_edit_media, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.photo | Filters.animation, admin_handlers.on_ad_edit_media, pass_user_data=True)
            ],
            enums.ADMIN_AD_EDIT_INTERVAL: [
                CallbackQueryHandler(admin_handlers.on_ad_edit_interval, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_ad_edit_interval, pass_user_data=True)
            ],
            enums.ADMIN_AD_EDIT_CHANNELS: [
                CallbackQueryHandler(admin_handlers.on_ad_edit_channels, pattern='^(done|select)', pass_user_data=True)
            ],
            enums.ADMIN_AD_EDIT_USERS: [
                CallbackQueryHandler(admin_handlers.on_ad_edit_users, pattern='^(done|select|page)', pass_user_data=True)
            ],
            enums.ADMIN_USERS: [
                CallbackQueryHandler(admin_handlers.on_users, pattern='^users', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_PERMS: [
                CallbackQueryHandler(admin_handlers.on_registered_users_perms, pattern='^(back|select)', pass_user_data=True)
            ],
            enums.ADMIN_REGISTERED_USERS: [
                CallbackQueryHandler(admin_handlers.on_registered_users, pattern='^(back|page|select)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_SELECT: [
                CallbackQueryHandler(admin_handlers.on_registered_users_select, pattern='^registration', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_ORDERS: [
                CallbackQueryHandler(admin_handlers.on_registered_users_orders, pattern='^(back|select|page)', pass_user_data=True)
            ],
            enums.ADMIN_REGISTERED_USERS_STATUS: [
                CallbackQueryHandler(admin_handlers.on_registered_users_status, pattern='^(back|select)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_REMOVE: [
                CallbackQueryHandler(admin_handlers.on_registered_users_remove, pattern='^(yes|no)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_BLACK_LIST: [
                CallbackQueryHandler(admin_handlers.on_registered_users_black_list, pattern='^(yes|no)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations, pattern='^(back|page|select)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS_APPROVE: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations_approve, pattern='^(back|select)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS_BLACK_LIST: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations_black_list, pattern='^(yes|no)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS_USER: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations_user, pattern='^(back|approve_user|black_list)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_BLACK_LIST: [
                CallbackQueryHandler(admin_handlers.on_black_list, pattern='^(back|page|select)', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_BLACK_LIST_USER: [
                CallbackQueryHandler(admin_handlers.on_black_list_user, pattern='^black_list', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_LOGISTIC_MANAGERS: [
                CallbackQueryHandler(admin_handlers.on_logistic_managers, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_LOGISTIC_MANAGER_SETTINGS: [
                CallbackQueryHandler(admin_handlers.on_logistic_manager_settings, pattern='logistic', pass_user_data=True)
            ],
            enums.ADMIN_BOT_LANGUAGE: [
                CallbackQueryHandler(admin_handlers.on_bot_language, pattern='^(back|iw|en)', pass_user_data=True)
            ],
            enums.ADMIN_BOT_STATUS: [
                CallbackQueryHandler(
                    admin_handlers.on_admin_bot_status, pattern='^bot_status', pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_ORDER_OPTIONS: [
                CallbackQueryHandler(
                    admin_handlers.on_admin_order_options, pattern='^bot_order_options', pass_user_data=True)
            ],
            enums.ADMIN_ADD_DISCOUNT: [
                CallbackQueryHandler(admin_handlers.on_admin_add_discount, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_add_discount,
                               pass_user_data=True),
            ],
            enums.ADMIN_EDIT_IDENTIFICATION_STAGES: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_stages, pattern='^id', pass_user_data=True)
            ],
            enums.ADMIN_EDIT_IDENTIFICATION_QUESTION_TYPE: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_question_type, pattern='^(back|photo|text|video)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_EDIT_IDENTIFICATION_STAGES_TEXT: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_text_type, pattern='^(back|phone|text|id)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_EDIT_IDENTIFICATION_QUESTION: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_question, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_edit_identification_question, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_IDENTIFICATION_PERMISSIONS: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_permissions, pattern='^(select|done)', pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY: [
                CallbackQueryHandler(admin_handlers.on_delivery, pattern='^(back|edit_methods|edit_fee)', pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_METHODS: [
                CallbackQueryHandler(admin_handlers.on_delivery_methods, pattern='^(back|pickup|delivery|both)', pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE: [
                CallbackQueryHandler(admin_handlers.on_delivery_fee, pattern='^(back|add|perms)', pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE_ADD: [
                CallbackQueryHandler(admin_handlers.on_delivery_fee_add, pattern='^(back|all|select)', pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE_LOCATION: [
                CallbackQueryHandler(admin_handlers.on_add_delivery_for_location, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE_ENTER: [
                CallbackQueryHandler(admin_handlers.on_delivery_fee_enter, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_delivery_fee_enter, pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE_PERMISSIONS: [
                CallbackQueryHandler(admin_handlers.on_delivery_fee_permissions, pattern='^(done|select)', pass_user_data=True),
            ],
            enums.ADMIN_INIT: [
                CommandHandler('cancel', admin_handlers.on_cancel),
                MessageHandler(Filters.all, admin_handlers.on_admin_fallback),
            ],
            enums.ADMIN_RESET_DATA: [
                CallbackQueryHandler(admin_handlers.on_admin_reset_all_data, pattern='^(back|yes|no)', pass_user_data=True)
            ],
            enums.ADMIN_RESET_CONFIRM: [
                CallbackQueryHandler(admin_handlers.on_admin_reset_confirm, pattern='^(back|yes|no)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_groups, pattern='^(back|add|list)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_LIST: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_groups_list, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_SELECTED: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_selected, pattern='^(back|edit|special_clients|users|delete)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_CLIENTS: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_clients, pattern='^(back|done|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_USERS: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_users, pattern='^(back|select|search)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_USERS_SEARCH: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_users_search, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_product_price_group_users_search, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_USERS_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_users_select, pattern='^(back|done|select)', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_CHANGE: [
                MessageHandler(Filters.text, admin_handlers.on_admin_product_price_group_change, pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_change, pattern='^back', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_PRICES: [
                MessageHandler(Filters.text, admin_handlers.on_admin_product_price_group_prices, pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_prices, pattern='^back|', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_PERMISSIONS_NEW: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_permissions_new, pattern='^(done|select)', pass_user_data=True)
            ],
            enums.ADMIN_BTC_PAYMENTS: [
                CallbackQueryHandler(admin_handlers.on_admin_btc_settings, pattern='^btc', pass_user_data=True)
            ],
            enums.ADMIN_BTC_NEW_WALLET_ID: [
                MessageHandler(Filters.text, admin_handlers.on_admin_btc_new_wallet_id, pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_admin_btc_new_wallet_id, pattern='^back', pass_user_data=True)
            ],
            enums.ADMIN_BTC_NEW_PASSWORD: [
                MessageHandler(Filters.text, admin_handlers.on_admin_btc_new_password, pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_admin_btc_new_password, pattern='^back', pass_user_data=True)
            ],
            enums.ADMIN_SET_CURRENCIES: [
                CallbackQueryHandler(admin_handlers.on_admin_change_currency, pattern='^(back|USD|GBP|EUR|ILS)', pass_user_data=True)
            ],
            enums.ADMIN_SET_CURRENCIES_CONFIRM: [
                CallbackQueryHandler(admin_handlers.on_admin_change_currency_confirm, pattern='^(yes|no)', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY: [
                CallbackQueryHandler(admin_handlers.on_lottery, pattern='^lottery', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_WINNERS: [
                CallbackQueryHandler(admin_handlers.on_lottery_winners, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_SETTINGS: [
                CallbackQueryHandler(admin_handlers.on_lottery_settings, pattern='^lottery', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_OFF_CONFIRM: [
                CallbackQueryHandler(admin_handlers.on_lottery_off_confirm, pattern='^(yes|no)', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_WINNERS_NUM: [
                CallbackQueryHandler(admin_handlers.on_lottery_winners_num, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_lottery_winners_num, pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_PARTICIPANTS: [
                CallbackQueryHandler(admin_handlers.on_lottery_participants, pattern='^lottery', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_CONDITIONS: [
                CallbackQueryHandler(admin_handlers.on_lottery_conditions, pattern='^lottery', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_PRODUCT_SELECT: [
                CallbackQueryHandler(admin_handlers.on_lottery_select_product, pattern='^(page|select|back)', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_AMOUNT_SELECT: [
                CallbackQueryHandler(admin_handlers.on_lottery_amount_select, pattern='^(select|back)', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_TICKETS_NUM: [
                CallbackQueryHandler(admin_handlers.on_lottery_tickets_num, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_lottery_tickets_num, pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_PERMISSIONS: [
                CallbackQueryHandler(admin_handlers.on_lottery_permissions, pattern='^(done|select)', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_PARTICIPANTS_USERS: [
                CallbackQueryHandler(admin_handlers.on_lottery_participants_users, pattern='^(done|select|page)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_MIN_PRICE: [
                CallbackQueryHandler(admin_handlers.on_lottery_min_price, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_lottery_min_price, pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_PRODUCTS_CONDITION: [
                CallbackQueryHandler(admin_handlers.on_lottery_products_condition, pattern='^lottery', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_SINGLE_PRODUCT_CONDITION: [
                CallbackQueryHandler(admin_handlers.on_lottery_single_product_condition, pattern='^(select|page|back)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_CATEGORY_CONDITION: [
                CallbackQueryHandler(admin_handlers.on_lottery_category_condition, pattern='^(select|page|back)',
                                     pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_MESSAGES: [
                CallbackQueryHandler(admin_handlers.on_lottery_messages, pattern='^lottery', pass_user_data=True)
            ],
            enums.ADMIN_LOTTERY_MESSAGES_INTERVAL: [
                CallbackQueryHandler(admin_handlers.on_lottery_messages_interval, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_lottery_messages_interval, pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS: [
                CallbackQueryHandler(admin_handlers.on_reviews, pattern='^reviews', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_PENDING: [
                CallbackQueryHandler(admin_handlers.on_reviews_pending, pattern='^(back|select|page)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_PENDING_SELECT: [
                CallbackQueryHandler(admin_handlers.on_reviews_pending_select, pattern='^reviews', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_SHOW:[
                CallbackQueryHandler(admin_handlers.on_reviews_show, pattern='^reviews', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_BY_DATE: [
                CallbackQueryHandler(admin_handlers.on_reviews_by_date, pattern='^(year|month|day|back)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_BY_DATE_SELECT: [
                CallbackQueryHandler(admin_handlers.on_reviews_by_date_select, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_BY_CLIENT_PERMISSIONS: [
                CallbackQueryHandler(admin_handlers.on_reviews_by_client_permissions, pattern='^(back|select)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_BY_CLIENT: [
                CallbackQueryHandler(admin_handlers.on_reviews_by_client, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_BY_CLIENT_LIST: [
                CallbackQueryHandler(admin_handlers.on_reviews_by_client_list, pattern='^(back|page|select)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_QUESTIONS: [
                CallbackQueryHandler(admin_handlers.on_reviews_questions, pattern='^reviews', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_QUESTIONS_LIST: [
                CallbackQueryHandler(admin_handlers.on_reviews_questions_list, pattern='^(back|select)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_QUESTIONS_SELECT: [
                CallbackQueryHandler(admin_handlers.on_reviews_questions_select, pattern='^(delete|back)', pass_user_data=True)
            ],
            enums.ADMIN_REVIEWS_QUESTIONS_NEW: [
                CallbackQueryHandler(admin_handlers.on_reviews_questions_new, pattern='^back', pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_reviews_questions_new, pass_user_data=True)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(handlers.on_start, pattern='^start_bot',  pass_user_data=True),
            CommandHandler('start', handlers.on_start, pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_courier_menu, pattern='^courier_menu', pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_courier_chat, pattern='^courier_chat', pass_user_data=True),
            CallbackQueryHandler(handlers.on_chat_with_courier, pattern='^client_chat', pass_user_data=True),
            CallbackQueryHandler(handlers.on_open_chat_msg, pattern='^client_read_msg', pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_open_chat_msg, pattern='^courier_read_msg', pass_user_data=True),
            CallbackQueryHandler(courier_handlers.on_client_waiting_keyboard, pattern='^courier_ping', pass_user_data=True),
            CallbackQueryHandler(handlers.on_client_order_delivered, pattern='^delivered_order', pass_user_data=True)
        ])
    updater = Updater(config.api_token, user_sig_handler=close_db_on_signal, workers=18)
    updater.dispatcher.add_handler(user_conversation_handler)
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.service_channel_courier_query_handler,
                             pattern='^take_order',
                             pass_user_data=True))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.service_channel_sendto_courier_handler,
                             pattern='^sendto',
                             pass_user_data=True))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.on_service_order_message, pattern='^order',pass_user_data=True)
    )
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.on_service_order_finished_message, pattern='^finished_order', pass_user_data=True)
    )
    updater.dispatcher.add_handler(CallbackQueryHandler(handlers.cancel_order_confirm, pattern='^cancel_order'))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.on_courier_confirm, pattern='^confirmed', pass_user_data=True))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.on_courier_unconfirm, pattern='^notconfirmed', pass_user_data=True))
    updater.dispatcher.add_handler((
        CallbackQueryHandler(handlers.delete_message, pattern='delete_msg')
    ))
    updater.dispatcher.add_handler((
        CallbackQueryHandler(admin_handlers.on_start_btc_processing, pattern='btc_processing_start')
    ))
    updater.dispatcher.add_error_handler(handlers.on_error)
    start_orders_processing(updater.bot)
    send_lottery_messages(updater.bot)
    send_channel_advertisments(updater.bot)
    manage_lottery_participants(updater.bot)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    create_tables()
    shortcuts.init_bot_tables()
    wallet_enable_hd(get_channel_trans(), BtcSettings.WALLET, BtcSettings.PASSWORD, BtcSettings.SECOND_PASSWORD)
    main()
