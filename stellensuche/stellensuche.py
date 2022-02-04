#!/usr/bin/env python3

import re
import json
import requests as r
import unicodedata
from bs4 import BeautifulSoup as BS
import appdaemon.plugins.hass.hassapi as hass

STARTSEITE_URL = 'https://lobw.kultus-bw.de/lobw/Stellen/Suche/Sbs'
LEHRAMT_DATA_URL = 'https://lobw.kultus-bw.de/lobw/ComboBox/LoadWerte?WerteListeValue=0&WgVerfahren=LEIN&WgNummer=43'
ORTE_DATA_URL = 'https://lobw.kultus-bw.de/lobw/ComboBox/LoadWerte?WerteListeValue=0&WgVerfahren=LEIN&WgNummer=76'
FACHRICHTUNGEN_DATA_URL = 'https://lobw.kultus-bw.de/lobw/ComboBox/LoadWerteStellenFaecher?WerteListeValue=0&WgVerfahren=LEIN&lehramt=SOP'


def remove_accents(input_str):
    """
    https://stackoverflow.com/a/517974
    """
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])


def get_json_from_url(url):
    req = r.get(url)
    req.raise_for_status()
    return req.json()


def get_value_or_default(data, key, default=None):
    kv = {item['Text']: item['Value'] for item in data['data']}

    if key in kv:
        return kv[key]

    lkey = key.lower()

    # try to find substring
    for k, v in kv.items():
        if lkey in k.lower():
            return v

    return default


class Stellensuche(hass.Hass):
    def initialize(self):
        self.request_data = None
        self.log('Stellensuche started')
        self.register_service("stellensuche/run_stellensuche", self.run_stellensuche)
        self.run_every(self.run_stellensuche, "now", int(self.args['interval_in_mins']))
        self.run_stellensuche()

    def build_request_data(self):
        self.request_data = {
            "Lehramt": "",
            "Fach1": "",
            "Fach2": "",
            "Fach3": "",
            "Ort": "",
            "Umkreis": "",
        }

        ort = self.args['ort']
        if ort is not None:
            orte_json = get_json_from_url(ORTE_DATA_URL)
            self.request_data['Ort'] = get_value_or_default(orte_json, ort, "")

        lehramt = self.args['lehramt']
        if lehramt is not None:
            lehramt_json = get_json_from_url(LEHRAMT_DATA_URL)
            self.request_data['Lehramt'] = get_value_or_default(lehramt_json, lehramt, "")

        self.request_data['Umkreis'] = self.args['umkreis'] or ""

        fachrichtungen = self.args['fachrichtungen']
        fach_json = get_json_from_url(FACHRICHTUNGEN_DATA_URL)
        for num, fach in enumerate(fachrichtungen, start=1):
            self.request_data[f"Fach{num}"] = get_value_or_default(fach_json, fach, "")

    def run_stellensuche(self, *args, **kwargs):
        if self.request_data is None:
            self.build_request_data()

        # fetch options
        data = {
            **{
                "Erhebung": "Sbs",
                "RpBezirk": "",
                "saveOption": "list",
                "IsOhneGs": "false",
                "IsOhneWhr": "false",
                "X-Requested-With": "XMLHttpRequest"
            },
            **self.request_data
        }

        with r.Session() as s:
            startseite = s.get(STARTSEITE_URL)
            startseite.raise_for_status()
            soup = BS(startseite.text, 'html.parser')
            token = soup.select_one('input[name=__RequestVerificationToken]').attrs['value']
            data["__RequestVerificationToken"] = token
            ergebnis = s.post('https://lobw.kultus-bw.de/lobw/Stellen/Ergebnis', data=data)
            ergebnis.raise_for_status()
            search = re.search(r"let searchModel = '([^']*)';", ergebnis.text)

            if search is None:
                result = None
            else:
                raw_code = search.groups()[0]
                result = json.loads(raw_code.encode('utf-8').decode('unicode-escape'))

            fix = '_'

            if data['Lehramt'] != '':
                fix = f'_{data["Lehramt"]}_'

            if self.args['ort']:
                clean_ort = remove_accents(self.args['ort'])
                if fix == '_':
                    fix = f'_{clean_ort}_'
                else:
                    fix = f'{fix}{clean_ort}'

            if data['Umkreis'] != '':
                if fix == '_':
                    fix = f'_{data["Umkreis"]}_'
                else:
                    fix = f'{fix}{data["Umkreis"]}'

            if data['Fach1'] != '':
                if fix == '_':
                    fix = f'_{data["Fach1"]}_'
                else:
                    fix = f'{fix}{data["Fach1"]}'

            if data['Fach2'] != '':
                if fix == '_':
                    fix = f'_{data["Fach2"]}_'
                else:
                    fix = f'{fix}{data["Fach2"]}'

            if data['Fach3'] != '':
                if fix == '_':
                    fix = f'_{data["Fach3"]}_'
                else:
                    fix = f'{fix}{data["Fach3"]}'

            total = result['TotalCount'] if result is not None else 0

            stellen = {item['AusschreibungsNummer']: f'{item["Ort"]} ({item["Schulbezeichnung"]})' for item in result['Stellen']} if result is not None else {}

            self.set_state(f'sensor.stellensuche{fix}total_count',
                            state=total,
                            attributes={'friendly_name': 'Anzahl der Stellen', 'stellen': stellen})
