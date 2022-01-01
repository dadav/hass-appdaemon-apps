import re
import appdaemon.plugins.hass.hassapi as hass
import yfinance as yf
# from datetime import datetime

RE_NON_ALPHA = re.compile(r'[\W_]+')

def normalize_sym(old_sym):
    old_sym = old_sym.lower()
    old_sym = RE_NON_ALPHA.sub('', old_sym)
    return old_sym

class Finance(hass.Hass):
    def initialize(self):
        self.log('Finance started')
        self.last_time = dict()
        self.register_service("finance/fetch_data", self.fetch_data)
        self.run_every(self.fetch_data, "now", self.args["interval_in_minutes"] * 60)
        self.fetch_data()

    def fetch_data(self, *args, **kwargs):
        symbols = ' '.join(self.args['symbols'])
        self.log('Fetching data for the following symbols: %s', symbols)

        tickers = yf.Tickers(symbols)

        for sym, data in tickers.tickers.items():
            data = data.info

            # # skip if value has not never date
            # unix_time = data.get('regularMarketTime', None)
            # if sym in self.last_time and unix_time is not None and self.last_time[sym] == unix_time:
            #     continue
            # self.last_time[sym] = unix_time
            # time = datetime.utcfromtimestamp(unix_time)

            common = {
                'device_class': 'monetary',
                'friendly_name': data.get('shortName', sym),
                'state_class': 'measurement',
                'unit_of_measurement': data.get('currencySymbol', '$'),
                'entity_picture': data.get('logo_url', None),
                'icon': 'mdi:cash',
                # 'value_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            }

            nsym = normalize_sym(sym)

            value = data.get('regularMarketPrice', None)
            if value is not None:
                self.set_state(f'sensor.finance_{nsym}', state=value, attributes={**common})

            diff = data.get('regularMarketChange', None)
            if diff is not None:
                self.set_state(f'sensor.finance_{nsym}_diff', state=diff, attributes={**common, 'icon': 'swap-vertical-circle'})

            diff_pcent = data.get('regularMarketChangePercent', None)
            if diff_pcent is not None:
                self.set_state(f'sensor.finance_{nsym}_diff_percent', state=diff_pcent * 100.0, attributes={**common, 'unit_of_measurement': '%', 'icon': 'mdi:percent'})
