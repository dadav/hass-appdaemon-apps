import appdaemon.plugins.hass.hassapi as hass
import re
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep
from pathlib import Path

SERVICE_URL = "https://www.breitbandmessung.de/test"

class Breitbandmessung(hass.Hass):
  def initialize(self):
    self.log('Breitbandmessung started')
    self.register_service("breitbandmessung/run_speedtest", self.run_speedtest)
    runtime = datetime.time(0, 0, 0)
    self.run_hourly(self.run_speedtest, runtime)
    self.run_speedtest()

  def run_speedtest(self, *args, **kwargs):
    self.log('Setting up the chromium driver')
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    self.driver = webdriver.Chrome(options=chrome_options)
    self.element_wait = WebDriverWait(self.driver, self.args["interaction_timeout"])
    self.result_wait = WebDriverWait(self.driver, self.args["speedtest_timeout"])
    self.driver.get(SERVICE_URL)
    element = self.element_wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, 'modal-dialog-centered')))
    element = self.element_wait.until(EC.element_to_be_clickable((By.ID, 'allow-necessary')))
    element.click()
    element = self.element_wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'btn-primary')))
    element.click()
    element = self.element_wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Akzeptieren']")))
    element.click()
    self.log('Speedtest will start now...')
    server_text = self.element_wait.until(EC.presence_of_element_located((By.CLASS_NAME, "rtt-info"))).text
    match = re.search(r'Die Laufzeit wird zu Servern in (.*) gemessen', server_text)
    if match:
      server = match.groups()[0]
      self.log(f"Use server {server}.")
    else:
      server = 'Unknown'
      self.log('Server can not be parsed.')
    self.result_wait.until(EC.presence_of_element_located((By.XPATH, "//h1[text()='Die Browsermessung ist abgeschlossen.']")))
    sleep(5)
    ping = self.driver.find_element(By.XPATH, "//span[@class='title' and text()='Laufzeit']/parent::div/following-sibling::div/span").text
    ping = int(ping)
    download = self.driver.find_element(By.XPATH, "//span[@class='title' and text()='Download']/parent::div/following-sibling::div/span").text
    download = float(download.replace(',','.'))
    upload = self.driver.find_element(By.XPATH, "//span[@class='title' and text()='Upload']/parent::div/following-sibling::div/span").text
    upload = float(upload.replace(',','.'))
    test_id = self.driver.find_element(By.XPATH, "//div/table/tbody/tr[5]/td[3]").text
    self.log(f"TestID: {test_id}\tPing: {ping}\tDownload: {download}\tUpload: {upload}")
    execution_time = datetime.datetime.now().strftime('%d.%m.%Y, %H:%M:%S')

    common_informations = {
      'test_id': test_id,
      'server': server,
      'icon': 'mdi:speedometer',
      'execution_time': execution_time,
    }

    if self.args["screenshots"] and (
      self.args["screenshots_threshold"]["download"] >= download or
      self.args["screenshots_threshold"]["upload"] >= upload or
      self.args["screenshots_threshold"]["ping"] <= ping):
      common_informations = {
        **common_informations,
        'screenshot_base64': self.driver.get_screenshot_as_base64()
      }

    self.set_state('sensor.breitbandmessung_ping',
                    state=ping,
                    attributes={**common_informations,
                    'unit_of_measurement': 'ms',
                    'friendly_name': 'Breitbandmessung Ping'})
    self.set_state('sensor.breitbandmessung_download',
                    state=download,
                    attributes={**common_informations,
                    'unit_of_measurement': 'Mbit/s',
                    'friendly_name': 'Breitbandmessung Download'})
    self.set_state('sensor.breitbandmessung_upload',
                    state=upload,
                    attributes={**common_informations,
                    'unit_of_measurement': 'Mbit/s',
                    'friendly_name': 'Breitbandmessung Upload'})
    self.driver.quit()
