#! /usr/bin/env python3
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, Filters, MessageHandler, Updater, \
    Handler

from src import admin_handlers
from src import enums
from src import handlers
from src.helpers import config, get_user_id, get_channel_trans, init_bot_tables

# from src.shortcuts import resend_responsibility_keyboard, make_confirm, make_unconfirm

from src.models import create_tables, close_db
from src.btc_wrapper import wallet_enable_hd
from src.btc_settings import BtcSettings
# from src.btc_processor import start_orders_processing

# will be called when conversation context is lost (e.g. bot is restarted)
# and the user clicks menu buttons


def close_db_on_signal(signum, frame):
    close_db()


def error_callback(bot, update, error):
    raise error


def main():
    # courier_conversation_handler = ConversationHandler(
    #     entry_points=[
    #         CallbackQueryHandler(handlers.on_courier_action_to_confirm,
    #                              pattern='^confirm_courier', pass_user_data=True
    #                              ),
    #         CallbackQueryHandler(handlers.on_courier_ping_choice,
    #                              pattern='^ping', pass_user_data=True),
    #         CallbackQueryHandler(handlers.on_admin_drop_order, pattern='^admin_dropped'),
    #         CallbackQueryHandler(resend_responsibility_keyboard,
    #                              pattern='^dropped',
    #                              )
    #     ],
    #     states={
    #         enums.COURIER_STATE_INIT: [
    #             CallbackQueryHandler(handlers.on_courier_action_to_confirm,
    #                                  pattern='^confirm_courier', pass_user_data=True
    #                                  ),
    #             CallbackQueryHandler(handlers.on_courier_ping_choice,
    #                                  pattern='^ping', pass_user_data=True),
    #             CallbackQueryHandler(handlers.on_admin_drop_order, pattern='^admin_dropped'),
    #             CallbackQueryHandler(resend_responsibility_keyboard,
    #                                  pattern='^dropped',
    #                                  )
    #         ],
    #         enums.COURIER_STATE_PING: [
    #             CallbackQueryHandler(handlers.on_courier_ping_client, pass_user_data=True)
    #         ],
    #         enums.COURIER_STATE_PING_SOON: [
    #             CallbackQueryHandler(handlers.on_courier_ping_client_soon, pass_user_data=True),
    #             MessageHandler(Filters.text, handlers.on_courier_ping_client_soon, pass_user_data=True)
    #         ],
    #         enums.COURIER_STATE_CONFIRM_ORDER: [
    #             CallbackQueryHandler(handlers.on_courier_confirm_order, pass_user_data=True)
    #         ],
    #         enums.COURIER_STATE_CONFIRM_REPORT: [
    #             CallbackQueryHandler(handlers.on_courier_confirm_report,)
    #         ],
    #         enums.COURIER_STATE_REPORT_REASON: [
    #             MessageHandler(Filters.text, handlers.on_courier_enter_reason),
    #             CallbackQueryHandler(handlers.on_courier_cancel_reason, pattern='^back')
    #         ]
    #     },
    #     fallbacks=[
    #         CommandHandler('start', handlers.on_start, pass_user_data=True)
    #     ]
    # )
    user_conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', handlers.on_start, pass_user_data=True),
            CallbackQueryHandler(handlers.on_menu, pattern='^(menu|product)', pass_user_data=True)
        ],
        states={
            enums.BOT_INIT: [
                CommandHandler('start', handlers.on_start, pass_user_data=True),
                CallbackQueryHandler(handlers.on_menu, pattern='^(menu|product)', pass_user_data=True)
            ],
            enums.BOT_REGISTRATION: [
                CallbackQueryHandler(handlers.on_registration, pass_user_data=True)
            ],
            enums.BOT_REGISTRATION_REPEAT: [
                CallbackQueryHandler(handlers.on_registration_repeat, pass_user_data=True)
            ],
            enums.BOT_IDENTIFICATION: [
                CallbackQueryHandler(handlers.on_registration_identification, pass_user_data=True),
                MessageHandler(Filters.text | Filters.photo | Filters.video, handlers.on_registration_identification, pass_user_data=True)
            ],
            enums.BOT_PHONE_NUMBER: [
                MessageHandler(Filters.text | Filters.contact, handlers.on_registration_phone_number, pass_user_data=True)
            ],
            enums.BOT_CHANNELS: [
                CallbackQueryHandler(handlers.on_channels, pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_SHIPPING: [
                CallbackQueryHandler(handlers.on_order_delivery, pass_user_data=True),
            ],
            enums.BOT_CHECKOUT_LOCATION: [
                CallbackQueryHandler(handlers.on_order_locations, pass_user_data=True),
            ],
            enums.BOT_CHECKOUT_ADDRESS: [
                MessageHandler(Filters.text, handlers.on_order_delivery_address, pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_DATETIME_SELECT: [
                CallbackQueryHandler(handlers.on_order_datetime_select, pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_DATE_SELECT: [
                CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
                CallbackQueryHandler(handlers.on_order_date_select, pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_TIME_SELECT: [
                CallbackQueryHandler(handlers.on_time_picker_change, pattern='^time_picker', pass_user_data=True),
                CallbackQueryHandler(handlers.on_order_time_select, pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_PHONE_NUMBER: [
                MessageHandler(Filters.contact | Filters.text,
                               handlers.on_order_phone_number, pass_user_data=True),
            ],
            enums.BOT_CHECKOUT_IDENTIFY: [
                CallbackQueryHandler(handlers.on_order_identification, pass_user_data=True),
                MessageHandler(Filters.text | Filters.photo | Filters.video | Filters.all, handlers.on_order_identification, pass_user_data=True)
            ],
            enums.BOT_CHECKOUT_PAYMENT_TYPE: [
                CallbackQueryHandler(handlers.on_order_payment_type,
                                     pass_user_data=True),
            ],
            enums.BOT_BTC_CONVERSION_FAILED: [
                CallbackQueryHandler(handlers.on_order_btc_conversion_failed, pass_user_data=True),
            ],
            enums.BOT_GENERATING_ADDRESS_FAILED: [
                CallbackQueryHandler(handlers.on_order_generating_address_failed, pass_user_data=True),
            ],
            enums.BOT_BTC_TOO_LOW: [
                CallbackQueryHandler(handlers.on_order_btc_too_low, pass_user_data=True),
            ],
            enums.BOT_ORDER_CONFIRMATION: [
                CallbackQueryHandler(handlers.on_order_confirm, pass_user_data=True),
            ],
            enums.BOT_LANGUAGE_CHANGE: [
                CallbackQueryHandler(handlers.on_bot_language_change,
                                     pass_user_data=True),
            ],
            enums.BOT_MY_ORDERS: [
                CallbackQueryHandler(handlers.on_menu, pattern='product', pass_user_data=True),
                CallbackQueryHandler(handlers.on_my_orders, pass_user_data=True)
            ],
            # enums.BOT_MY_ORDERS_DATE: [
            #     CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
            #     CallbackQueryHandler(handlers.on_my_order_date, pass_user_data=True)
            # ],
            enums.BOT_MY_LAST_ORDER: [
                CallbackQueryHandler(handlers.on_my_last_order, pass_user_data=True)
            ],
            enums.BOT_MY_LAST_ORDER_CANCEL: [
                CallbackQueryHandler(handlers.on_my_last_order_cancel, pass_user_data=True)
            ],
            enums.BOT_MY_ORDERS_SELECT:[
                CallbackQueryHandler(handlers.on_my_order_select, pass_user_data=True)
            ],
            enums.BOT_PRODUCT_CATEGORIES: [
                CallbackQueryHandler(handlers.on_product_categories, pass_user_data=True)
            ],
            #
            # admin states
            #
            enums.ADMIN_MENU: [
                CallbackQueryHandler(admin_handlers.on_settings_menu, pass_user_data=True)],
            # enums.ADMIN_STATISTICS: [CallbackQueryHandler(
            #     admin_handlers.on_statistics_menu, pattern='^statistics', pass_user_data=True)],
            # enums.ADMIN_STATISTICS_GENERAL: [
            #     CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
            #     CallbackQueryHandler(admin_handlers.on_statistics_general, pass_user_data=True),
            # ],
            # enums.ADMIN_STATISTICS_COURIERS: [
            #     CallbackQueryHandler(admin_handlers.on_statistics_courier_select, pass_user_data=True)
            # ],
            # enums.ADMIN_STATISTICS_COURIERS_DATE: [
            #     CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
            #     CallbackQueryHandler(admin_handlers.on_statistics_couriers, pass_user_data=True)
            # ],
            # enums.ADMIN_STATISTICS_LOCATIONS: [
            #     CallbackQueryHandler(admin_handlers.on_statistics_locations_select, pass_user_data=True)
            # ],
            # enums.ADMIN_STATISTICS_LOCATIONS_DATE: [
            #     CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
            #     CallbackQueryHandler(admin_handlers.on_statistics_locations, pass_user_data=True)
            # ],
            # enums.ADMIN_STATISTICS_USER: [
            #     CallbackQueryHandler(admin_handlers.on_statistics_username, pass_user_data=True),
            #     MessageHandler(Filters.text, admin_handlers.on_statistics_username, pass_user_data=True)
            # ],
            # enums.ADMIN_STATISTICS_USER_DATE: [
            #     CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
            #     CallbackQueryHandler(admin_handlers.on_statistics_user, pass_user_data=True)
            # ],
            enums.ADMIN_BOT_SETTINGS: [
                CallbackQueryHandler(admin_handlers.on_bot_settings_menu, pass_user_data=True)
            ],
            enums.ADMIN_COURIERS: [
                CallbackQueryHandler(admin_handlers.on_couriers, pass_user_data=True)
            ],
            enums.ADMIN_COURIER_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_courier_detail, pass_user_data=True)
            ],
            enums.ADMIN_COURIER_LOCATIONS: [
                CallbackQueryHandler(admin_handlers.on_courier_locations, pass_user_data=True)
            ],
            enums.ADMIN_COURIER_WAREHOUSE_PRODUCTS: [
                CallbackQueryHandler(admin_handlers.on_courier_warehouse_products, pass_user_data=True)
            ],
            enums.ADMIN_COURIER_WAREHOUSE_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_courier_warehouse_detail, pass_user_data=True)
            ],
            enums.ADMIN_COURIER_WAREHOUSE_EDIT: [
                CallbackQueryHandler(admin_handlers.on_courier_warehouse_edit, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_courier_warehouse_edit, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_WORKING_HOURS: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_working_hours, pass_user_data=True)
            ],
            enums.ADMIN_ENTER_WORKING_HOURS: [
                CallbackQueryHandler(admin_handlers.on_admin_enter_working_hours, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_enter_working_hours, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_MESSAGES: [
                CallbackQueryHandler(admin_handlers.on_edit_messages, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_MESSAGES_ENTER: [
                CallbackQueryHandler(admin_handlers.on_edit_messages_enter, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_edit_messages_enter, pass_user_data=True)
            ],
            enums.ADMIN_LOCATIONS: [
                CallbackQueryHandler(admin_handlers.on_locations, pass_user_data=True)
            ],
            enums.ADMIN_LOCATION_ADD: [
                CallbackQueryHandler(admin_handlers.on_location_add, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_location_add, pass_user_data=True)
            ],
            enums.ADMIN_LOCATIONS_VIEW: [
                CallbackQueryHandler(admin_handlers.on_locations_view, pass_user_data=True)
            ],
            enums.ADMIN_LOCATION_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_location_detail, pass_user_data=True)
            ],
            enums.ADMIN_ORDERS: [
                CallbackQueryHandler(admin_handlers.on_admin_orders, pattern='(^finished|^pending|^back)', pass_user_data=True)
            ],
            enums.ADMIN_ORDERS_PENDING_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_orders_pending_select, pass_user_data=True)
            ],
            # enums.ADMIN_ORDERS_FINISHED_DATE: [
            #     CallbackQueryHandler(handlers.on_calendar_change, pattern='^calendar', pass_user_data=True),
            #     CallbackQueryHandler(admin_handlers.on_admin_orders_finished_date, pass_user_data=True)
            # ],
            # enums.ADMIN_ORDERS_FINISHED_SELECT: [
            #     CallbackQueryHandler(admin_handlers.on_admin_orders_finished_select, pass_user_data=True)
            # ],
            enums.ADMIN_PRODUCTS: [
                CallbackQueryHandler(admin_handlers.on_products, pattern='^bot_products', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCTS_SHOW: [
                CallbackQueryHandler(admin_handlers.on_show_product, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_ADD: [
                CallbackQueryHandler(admin_handlers.on_product_add, pattern='^bot_product', pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_LAST_ADD: [
                CallbackQueryHandler(admin_handlers.on_product_last_select, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_SELECT: [
                CallbackQueryHandler(admin_handlers.on_product_edit_select, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT: [
                CallbackQueryHandler(admin_handlers.on_product_edit, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_TITLE: [
                CallbackQueryHandler(admin_handlers.on_product_edit_title, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_edit_title, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_PRICES: [
                CallbackQueryHandler(admin_handlers.on_product_edit_price_type, pass_user_data=True)
                # CallbackQueryHandler(admin.on_admin_product_edit_prices, pass_user_data=True),
                # MessageHandler(Filters.text, admin.on_admin_product_edit_prices, pass_user_data=True),
            ],
            enums.ADMIN_PRODUCT_EDIT_PRICES_TEXT: [
                CallbackQueryHandler(admin_handlers.on_product_edit_prices_text, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_edit_prices_text, pass_user_data=True),
            ],
            enums.ADMIN_PRODUCT_EDIT_PRICES_GROUP: [
                CallbackQueryHandler(admin_handlers.on_product_edit_prices_group, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_EDIT_MEDIA: [
                MessageHandler((Filters.text | Filters.photo | Filters.video), admin_handlers.on_product_edit_media,
                               pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel),
            ],
            enums.ADMIN_PRODUCT_TITLE: [
                CallbackQueryHandler(
                    admin_handlers.on_product_title, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_title,
                               pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel),
            ],
            enums.ADMIN_ADD_PRODUCT_PRICES: [
                CallbackQueryHandler(admin_handlers.on_add_product_prices, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICES_TEXT: [
                CallbackQueryHandler(admin_handlers.on_product_price_text, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_product_price_text, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PRODUCT_PRICES_GROUP: [
                CallbackQueryHandler(admin_handlers.on_product_price_group, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_MEDIA: [
                MessageHandler((Filters.text | Filters.photo | Filters.video), admin_handlers.on_product_media,
                               pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel),
            ],
            enums.ADMIN_DELETE_PRODUCT: [
                CallbackQueryHandler(admin_handlers.on_delete_product, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_WAREHOUSE: [
                CallbackQueryHandler(admin_handlers.on_warehouse, pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_PRODUCTS: [
                CallbackQueryHandler(admin_handlers.on_warehouse_products, pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_COURIERS: [
                CallbackQueryHandler(admin_handlers.on_warehouse_couriers, pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_PRODUCT_EDIT: [
                CallbackQueryHandler(admin_handlers.on_warehouse_product_credits, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_warehouse_product_credits, pass_user_data=True)
            ],
            enums.ADMIN_WAREHOUSE_COURIER_DETAIL: [
                CallbackQueryHandler(admin_handlers.on_warehouse_courier_detail, pass_user_data=True),
            ],
            enums.ADMIN_WAREHOUSE_COURIER_EDIT: [
                CallbackQueryHandler(admin_handlers.on_warehouse_courier_edit, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_warehouse_courier_edit, pass_user_data=True)
            ],
            enums.ADMIN_CATEGORIES: [
                CallbackQueryHandler(admin_handlers.on_admin_categories, pass_user_data=True),
            ],
            enums.ADMIN_CATEGORY_ADD: [
                CallbackQueryHandler(admin_handlers.on_admin_category_add, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_category_add, pass_user_data=True)
            ],
            enums.ADMIN_CATEGORY_PRODUCTS_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_category_products_select, pass_user_data=True)
            ],
            enums.ADMIN_CATEGORY_PRODUCTS_ADD: [
                CallbackQueryHandler(admin_handlers.on_admin_category_products_add, pass_user_data=True)
            ],
            enums.ADMIN_CATEGORY_REMOVE_SELECT: [
                CallbackQueryHandler(admin_handlers.on_admin_category_remove, pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS: [
                CallbackQueryHandler(admin_handlers.on_channels, pattern='^bot_channels', pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS_LANGUAGE: [
                CallbackQueryHandler(admin_handlers.on_channels_language)
            ],
            enums.ADMIN_CHANNELS_VIEW: [
                CallbackQueryHandler(admin_handlers.on_channels_view, pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS_DETAILS: [
                CallbackQueryHandler(admin_handlers.on_channel_details, pass_user_data=True)
            ],
            enums.ADMIN_CHANNELS_SET_NAME: [
                CallbackQueryHandler(admin_handlers.on_channel_set_name, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_channel_set_name, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_CHANNELS_SET_ID: [
                CallbackQueryHandler(admin_handlers.on_channel_set_id, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_channel_set_id, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_CHANNELS_SET_LINK: [
                CallbackQueryHandler(admin_handlers.on_channel_set_link, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_channel_set_link, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_CHANNELS_ADD: [
                CallbackQueryHandler(admin_handlers.on_channel_add, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_USERS: [
                CallbackQueryHandler(admin_handlers.on_users, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS: [
                CallbackQueryHandler(admin_handlers.on_registered_users, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_SELECT: [
                CallbackQueryHandler(admin_handlers.on_registered_users_select, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_STATUS: [
                CallbackQueryHandler(admin_handlers.on_registered_users_status, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_REMOVE: [
                CallbackQueryHandler(admin_handlers.on_registered_users_remove, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_REGISTERED_USERS_BLACK_LIST: [
                CallbackQueryHandler(admin_handlers.on_registered_users_black_list, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS_APPROVE: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations_approve, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS_BLACK_LIST: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations_black_list, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_PENDING_REGISTRATIONS_USER: [
                CallbackQueryHandler(admin_handlers.on_pending_registrations_user, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_BLACK_LIST: [
                CallbackQueryHandler(admin_handlers.on_black_list, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_BLACK_LIST_USER: [
                CallbackQueryHandler(admin_handlers.on_black_list_user, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_BOT_LANGUAGE: [
                CallbackQueryHandler(admin_handlers.on_bot_language, pass_user_data=True)
            ],
            enums.ADMIN_BOT_STATUS: [
                CallbackQueryHandler(
                    admin_handlers.on_admin_bot_status, pass_user_data=True),
                CommandHandler('cancel', admin_handlers.on_cancel)
            ],
            enums.ADMIN_ORDER_OPTIONS: [
                CallbackQueryHandler(
                    admin_handlers.on_admin_order_options, pattern='^bot_order_options', pass_user_data=True)
            ],
            # enums.ADMIN_ADD_DISCOUNT: [
            #     CallbackQueryHandler(
            #         admin_handlers.on_admin_add_discount, pass_user_data=True),
            #     MessageHandler(Filters.text, admin_handlers.on_admin_add_discount,
            #                    pass_user_data=True),
            #     CommandHandler('cancel', admin_handlers.on_cancel),
            # ],
            enums.ADMIN_EDIT_IDENTIFICATION_STAGES: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_stages, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_IDENTIFICATION_QUESTION_TYPE: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_question_type, pass_user_data=True)
            ],
            enums.ADMIN_EDIT_IDENTIFICATION_QUESTION: [
                CallbackQueryHandler(admin_handlers.on_admin_edit_identification_question, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_admin_edit_identification_question, pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY: [
                CallbackQueryHandler(admin_handlers.on_delivery, pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_METHODS: [
                CallbackQueryHandler(admin_handlers.on_delivery_methods, pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE: [
                CallbackQueryHandler(admin_handlers.on_delivery_fee, pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE_ADD: [
                CallbackQueryHandler(admin_handlers.on_delivery_fee_add, pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE_LOCATION: [
                CallbackQueryHandler(admin_handlers.on_add_delivery_for_location, pass_user_data=True)
            ],
            enums.ADMIN_DELIVERY_FEE_ENTER: [
                CallbackQueryHandler(admin_handlers.on_delivery_fee_enter, pass_user_data=True),
                MessageHandler(Filters.text, admin_handlers.on_delivery_fee_enter, pass_user_data=True)
            ],

            enums.ADMIN_INIT: [
                CommandHandler('cancel', admin_handlers.on_cancel),
                MessageHandler(Filters.all, admin_handlers.on_admin_fallback),
            ],
            enums.ADMIN_RESET_DATA: [
                CallbackQueryHandler(admin_handlers.on_admin_reset_all_data, pass_user_data=True)
            ],
            enums.ADMIN_RESET_CONFIRM: [
                CallbackQueryHandler(admin_handlers.on_admin_reset_confirm, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUPS: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_groups, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_LIST: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_groups_list, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUPS_SELECTED: [
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_selected, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_CHANGE: [
                MessageHandler(Filters.text, admin_handlers.on_admin_product_price_group_change, pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_change, pass_user_data=True)
            ],
            enums.ADMIN_PRODUCT_PRICE_GROUP_SAVE: [
                MessageHandler(Filters.text, admin_handlers.on_admin_product_price_group_save, pass_user_data=True),
                CallbackQueryHandler(admin_handlers.on_admin_product_price_group_save, pass_user_data=True)
            ],
            enums.ADMIN_BTC_PAYMENTS: [
                CallbackQueryHandler(admin_handlers.on_admin_btc_settings)
            ],
            enums.ADMIN_BTC_NEW_WALLET_ID: [
                MessageHandler(Filters.text, admin_handlers.on_admin_btc_new_wallet_id),
                CallbackQueryHandler(admin_handlers.on_admin_btc_new_wallet_id)
            ],
            enums.ADMIN_BTC_NEW_PASSWORD: [
                MessageHandler(Filters.text, admin_handlers.on_admin_btc_new_password),
                CallbackQueryHandler(admin_handlers.on_admin_btc_new_password)
            ],
            # enums.ADMIN_SET_CURRENCIES: [
            #     CallbackQueryHandler(admin_handlers.on_admin_change_currency)
            # ]
        },
        fallbacks=[
            # CommandHandler('cancel', handlers.on_cancel, pass_user_data=True),
            CommandHandler('start', handlers.on_start, pass_user_data=True)
        ])
    updater = Updater(config.api_token, user_sig_handler=close_db_on_signal, workers=12)
    # updater.dispatcher.add_handler(MessageHandler(
    #     Filters.all, handlers.get_channel_id
    # ))
    # updater.dispatcher.add_handler(MessageHandler(
    #     Filters.status_update.new_chat_members, handlers.send_welcome_message))
    updater.dispatcher.add_handler(user_conversation_handler)
    # updater.dispatcher.add_handler(courier_conversation_handler)
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.service_channel_courier_query_handler,
                             pattern='^courier',
                             pass_user_data=True))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.service_channel_sendto_courier_handler,
                             pattern='^sendto',
                             pass_user_data=True))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(handlers.on_service_order_message, pattern='^order',pass_user_data=True)
    )
    updater.dispatcher.add_handler(CallbackQueryHandler(handlers.cancel_order_confirm, pattern='^cancel_order'))
    # updater.dispatcher.add_handler(
    #     CallbackQueryHandler(make_confirm,
    #                          pattern='^confirmed',
    #                          pass_user_data=True))
    # updater.dispatcher.add_handler(
    #     CallbackQueryHandler(make_unconfirm,
    #                          pattern='^notconfirmed',
    #                          pass_user_data=True))
    updater.dispatcher.add_handler((
        CallbackQueryHandler(handlers.delete_message, pattern='delete_msg')
    ))
    # updater.dispatcher.add_handler((
    #     CallbackQueryHandler(admin_handlers.on_start_btc_processing, pattern='btc_processing_start')
    # ))
    updater.dispatcher.add_error_handler(handlers.on_error)
    # start_orders_processing(updater.bot)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    create_tables()
    init_bot_tables()
    wallet_enable_hd(get_channel_trans(), BtcSettings.WALLET, BtcSettings.PASSWORD, BtcSettings.SECOND_PASSWORD)
    main()
