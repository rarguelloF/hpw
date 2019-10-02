#!/usr/bin/env python

import os
import sys
import random
import subprocess
import logging
import logging.config

import requests
from requests_html import HTMLSession

logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'standard': {
            'format': '%(message)s'
        },
    },
    'handlers': {
        'default': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'INFO',
            'propagate': True
        }
    }
})

logger = logging.getLogger()


def execute(command, env=None):
    popen = subprocess.Popen(
        ' '.join(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        env=env,
        shell=True
    )

    for stdout_line in iter(popen.stdout.readline, ''):
        logger.info(stdout_line.strip())

    popen.stdout.close()
    return popen.wait()


class Proxy:
    exposed_env_vars = os.environ.get(
        'PROXY_EXPOSED_ENV_VARS',
        'HTTP_PROXY HTTPS_PROXY http_proxy https_proxy',
    ).split()

    def __init__(self, host, port, country_code, country, anonymity, google, https, last_checked):
        self.host = host
        self.port = port
        self.country_code = country_code
        self.country = country
        self._anonymity = anonymity
        self._google = google
        self._https = https
        self.last_checked = last_checked

        self.used = False
        self._valid = (None, '')

    def __str__(self):
        return (
            f'Address: {self.address} | '
            f'Country: {self.country} | '
            f'Anonymity level: {self.anonymity} | '
            f'Managed by Google: {self._google} | '
            f'Already used: {"yes" if self.used else "no"} | '
            f'Last checked: {self.last_checked}'
        )

    @property
    def address(self):
        return f"{'https' if self.use_https else 'http'}://{self.host}:{self.port}"

    @property
    def is_google(self):
        return self._google == 'yes'

    @property
    def use_https(self):
        return (
            self._https == 'yes' and
            os.environ.get('PROXY_USE_HTTPS', '0').lower() in ('true', 'yes', 'y', '1')
        )

    @property
    def anonymity(self):
        return {
            'anonymous': 'low',
            'elite proxy': 'high',
        }[self._anonymity]

    def verify(self):
        valid_cache, _ = self._valid
        if valid_cache is not None:
            return self._valid

        verify_url = os.environ.get('PROXY_VERIFY_URL', 'http://checkip.amazonaws.com/')
        verify_timeout = int(os.environ.get('PROXY_INVALID_TIMEOUT', '2'))

        def cache_and_return(result):
            self._valid = result
            return result

        try:
            resp = requests.get(
                verify_url,
                timeout=verify_timeout,
                proxies={
                    'http': self.address,
                    'https': self.address,
                },
            )
        except requests.exceptions.Timeout:
            return cache_and_return((False, f'Timeout after {verify_timeout} seconds'))
        except requests.exceptions.RequestException as err:
            return cache_and_return((False, f'An error occured: {err}'))

        if not resp.ok:
            return cache_and_return((False, f'Bad status code: {resp.status_code}'))

        public_ip = resp.text.replace('\n', '')

        if public_ip != self.host:
            return cache_and_return((False, f'IPs don\'t match: {self.host}(proxy) != {public_ip}(public IP)'))

        return cache_and_return((True, ''))

    def run(self, command):
        env = {}
        env.update(os.environ)
        env.update({key: self.address for key in self.exposed_env_vars})

        result = execute(command, env=env)
        self.used = True
        return result


class SSLProxyManager:
    def __init__(self, proxies=None):
        self._session = HTMLSession()
        self._proxies = []

        if not proxies:
            self._proxies = self._get_proxy_list()
        else:
            self._proxies = proxies

    @property
    def proxies(self):
        return self._proxies

    def refresh(self):
        self._proxies = self._get_proxy_list()

    def unused(self):
        return SSLProxyManager([proxy for proxy in self._proxies if not proxy.used])

    def valid(self):
        return SSLProxyManager([proxy for proxy in self._proxies if proxy.verify()[0]])

    def random(self, unused_only=True):
        max_tries = int(os.environ.get('PROXY_RANDOM_MAX_TRIES', '10'))
        proxy = None
        is_valid = False
        tries = 0

        if unused_only and all(proxy.used for proxy in self._proxies):
            raise Exception(f'All proxies are already used.')

        while not is_valid:
            if tries >= max_tries:
                raise Exception(f'Reached max tries {max_tries} trying to get a random valid proxy.')

            proxy = random.choice(self._proxies)
            if unused_only and not proxy.used:
                is_valid = proxy.verify()

            tries += 1

        return proxy

    def _get_proxy_list(self):
        resp = self._session.get('https://www.sslproxies.org/')
        if not resp.ok:
            logger.info(f'There was an error ({resp.status_code}) fetching from https://www.sslproxies.org/:')
            resp.raise_for_status

        proxies = []
        for tr in resp.html.find('#proxylisttable tbody tr'):
            data = [td.text for td in tr.find('td')]
            proxy = Proxy(*data)
            if proxy.address in [p.address for p in self._proxies if p.used]:
                proxy.used = True

            proxies.append(proxy)

        return proxies


def main():
    p_manager = SSLProxyManager()

    command = sys.argv[1:]
    if not command:
        logger.info('No command specified')
        sys.exit(1)

    refresh_tries = int(os.environ.get('REFRESH_TRIES', '3'))
    max_total_tries = int(os.environ.get('COMMAND_MAX_TRIES', '10'))
    exit_code = 1
    total_tries = 0
    tries = 0

    logger.info(f"Running command: {' '.join(command)}")
    while exit_code != 0:
        if tries >= refresh_tries:
            logger.info(f'Reached {refresh_tries} unsuccessful tries. Refreshing proxy list...')
            p_manager.refresh()
            tries = 0

        if total_tries >= max_total_tries:
            raise Exception(f'Reached max tries {max_total_tries} running command.')

        proxy = p_manager.random()
        logger.info(f'Using proxy (try {tries + 1}): {proxy}')
        exit_code = proxy.run(command)
        tries += 1
        total_tries += 1

    logger.info('Done!')


if __name__ == '__main__':
    main()
