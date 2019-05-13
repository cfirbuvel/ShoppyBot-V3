from collections import defaultdict
from decimal import Decimal

from .btc_wrapper import CurrencyConverter
from .helpers import config
from .models import ProductCount, Product, User, OrderItem


class Cart:

    @staticmethod
    def check_cart(user_data):
        # check that cart is still here in case we've restarted
        cart = user_data.get('cart')
        if cart is None:
            cart = {}
            user_data['cart'] = cart
        return cart

    @staticmethod
    def add(user_data, product_id):
        cart = Cart.check_cart(user_data)
        product = Product.get(id=product_id)
        if product.group_price:
            query = (ProductCount.product_group == product.group_price)
        else:
            query = (ProductCount.product == product)
        prices = ProductCount.select().where(query).order_by(ProductCount.count.asc())
        counts = [x.count for x in prices]
        print(counts)
        if product_id not in cart:
            cart[product_id] = counts[0]
        else:
            # add more
            current_count = cart[product_id]
            current_count_index = counts.index(current_count)
            # iterate through possible product counts for next price
            next_count_index = (current_count_index + 1) % len(counts)
            cart[product_id] = counts[next_count_index]
        user_data['cart'] = cart
        return user_data

    @staticmethod
    def remove(user_data, product_id):
        cart = Cart.check_cart(user_data)
        product_id = product_id
        product = Product.get(id=product_id)
        if product.group_price:
            query = (ProductCount.product_group == product.group_price)
        else:
            query = (ProductCount.product == product)
        prices = ProductCount.select().where(query).order_by(ProductCount.count.asc())
        counts = [x.count for x in prices]

        if product_id in cart:
            current_count = cart[product_id]
            current_count_index = counts.index(current_count)

            if current_count_index == 0:
                del cart[product_id]
            else:
                next_count_index = current_count_index - 1
                cart[product_id] = counts[next_count_index]
        user_data['cart'] = cart

        return user_data

    @staticmethod
    def remove_all(user_data, product_id):
        cart = Cart.check_cart(user_data)
        try:
            del cart[product_id]
        except KeyError:
            pass
        user_data['cart'] = cart
        return user_data

    @staticmethod
    def get_products_info(user_data, currency, for_order=False):
        product_ids = Cart.get_product_ids(user_data)

        group_prices = defaultdict(int)
        products = Product.select().where(Product.id << list(product_ids))
        products_counts = []
        for product in products:
            count = Cart.get_product_count(user_data, product.id)
            group_price = product.group_price
            if group_price:
                group_prices[group_price.id] += count
            products_counts.append((product, count))

        for group_id, count in group_prices.items():
            group_count = ProductCount.select().where(
                ProductCount.product_group == group_id, ProductCount.count <= count
            ).order_by(ProductCount.count.desc()).first()
            price_per_one = group_count.price / group_count.count
            group_prices[group_id] = price_per_one

        products_info = []
        for product, count in products_counts:
            group_price = product.group_price
            if group_price:
                product_price = count * group_prices[group_price.id]
                product_price = Decimal(product_price).quantize(Decimal('0.01'))
            else:
                product_price = ProductCount.get(product=product, count=count).price
            if not currency == config.currency and not for_order:
                product_price = CurrencyConverter.convert_currencies(product_price, config.currency, currency)
            if for_order:
                name = product.id
            else:
                name = product.title
            products_info.append((name, count, product_price))
        return products_info

    @staticmethod
    def get_product_ids(user_data):
        cart = Cart.check_cart(user_data)
        return cart.keys()

    @staticmethod
    def get_product_count(user_data, product_id):
        cart = Cart.check_cart(user_data)
        if product_id not in cart:
            return 0
        else:
            return cart[product_id]

    @staticmethod
    def not_empty(user_data):
        cart = Cart.check_cart(user_data)
        return len(cart) > 0

    @staticmethod
    def get_product_subtotal(user_data, product_id):
        count = Cart.get_product_count(user_data, product_id)
        product = Product.get(id=product_id)
        if product.group_price:
            subquery = {'product_group': product.group_price}
            # subquery = (ProductCount.product_group == product.group_price)
        else:
            subquery = {'product': product}
        try:
            product_count = ProductCount.get(count=count, **subquery)
        except ProductCount.DoesNotExist:
            price = 0
        else:
            price = product_count.price
        return price

    @staticmethod
    def get_cart_total(user_data, currency):
        products_info = Cart.get_products_info(user_data, currency)
        total = sum((val[-1] for val in products_info))
        return total

    @staticmethod
    def fill_order(user_data, order, currency):
        products = Cart.get_products_info(user_data, currency, for_order=True)
        total = 0
        for p_id, p_count, p_price in products:
            OrderItem.create(order=order, product_id=p_id, count=p_count, total_price=p_price)
            total += p_price
        return total