from decimal import Decimal
from datetime import datetime
import requests

from requests.exceptions import ConnectionError

from pytz import timezone

from .btc_settings import BtcSettings
from .helpers import config, quantize_btc, logger
from .models import CurrencyRates, Currencies


class BtcError(Exception):
    pass


class BtcWallet:

    def __init__(self, trans, wallet_id, password, second_password=None):
        self.wallet_id = wallet_id
        self.password = password
        self.second_password = second_password
        self.main_url = self.get_main_url()
        self._ = trans

    def get_main_url(self):
        url = 'http://localhost:{}/merchant/{}/'.format(BtcSettings.PORT, self.wallet_id)
        return url

    def make_request(self, url, params):
        try:
            resp = requests.get(url, params=params)
        except ConnectionError as ex:
            logger.error('BTC request failed:\n{}'.format(str(ex)))
            error = 'Connection error'
        else:
            res = resp.json()
            if resp.status_code == 200:
                return res
            else:
                error = res.get('error', '')
            logger.error('BTC request failed:\n{}'.format(res))
        raise BtcError(error)

    def convert_to_satoshi(self, amount):
        return amount * 100000000

    def convert_from_satoshi(self, amount):
        return amount / 100000000

    def enable_hd(self):
        resp = self.make_request(self.main_url + 'enableHD', {'password': self.password})
        return resp

    def check_wallet_balance(self):
        url = self.main_url + 'balance'
        resp = self.make_request(url, {'password': self.password})
        balance = self.convert_from_satoshi(resp['balance'])
        return balance

    def make_payment(self, amount, to, xpub):
        url = self.main_url + 'payment'
        amount = self.convert_to_satoshi(amount)
        amount = int(amount)
        account_index = self.get_account_index(xpub)
        params = {'password': self.password, 'to': to, 'amount': amount, 'from': account_index}
        if self.second_password:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to make payment'))
        res = (resp.get(val) for val in ('message', 'tx_hash', 'notice'))
        return res

    def list_accounts(self):
        url = self.main_url + 'accounts'
        params = {'password': self.password}
        if BtcSettings.SECOND_PASSWORD:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to get accounts data'))
        return resp

    def find_account(self, xpub):
        url = self.main_url + 'accounts/{}'.format(xpub)
        params = {'password': self.password}
        if BtcSettings.SECOND_PASSWORD:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to get accounts data'))
        return resp

    def get_account_index(self, xpub):
        resp = self.find_account(xpub)
        return resp['index']

    def get_account_address(self, xpub):
        resp = self.find_account(xpub)
        return resp['receiveAddress']

    def get_address_balance(self, address):
        url = self.main_url + 'address_balance'
        params = {'password': self.password, 'address': address}
        if self.second_password:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to check address balance'))
        balance = self.convert_from_satoshi(resp['balance'])
        total_received = self.convert_from_satoshi(resp['total_received'])
        total_received = quantize_btc(total_received)
        return balance, total_received

    def generate_btc_address(self, label):
        url = self.main_url + 'new_address'
        params = {'password': self.password, 'label': label}
        if self.second_password:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to create new BTC address'))
        return resp['address'], resp['label']

    def create_hd_account_address(self, label):
        url = self.main_url + 'accounts/create'
        params = {'password': self.password, 'label': label}
        if self.second_password:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to create new BTC address'))
        xpub = resp['xpub']
        url = self.main_url + 'accounts/{}/receiveAddress'.format(xpub)
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to create new BTC address'))
        return resp['address'], xpub

    def get_hd_account_balance(self, xpub):
        url = self.main_url + 'accounts/{}/balance'.format(xpub)
        params = {'password': self.password}
        if self.second_password:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        if not resp:
            raise BtcError(self._('Failed to check address balance'))
        balance = resp['balance']
        if balance is None:
            balance = 0
        balance = self.convert_from_satoshi(balance)
        balance = quantize_btc(balance)
        return balance

    def archive_address(self, address):
        url = self.main_url + 'archive_address'
        params = {'password': self.password, 'address': address}
        if self.second_password:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        return resp['archived']

    def unarchive_address(self, address):
        url = self.main_url + 'unarchive_address'
        params = {'password': self.password, 'address': address}
        if self.second_password:
            params['second_password'] = self.second_password
        resp = self.make_request(url, params)
        return resp['active']


def wallet_enable_hd(trans, wallet_id, password, second_password=None):
    wallet = BtcWallet(trans, wallet_id, password, second_password)
    try:
        res = wallet.enable_hd()
        success = True
    except BtcError as ex:
        res = str(ex)
        success = False
    return res, success


class CurrencyConverter:

    @staticmethod
    def convert_to_btc(currency, value):
        res = None
        last_rates = CurrencyConverter.get_last_rates(currency)
        if last_rates:
            res = quantize_btc(value * last_rates.btc_rate)
        return res

    @staticmethod
    def convert_from_btc(currency, value):
        res = None
        last_rates = CurrencyConverter.get_last_rates(currency)
        if last_rates:
            res = value / last_rates.btc_rate
            res = Decimal(res).quantize(Decimal('0.01'))
        return res

    @staticmethod
    def get_last_rates(currency):
        CurrencyConverter.fetch_update_currencies()
        last_rates = CurrencyRates.get(currency=currency)
        return last_rates

    @staticmethod
    def fetch_update_currencies():
        last_updated = config.currencies_last_updated
        if last_updated:
            now = datetime.now()
            il_tz = timezone('Asia/Jerusalem')
            now = il_tz.localize(now)
            diff = now - last_updated
            diff_more = diff.seconds / 3600 >= 1
        else:
            diff_more = True
        currencies = list(Currencies.CURRENCIES.keys())
        if diff_more:
            api_key = config.currencies_api_key
            url = 'http://apilayer.net/api/live'
            currencies.append('BTC')
            currencies = ','.join(currencies)
            params = {'access_key': api_key, 'currencies': currencies}
            resp = requests.get(url, params=params)
            if resp.status_code == 200:
                quotes = resp.json()['quotes']
                btc_rate = quotes.pop('USDBTC')
                btc_rate = Decimal(btc_rate)
                for name, rate in quotes.items():
                    name = name.replace('USD', '', 1)
                    rate = quantize_btc(rate)
                    currency_btc_rate = btc_rate / rate
                    currency_btc_rate = quantize_btc(currency_btc_rate)
                    try:
                        currency = CurrencyRates.get(currency=name)
                    except CurrencyRates.DoesNotExist:
                        currency = CurrencyRates(currency=name)
                    currency.btc_rate = currency_btc_rate
                    currency.dollar_rate = rate
                    currency.save()
                now = datetime.now()
                il_tz = timezone('Asia/Jerusalem')
                now = il_tz.localize(now)
                config.set_datetime_value('currencies_last_updated', now)

    @staticmethod
    def convert_currencies(amount, first_currency, second_currency):
        CurrencyConverter.fetch_update_currencies()
        first_currency = CurrencyRates.get(currency=first_currency)
        second_currency = CurrencyRates.get(currency=second_currency)
        dollar_amount = amount / first_currency.dollar_rate
        result_amount = dollar_amount * second_currency.dollar_rate
        result_amount = Decimal(result_amount).quantize(Decimal('0.01'))
        return result_amount

    @staticmethod
    def convert_btc(usd_rate, btc_rate):
        rate = btc_rate / usd_rate
        rate = quantize_btc(rate)
        return rate






